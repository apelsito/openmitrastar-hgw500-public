"""F372 bounded install state machine. Import and CLI are file-only.

There is deliberately no physical launcher, default backend or --execute.
The immutable NO_GO preparation is never rewritten: a separately verified,
source-bound admission is mandatory before any injected effect is constructed.
Original F365 flash primitives own all physical geometry and writes.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import hashlib
import json
import math
from pathlib import Path
import re
import time
from typing import Mapping

import f365_install_executor as original_writer
import f372_install_contract as contract

ROOT = Path(__file__).resolve().parents[1]
Failure = original_writer.Failure
require = original_writer.require
GATES = frozenset(('authorization', 'recovery', 'executor_review', 'host_lease',
                   'uart_nonce', 'transport_review', 'live_boot'))
UUID = re.compile(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}')
SHA = re.compile(r'[0-9a-f]{64}')


@dataclass(frozen=True)
class EvidenceRef:
    path: str
    sha256: str


@dataclass(frozen=True)
class VerifiedAdmission:
    plan_path: str
    plan_sha256: str
    scope_sha256: str
    initial_boot_id: str
    lease_id: str
    nonce_sha256: str
    expires_unix: float
    source_pins: Mapping[str, str]
    receipts: Mapping[str, EvidenceRef]


@dataclass(frozen=True)
class AdmissionDecision:
    plan_sha256: str
    scope_sha256: str
    initial_boot_id: str
    lease_id: str
    nonce_sha256: str
    expires_unix: float
    execution_scope: str = 'offline_simulation'
    status: str = 'PASS_VERIFIED_EXACT_F372_ADMISSION'
    verified_receipts: Mapping[str, str] = field(default_factory=dict)


def save_new(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=True)
        stream.write('\n')


def _error_code(error):
    message = str(error)
    # Backend exceptions can contain credentials, payloads or client identity.
    # Only a short machine reason code is retained, never arbitrary text.
    return message if re.fullmatch(r'[a-z][a-z0-9_-]{0,95}', message) else type(error).__name__


def _source_guard(admission, plan):
    pins = dict(admission.source_pins)
    mandatory = {str(Path(__file__).resolve()), str(ROOT/'tools/f365_install_executor.py'),
                 str(ROOT/'tools/f372_postboot_gate.py')}
    require(mandatory <= set(pins), 'executor_and_gate_source_pins_required')
    for source, digest in plan['sources'].items():
        require(pins.get(source) == digest, 'original_source_pin_missing_or_changed')
    for source, digest in pins.items():
        require(isinstance(digest, str) and SHA.fullmatch(digest), 'source_pin_digest')
        # The sealed source set includes one exact WSL provenance input.
        # Preserve that reviewed path by exact original pin equality; new
        # paths still require the strict C:/D: no-reparse local policy.
        checked = source if plan['sources'].get(source) == digest else contract.local_path(source)
        require(contract.sha(checked) == digest, 'execution_source_drift')


def _admit(admission, plan, verifier, clock):
    require(isinstance(admission, VerifiedAdmission), 'typed_verified_admission_required')
    require(callable(verifier), 'independent_admission_verifier_required')
    require(SHA.fullmatch(admission.plan_sha256 or '') and SHA.fullmatch(admission.scope_sha256 or ''),
            'admission_hash_binding')
    require(UUID.fullmatch(admission.initial_boot_id or '') and SHA.fullmatch(admission.nonce_sha256 or '')
            and bool(admission.lease_id), 'admission_epoch_lease_nonce')
    require(math.isfinite(admission.expires_unix) and clock() < admission.expires_unix,
            'admission_expired')
    loaded = contract.load_plan(admission.plan_path, admission.plan_sha256)
    require(loaded == plan, 'immutable_plan_binding')
    require(admission.scope_sha256 == plan['owner_authorization_scope_sha256'], 'admission_exact_scope')
    require(set(admission.receipts) == GATES, 'independent_gate_receipts_required')
    for ref in admission.receipts.values():
        require(isinstance(ref, EvidenceRef) and SHA.fullmatch(ref.sha256 or ''), 'typed_gate_reference_required')
        require(contract.sha(contract.local_path(ref.path)) == ref.sha256, 'gate_evidence_drift')
    _source_guard(admission, plan)
    decision = verifier(admission, plan)
    require(isinstance(decision, AdmissionDecision), 'typed_independent_decision_required')
    require(decision.status == 'PASS_VERIFIED_EXACT_F372_ADMISSION'
            and decision.execution_scope in ('offline_simulation', 'physical'), 'admission_decision_scope')
    for key in ('plan_sha256', 'scope_sha256', 'initial_boot_id', 'lease_id', 'nonce_sha256', 'expires_unix'):
        require(getattr(decision, key) == getattr(admission, key), 'independent_admission_binding')
    require(dict(decision.verified_receipts) == {key: ref.sha256 for key, ref in admission.receipts.items()},
            'independent_gate_decision_binding')
    return decision


class Host:
    """Reusable host adapter; every effect is supplied by the reviewed backend.

    Backend owns lease/PnP/nonce/network verification, child containment and
    bounded SSH. No subprocess, network or backup is created by this adapter.
    Its configuration/platform methods cannot call the old physical CLI.
    """
    def __init__(self, plan, out, *, backend=None):
        require(backend is not None, 'host_backend_unavailable')
        self.plan, self.out, self.backend = plan, Path(out), backend
        self.execution_scope = backend.execution_scope
        self.servers = []
        self.transport_events = []
        self.network_check_failures = 0

    def guard(self):
        for path, digest in self.plan['sources'].items():
            require(contract.sha(path) == digest, 'source_drift')
        return self.backend.guard() is True

    def network_guard(self):
        passed = self.guard() and self.backend.network_guard() is True
        if not passed:
            self.network_check_failures += 1
        return passed

    def ssh(self, command, data=b'', timeout=20, allow_disconnect=False):
        require(self.network_guard(), 'network_guard')
        return self.backend.ssh(command, data=data, timeout=timeout, allow_disconnect=allow_disconnect)

    def admission_binding(self, admission, decision):
        return self.backend.admission_binding(admission, decision)

    def initial_binding(self, identity):
        return self.backend.initial_binding(identity)

    identity = original_writer.Host.identity
    wait_identity = original_writer.Host.wait_identity
    watchdog_inactive = original_writer.Host.watchdog_inactive
    verify_store = original_writer.Host.verify_store
    verify_configuration = original_writer.Host.verify_configuration
    verify_ethernet = original_writer.Host.verify_ethernet
    verify_thermal_disabled = original_writer.Host.verify_thermal_disabled

    def reboot_to_prompt(self, uart, software_recovery=False):
        require(software_recovery is False, 'serial_reset_fallback_forbidden')
        mask = int(self.ssh('cat /proc/sys/kernel/sysrq').strip())
        require(mask == 1 or bool(mask & 128), 'sysrq_reboot_disabled')
        return original_writer.base.Host.reboot_to_prompt(self, uart, software_recovery=False)

    def platform(self, name, out):
        require(self.network_guard(), 'network_guard_before_platform')
        return self.backend.platform(name, out)

    def contain(self):
        outcomes = []
        for server in self.servers:
            try:
                outcomes.append(server.close() is True)
            except Exception:
                outcomes.append(False)
        return self.backend.contain() is True and all(outcomes)


class _PinnedPortSerial:
    """Route the old capture's COM3 assignment to reviewed COM4, without I/O."""
    def __init__(self, inner, port):
        object.__setattr__(self, '_inner', inner)
        object.__setattr__(self, '_port', port)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        if name in ('_inner', '_port'):
            object.__setattr__(self, name, value)
        elif name == 'port':
            require(value == 'COM3', 'old_capture_port_assignment_changed')
            self._inner.port = self._port
        else:
            setattr(self._inner, name, value)


class Uart(original_writer.Uart):
    """Original bounded writer/capture with an explicitly supplied serial factory.

    No native serial factory is selected. A physical factory must come from
    the future reviewed launcher with a matching nonce and retained lease.
    """
    def __init__(self, plan, guard, out, *, serial_factory=None, execution_scope=None):
        require(callable(serial_factory), 'uart_backend_unavailable')
        require(execution_scope in ('offline_simulation', 'physical'), 'uart_effect_scope')
        super().__init__(plan, guard, out)
        self.execution_scope = execution_scope
        port = plan['host_binding']['uart_port']
        require(port == 'COM4', 'reviewed_uart_port')
        self.factory = lambda: _PinnedPortSerial(serial_factory(), port)


class _TrackedUart:
    """Detect command-level ambiguity even when the legacy writer clears flight.

    A NEW prompt alone is insufficient: the exact erase/write receipt must
    match before an automatic second write can ever be considered.
    """
    def __init__(self, inner):
        self.inner = inner
        self.ambiguous_write = False
        self.mutation_calls = 0

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def __setattr__(self, name, value):
        if name in ('inner', 'ambiguous_write', 'mutation_calls'):
            object.__setattr__(self, name, value)
        else:
            setattr(self.inner, name, value)

    def mutate(self, command):
        if command == original_writer.ERASE_COMMAND:
            expected = [f'Erase: flash=0x{contract.LIVE:x} size={contract.PREFIX}']
        else:
            match = re.fullmatch(r'spi_flash write 0x007e0000 0x83000000 0x([0-9a-f]{8})', command)
            require(match is not None, 'unexpected_write_command')
            n = int(match[1], 16)
            require(n == contract.SPECS['f372']['bytes'] == contract.SPECS['f365']['bytes']
                    and n <= contract.PREFIX, 'unexpected_write_size')
            expected = [f'Write: flash=0x{contract.LIVE:x} mem=0x{contract.LOAD:x} size={n} ret_size={n}']
        self.mutation_calls += 1
        self.ambiguous_write = True
        response = self.inner.mutate(command)
        require(original_writer.response_lines(response, command) == expected, 'ambiguous_flash_receipt')
        self.ambiguous_write = False
        return response


class _GuardedHost:
    """Keep expiry/receipt/source checks on original transfer and UART guards."""
    def __init__(self, inner, admission_guard):
        self.inner = inner
        self.admission_guard = admission_guard

    def __getattr__(self, name):
        return getattr(self.inner, name)

    def guard(self):
        self.admission_guard()
        return self.inner.guard() is True

    def network_guard(self):
        self.admission_guard()
        return self.inner.network_guard() is True


def _default_postboot(host, identity, out):
    import f372_postboot_gate as gate
    manifest, srcversion = gate.inputs()
    text = host.ssh('sh -s', gate.remote_script(manifest['runtime_bindings']).encode('ascii'), timeout=90)
    report = gate.evaluate(text.decode('ascii'), manifest['runtime_bindings'], srcversion,
                           host.plan['_f372_previous_boot'])
    out.mkdir(parents=True, exist_ok=False)
    save_new(out/'result.json', report)
    return report


def run(plan, out, verified_admission=None, *, host_factory=None, uart_factory=None,
        server_factory=None, writer=None, admission_verifier=None, postboot_gate=None,
        clock=time.time):
    """Run only with explicit backends plus a separately verified admission.

    Result scopes are explicit: a control-only keep is never release PASS.
    Faults before erase leave flash unchanged; uncertain mutations quarantine;
    candidate faults permit one F365 return only from an already fresh prompt.
    No branch issues a serial reset, power cycle or second reboot.
    """
    out = Path(out)
    require(not out.exists() or (out.is_dir() and not any(out.iterdir())), 'new_empty_evidence_directory_required')
    out.mkdir(parents=True, exist_ok=True)
    result = dict(schema='openmitrastar.f372-install-result/v1', status='NO_GO_ADMISSION', stage='admission',
                  execution_scope='unavailable', hardware_started=False, hardware_actions=False,
                  write_target='physical_mtd4/linux_live', offset=contract.LIVE, erase_bytes=contract.PREFIX,
                  candidate_name='f372candidate', return_name='f365return', baseline_name='f367r9baseline',
                  controlled_reboot_attempts=0, candidate_write_attempts=0, return_write_attempts=0,
                  candidate_writer_confirmed=False, candidate_kept=False, f365_return_confirmed=False,
                  serial_reset_attempted=False, radio_reconfiguration_performed=False,
                  flash_command_in_flight=False, retain_lease_required=True, release_pass=False,
                  client_gate=False, traffic_gate=False, repeated_coldboot_gate=False,
                  acceptance_pending=list(plan.get('acceptance_pending', [])))
    host = uart = decision = None
    store_crc = plan.get('store', {}).get('crc32')
    write_started = False
    candidate_confirmed = False

    def checkpoint(stage):
        result['stage'] = stage
        with (out/'events.jsonl').open('a', encoding='ascii') as stream:
            stream.write(json.dumps(dict(stage=stage, monotonic_ms=round(time.monotonic()*1000)))+'\n')

    def admission_guard():
        require(clock() < verified_admission.expires_unix, 'admission_expired')
        _source_guard(verified_admission, plan)
        for ref in verified_admission.receipts.values():
            require(contract.sha(contract.local_path(ref.path)) == ref.sha256, 'gate_evidence_drift')
        require(host.admission_binding(verified_admission, decision) is True, 'live_lease_nonce_binding')

    def guard():
        require(host.guard() is True and host.network_guard() is True, 'retained_lease_or_network_guard')

    try:
        require(callable(host_factory) and callable(uart_factory) and callable(server_factory),
                'explicit_effect_factories_required')
        decision = _admit(verified_admission, plan, admission_verifier, clock)
        result['execution_scope'] = decision.execution_scope
        effect_plan = json.loads(json.dumps(plan))
        # Legacy host/UART guards run during each original writer operation.
        # Extend their private copy, never the sealed preparation, so new
        # executor/postboot pins remain guarded throughout a transfer/write.
        effect_plan['sources'] = dict(verified_admission.source_pins)
        # Reuse the unchanged F365 journal acceptance from its exact pinned
        # campaign. The F372 preparation deliberately omitted this old Host
        # input; adding it to the private adapter plan avoids an untested
        # return path without modifying any historical plan or firmware.
        require(plan['sources'].get(str(contract.OLD_PLAN)) == contract.OLD_PLAN_SHA,
                'pinned_configuration_baseline_required')
        effect_plan['boot_acceptance'] = contract.read(contract.OLD_PLAN)['boot_acceptance']
        effect_plan['known_hosts'] = plan['images']['f367r9']['known_hosts_path']
        effect_plan['_f372_previous_boot'] = verified_admission.initial_boot_id
        host = host_factory(effect_plan, out)
        require(host.execution_scope == decision.execution_scope, 'host_effect_scope_mismatch')
        host = _GuardedHost(host, admission_guard)
        raw_uart = uart_factory(effect_plan, host.guard, out)
        uart = _TrackedUart(raw_uart)
        require(raw_uart.execution_scope == decision.execution_scope, 'uart_effect_scope_mismatch')
        driver = original_writer if writer is None else writer
        if decision.execution_scope == 'physical':
            require(driver is original_writer, 'physical_writer_must_be_unchanged_original')
            require(postboot_gate is None, 'physical_postboot_must_be_source_bound_gate')
        guard()
        checkpoint('live-r9-baseline')
        identity = host.identity('f367r9')
        require(identity.get('boot_id') == verified_admission.initial_boot_id and host.initial_binding(identity) is True,
                'baseline_epoch_nonce_mismatch')
        result['baseline_identity'] = identity
        result['baseline_watchdog'] = host.watchdog_inactive()
        require(result['baseline_watchdog'].get('device_opened') == 0
                and result['baseline_watchdog'].get('ready_for_arm') == 1,
                'baseline_watchdog_not_inactive')
        result['store_before'] = host.verify_store()
        require(result['store_before'].get('sha256') == plan['store']['sha256'], 'baseline_store_binding')
        result['return_reference'] = dict(path=plan['images']['f365']['path'],
                                        sha256=plan['images']['f365']['sha256'],
                                        bytes=plan['images']['f365']['bytes'], copied=False)
        guard()
        uart.open()
        result['hardware_started'] = decision.execution_scope == 'physical'
        result['hardware_actions'] = result['hardware_started']
        require(host.identity('f367r9').get('boot_id') == verified_admission.initial_boot_id,
                'baseline_changed_before_reboot')
        host.watchdog_inactive()
        guard()
        checkpoint('one-controlled-reboot')
        result['controlled_reboot_attempts'] = 1
        host.reboot_to_prompt(uart, software_recovery=False)
        require(uart.has_prompt() and not getattr(uart, 'failed', None), 'fresh_bootbase_prompt_missing')
        guard()
        checkpoint('protected-store-r9-readback')
        result['domain_before'] = driver.domain(uart, effect_plan, store_crc)
        result['current_r9_fullslot_crc32'] = driver.flash_crc(uart, contract.LIVE, contract.SLOT,
                                                            plan['images']['f367r9']['full_slot_crc32'])
        guard()
        checkpoint('write-exact-f372')
        result['candidate_write_attempts'] = 1
        write_started = True
        result['writer'] = driver.write_image(uart, host, effect_plan, plan['images']['f372'],
                                             out/'install-f372', store_crc, server_factory)
        require(result['writer'].get('image') == plan['images']['f372']['sha256']
                and result['writer'].get('bytes') == plan['images']['f372']['bytes']
                and result['writer'].get('full_slot_crc32') == plan['images']['f372']['full_slot_crc32']
                and result['writer'].get('byte_compare') is True, 'candidate_writer_scope')
        candidate_confirmed = result['candidate_writer_confirmed'] = True
        guard()
        checkpoint('boot-written-f372')
        result['candidate_identity'] = driver.boot_written(uart, host, effect_plan, 'f372',
                                                          verified_admission.initial_boot_id)
        require(result['candidate_identity'].get('boot_id') != verified_admission.initial_boot_id
                and UUID.fullmatch(result['candidate_identity'].get('boot_id', '')), 'candidate_new_boot')
        guard()
        checkpoint('postboot-control-f372')
        postboot = _default_postboot if postboot_gate is None else postboot_gate
        result['postboot_control'] = postboot(host, result['candidate_identity'], out/'postboot-f372')
        report = result['postboot_control']
        require(report.get('status') == 'PASS_CONTROL_ONLY' and report.get('release_pass') is False
                and report.get('boot_id') == result['candidate_identity']['boot_id']
                and bool(report.get('checks')) and all(v is True for v in report['checks'].values()),
                'f372_postboot_control_failed')
        guard()
        result['candidate_kept'] = True
        result['status'] = 'PASS_F372_CONTROL_ONLY'
        checkpoint('complete-f372-control-only')
    except Exception as error:
        result['error'] = _error_code(error)
        if uart is not None and result['controlled_reboot_attempts']:
            mutated = bool(getattr(uart, 'erase_requested', False) or getattr(uart, 'write_requested', False))
            uncertain = bool(getattr(uart, 'write_in_flight', False) or uart.ambiguous_write
                             or (write_started and mutated and not candidate_confirmed))
            if uncertain:
                result['status'] = 'STOP_UNCERTAIN_NO_AUTOMATIC_WRITE'
            elif not uart.has_prompt() or getattr(uart, 'failed', None):
                result['status'] = 'STOP_NO_FRESH_PROMPT_NO_RESET'
            elif not mutated and not candidate_confirmed:
                result['status'] = 'FAILED_BEFORE_ERASE_BASELINE_UNCHANGED'
            elif candidate_confirmed:
                try:
                    require(host.contain() is True, 'prior_helpers_not_contained')
                    guard()
                    require(uart.has_prompt() and not uart.write_in_flight and not uart.ambiguous_write,
                            'fresh_prompt_required_for_return')
                    result['return_domain_before'] = driver.domain(uart, effect_plan, store_crc)
                    guard()
                    checkpoint('one-exact-f365-return')
                    result['return_write_attempts'] = 1
                    result['return_writer'] = driver.write_image(uart, host, effect_plan, plan['images']['f365'],
                                                                out/'return-f365', store_crc, server_factory)
                    require(result['return_writer'].get('image') == plan['images']['f365']['sha256']
                            and result['return_writer'].get('bytes') == plan['images']['f365']['bytes']
                            and result['return_writer'].get('byte_compare') is True
                            and result['return_writer'].get('full_slot_crc32') == plan['images']['f365']['full_slot_crc32'],
                            'return_writer_scope')
                    guard()
                    result['returned_identity'] = driver.boot_written(uart, host, effect_plan, 'f365',
                                                                     verified_admission.initial_boot_id)
                    require(UUID.fullmatch(result['returned_identity'].get('boot_id', ''))
                            and result['returned_identity']['boot_id'] != verified_admission.initial_boot_id
                            and result['returned_identity']['boot_id'] != result.get('candidate_identity', {}).get('boot_id'),
                            'return_new_boot')
                    result['return_platform'] = host.platform('f365', out/'platform-f365')
                    require(result['return_platform'].get('status') == 'PASS', 'return_platform_failed')
                    result['returned_watchdog'] = host.watchdog_inactive()
                    result['returned_store'] = host.verify_store()
                    require(result['returned_store'].get('sha256') == plan['store']['sha256'], 'return_store_binding')
                    result['returned_configuration'] = host.verify_configuration()
                    result['returned_ethernet'] = host.verify_ethernet()
                    result['returned_thermal'] = host.verify_thermal_disabled()
                    guard()
                    result['f365_return_confirmed'] = True
                    result['status'] = 'FAILED_F372_WITH_EXACT_F365_RETURN'
                    checkpoint('complete-exact-f365-return')
                except Exception as recovery:
                    result['recovery_error'] = _error_code(recovery)
                    result['status'] = 'STOP_RETURN_UNPROVEN_NO_RETRY'
    finally:
        if host is not None:
            try:
                result['children_contained'] = host.contain() is True
            except Exception:
                result['children_contained'] = False
        else:
            result['children_contained'] = True
        if uart is not None:
            result['flash_command_in_flight'] = bool(getattr(uart, 'write_in_flight', False))
            result['ambiguous_write'] = uart.ambiguous_write
            result['mutation_command_count'] = uart.mutation_calls
            try:
                result['uart'] = uart.close()
            except Exception:
                result['uart'] = {}
            result['containment_confirmed'] = (result['children_contained']
                and result['uart'].get('reader_stopped') is True and result['uart'].get('port_closed') is True
                and not result['uart'].get('reader_error'))
        else:
            result['uart'] = dict(reader_stopped=True, port_closed=True, opened=False)
            result['containment_confirmed'] = result['children_contained']
        try:
            if host is not None:
                guard()
            result['final_domain_guard'] = host is not None
        except Exception:
            result['final_domain_guard'] = False
        success = result['candidate_kept'] or result['f365_return_confirmed']
        result['retain_lease_required'] = not (success and result['containment_confirmed']
            and result['final_domain_guard'] and not result['flash_command_in_flight']
            and not result.get('ambiguous_write', False))
        if success and result['retain_lease_required']:
            result['status'] = 'STOP_CONTAINMENT_OR_GUARD_UNPROVEN'
        result['parent_quarantine_preserved'] = True
        result['lease_release_performed'] = False
        save_new(out/'result.json', result)
    return result


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    args = parser.parse_args()
    plan = contract.load_plan(args.plan, args.plan_sha256)
    print(json.dumps(dict(status='OFFLINE_VALID_F372_CORE_PHYSICAL_NO_GO', hardware_actions=False,
                          immutable_plan_status=plan['status'], physical_backend_available=False,
                          physical_launcher_implemented=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
