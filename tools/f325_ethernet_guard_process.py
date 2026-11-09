"""Bounded inherited-context checker for a future reviewed Ethernet executor.

No CLI. Construction does not inspect/open COM3 or start a process. The existing
PowerShell checker reads the live parent lease, pinned adapter and authenticated
board-binding context; it does not open UART. Source pins are checked before and
after execution. This checker is not the missing owner network authorization.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import shutil
import subprocess

from f325_ethernet_handoff import exact_pair


TOOLS = Path(__file__).resolve().parent
PINS = {
    'f325_assert_physical_context.ps1': '2ef11231c01448b4c257ebeac278c4a81c25912ffe81d3646f86e0f61b72c9f5',
    'f325_hardware_context.ps1': '085907ddbf3d0113df0ff66f2744f0e424bbda42a51bf6605cd47c2b74589571',
    'f319_uart_guard.ps1': 'c7522ad8787061d82805397a9521a6672a3cfbe497d026462dfb91eb954a3478',
}
EXPECTED_STDOUT = b'PASS_F325_INHERITED_PHYSICAL_CONTEXT'


def validate_sources() -> bool:
    return all(hashlib.sha256((TOOLS / name).read_bytes()).hexdigest() == digest
               for name, digest in PINS.items())


class InheritedPhysicalGuard:
    def __init__(self, *, direction: str, network_authorized: bool = False,
                 popen_factory=subprocess.Popen, validate=validate_sources,
                 resolve_program=shutil.which):
        self.image, _ = exact_pair(direction)
        self.direction = direction
        self.network_authorized = network_authorized
        self.popen_factory, self.validate, self.resolve_program = popen_factory, validate, resolve_program
        self.processes = []
        self.unknown_spawn = False
        self.terminal_failure = False
        self.calls = 0
        self.last_error_code = None

    @staticmethod
    def _stop(process) -> bool:
        try:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
            return process.poll() is not None
        except Exception:
            return False

    def __call__(self) -> bool:
        if self.network_authorized is not True or self.terminal_failure or not self.all_stopped():
            self.last_error_code = 'scope_or_prior_containment'
            return False
        process = None
        successful = False
        try:
            if self.validate() is not True:
                self.last_error_code = 'guard_source_drift'
                self.terminal_failure = True
                return False
            program = self.resolve_program('powershell.exe')
            if not program or not Path(program).is_absolute():
                self.last_error_code = 'guard_program_missing'
                self.terminal_failure = True
                return False
            arguments = [program, '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(TOOLS / 'f325_assert_physical_context.ps1'),
                '-CandidateSha256', self.image['sha256'], '-Direction', self.direction]
            self.calls += 1
            try:
                process = self.popen_factory(arguments, stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
            except Exception:
                self.unknown_spawn = True
                raise
            self.processes.append(process)
            output, _ = process.communicate(timeout=30)
            if (process.poll() != 0 or type(output) is not bytes or len(output) > 65536
                    or output.strip() != EXPECTED_STDOUT or self.validate() is not True):
                self.last_error_code = 'guard_result_not_exact'
                self.terminal_failure = True
                return False
            successful = True
        except Exception:
            self.last_error_code = 'guard_process_failed'
            self.terminal_failure = True
            return False
        finally:
            if process is not None:
                if not self._stop(process):
                    self.last_error_code = 'guard_termination_unconfirmed'
                    self.terminal_failure = True
                if process.stdout is not None:
                    try:
                        process.stdout.close()
                    except Exception:
                        self.terminal_failure = True
                        self.last_error_code = 'guard_output_close_unconfirmed'
        return successful and not self.terminal_failure and self.all_stopped()

    def all_stopped(self) -> bool:
        if self.unknown_spawn:
            return False
        try:
            return all(process.poll() is not None for process in self.processes)
        except Exception:
            return False

    def close_all(self) -> bool:
        results = [self._stop(process) for process in self.processes]
        return all(results) and self.all_stopped()

    def diagnostics(self) -> dict:
        return {'schema': 'openmitrastar.f325-ethernet-guard-process/v1',
            'calls': self.calls, 'terminal_failure': self.terminal_failure,
            'all_helpers_stopped': self.all_stopped(), 'unknown_spawn': self.unknown_spawn,
            'last_error_code': self.last_error_code, 'raw_output_logged': False}
