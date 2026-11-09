"""Mocked process handles only; never invokes PowerShell or reads a device."""
import io
import subprocess
from pathlib import Path
from unittest.mock import Mock

import pytest

from f323_ethernet_guard_process import EXPECTED_STDOUT, InheritedPhysicalGuard, validate_sources


class FakeProcess:
    def __init__(self, output=EXPECTED_STDOUT + b'\r\n', exit_code=0):
        self.output = output
        self.exit_code = exit_code
        self.returncode = None
        self.stdout = io.BytesIO()
        self.events = []
        self.timeout = False
        self.terminate_works = True
        self.kill_works = True
        self.close_error = False

    def communicate(self, timeout):
        self.events.append(('communicate', timeout))
        if self.timeout:
            raise subprocess.TimeoutExpired('synthetic-guard', timeout)
        self.returncode = self.exit_code
        return self.output, None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.events.append(('terminate',))
        if self.terminate_works:
            self.returncode = -1

    def kill(self):
        self.events.append(('kill',))
        if self.kill_works:
            self.returncode = -9

    def wait(self, timeout):
        self.events.append(('wait', timeout))
        if self.returncode is None:
            raise subprocess.TimeoutExpired('synthetic-guard', timeout)
        return self.returncode


def fixture(process=None, **kwargs):
    process = process or FakeProcess()
    factory = Mock(return_value=process)
    validate = Mock(return_value=True)
    options = dict(direction='promote', network_authorized=True, popen_factory=factory,
                   validate=validate, resolve_program=lambda _: str(Path('synthetic-powershell.exe').absolute()))
    options.update(kwargs)
    return InheritedPhysicalGuard(**options), process, factory, validate


@pytest.mark.parametrize('authority', [False, None, 1, 'yes'])
def test_no_network_authority_means_no_native_callback(authority):
    guard, _, factory, validate = fixture(network_authorized=authority)
    assert guard() is False
    factory.assert_not_called()
    validate.assert_not_called()


def test_constructor_is_inert_and_real_source_validation_is_file_only():
    guard, _, factory, validate = fixture()
    factory.assert_not_called()
    validate.assert_not_called()
    assert guard.all_stopped() is True
    assert validate_sources() is True


def test_exact_completed_checker_passes_with_fixed_safe_arguments():
    guard, process, factory, validate = fixture()
    assert guard() is True
    assert guard.all_stopped() is True and process.stdout.closed
    args, kwargs = factory.call_args
    argv = args[0]
    assert '-NonInteractive' in argv and '-NoProfile' in argv
    assert argv[argv.index('-Direction') + 1] == 'promote'
    assert argv[argv.index('-CandidateSha256') + 1] == guard.image['sha256']
    assert kwargs['stdin'] == subprocess.DEVNULL
    assert kwargs['stderr'] == subprocess.STDOUT
    assert validate.call_count == 2
    assert process.events == [('communicate', 30)]


@pytest.mark.parametrize('output,code', [(b'PASS_DIFFERENT', 0), (EXPECTED_STDOUT, 1),
    (EXPECTED_STDOUT + b'\nUNTRUSTED_SECRET', 0), (b'x' * 65537, 0), ('not bytes', 0)],
    ids=['wrong-marker', 'nonzero-exit', 'extra-output', 'oversized-output', 'not-bytes'])
def test_nonexact_result_is_terminal_without_logging_raw_output(output, code):
    guard, process, factory, _ = fixture(FakeProcess(output, code))
    assert guard() is False and guard.terminal_failure
    assert guard() is False and factory.call_count == 1
    assert process.stdout.closed and guard.all_stopped()
    assert 'UNTRUSTED_SECRET' not in str(guard.diagnostics())


def test_source_drift_refused_before_launch():
    guard, _, factory, validate = fixture()
    validate.return_value = False
    assert guard() is False
    factory.assert_not_called()
    assert guard.terminal_failure and guard.all_stopped()


def test_source_change_during_checker_cannot_qualify_uart():
    guard, _, _, validate = fixture()
    validate.side_effect = [True, False]
    assert guard() is False and guard.terminal_failure


@pytest.mark.parametrize('resolved', [None, 'relative.exe'])
def test_unresolved_or_relative_interpreter_never_launches(resolved):
    guard, _, factory, _ = fixture(resolve_program=lambda _: resolved)
    assert guard() is False
    factory.assert_not_called()


@pytest.mark.parametrize('needs_kill', [False, True])
def test_timeout_stops_only_owned_handle_and_proves_terminal_state(needs_kill):
    process = FakeProcess()
    process.timeout = True
    process.terminate_works = not needs_kill
    guard, _, _, _ = fixture(process)
    assert guard() is False
    assert ('terminate',) in process.events
    assert (('kill',) in process.events) is needs_kill
    assert guard.all_stopped() is True and process.stdout.closed


def test_unconfirmed_termination_blocks_next_check_and_retains_handle():
    process = FakeProcess()
    process.timeout = True
    process.terminate_works = process.kill_works = False
    guard, _, factory, _ = fixture(process)
    assert guard() is False and guard.all_stopped() is False
    assert guard() is False and factory.call_count == 1
    assert guard.close_all() is False
    assert guard.processes == [process]
    process.returncode = -9  # A later handle observation can resolve containment.
    assert guard.all_stopped() is True


def test_spawn_exception_is_sanitized_and_cannot_claim_no_live_helper():
    guard, _, factory, _ = fixture()
    factory.side_effect = RuntimeError('UNTRUSTED_SECRET')
    assert guard() is False
    assert guard.unknown_spawn and not guard.all_stopped() and not guard.close_all()
    assert 'UNTRUSTED_SECRET' not in str(guard.diagnostics())


def test_stdout_close_failure_cannot_return_true_after_finally():
    class BadClose(io.BytesIO):
        def close(self):
            raise OSError('UNTRUSTED_SECRET')
    process = FakeProcess()
    process.stdout = BadClose()
    guard, _, _, _ = fixture(process)
    assert guard() is False and guard.terminal_failure
    assert guard.all_stopped() is True


def test_unsupported_direction_cannot_construct_guard():
    with pytest.raises(ValueError):
        fixture(direction='fallback')
