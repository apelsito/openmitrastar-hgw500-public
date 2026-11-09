"""F366 install, one native acquisition and unconditional exact F365 return.

Default/import are file-only. The PowerShell owner supplies the fresh hardware
lease/nonce. Flash, Bootbase, scoped TFTP and serial recovery are unchanged F365
implementations. Diagnostic output is persisted before the watchdog reset.
"""
from pathlib import Path
import argparse
import json
import os
import queue
import re
import secrets
import subprocess
import threading
import time

import f365_install_executor as writer
import f365_install_contract as baseline
import f346_powershell as desktop_ps
from f365_failure_snapshot import save_failure_snapshot
from f366_dfs_campaign import review_transcript, strict_object

Failure, require = writer.Failure, writer.require
ROOT = baseline.ROOT
EVIDENCE_ROOT = Path('/workspace/OpenMitraStar/f366-acquisition')
SUPERVISOR_SHA = '015d16cafef7e13e008fa451dbc25d5887f4e6935e695c2e2cbca90f2ed74904'


class Uart(writer.Uart):
    """Same exact writer vocabulary, for the two image rows in this plan."""


def pending_command():
    return r'''set -eu
printf 'boot='; cat /run/openmitrastar/boot-state
printf 'radio2='; /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status | sed -n 's/^state=//p'
for pair in 'bridge2:/sys/class/net/br0/brif/wlan0' 'qdrv:/sys/module/qdrv' 'provider:/sys/module/qtn_radar_f366' 'wifi0:/sys/class/net/wifi0' 'owner:/run/openmitrastar/watchdog/owner.lock' 'socket:/run/openmitrastar/watchdog/supervisor.sock'; do
 key=${pair%%:*}; path=${pair#*:}; if [ -e "$path" ]; then printf '%s=1\n' "$key"; else printf '%s=0\n' "$key"; fi
done
printf 'fatal='; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access|VFS: Unable to mount root' || true
'''


def pending_response(raw):
    pairs = [line.split('=', 1) for line in raw.decode('ascii').splitlines()]
    require(all(len(pair) == 2 for pair in pairs), 'pending_response')
    rows = strict_object(pairs)
    require(rows == dict(boot='ready', radio2='ENABLED', bridge2='1', qdrv='0', provider='0', wifi0='0', owner='0', socket='0', fatal='0'), 'native_boot_not_pending_or_management_unhealthy')
    return dict(status='PASS_F366_PENDING_MANAGEMENT', checks=9, acquisition_started=False, radio2_enabled=True, wifi0_created=False)


class Host(writer.Host):
    def _guard(self, network):
        for path, digest in self.plan['sources'].items():
            require(baseline.sha(path) == digest, 'source_drift')
        args = [desktop_ps.executable(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(ROOT/'tools/assert_f366_context.ps1')]
        if network:
            args.append('-CheckNetwork')
        result = subprocess.run(args, env=desktop_ps.environment(), capture_output=True, timeout=30, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0 and result.stdout.strip() == b'PASS_F366_ACQUISITION_CONTEXT' and not result.stderr

    def initial_binding(self, identity):
        return json.loads(os.environ.get('OM_F366_CONTEXT', '{}')).get('initial_boot_id') == identity['boot_id']

    def backup_reference(self):
        image = self.plan['images']['f365']
        require(baseline.sha(image['path']) == image['sha256'], 'fallback_reference_changed')
        # The immutable private full image plus fresh pre-write physical CRC
        # below form the rollback binding; do not call this a fresh raw dump.
        return dict(path=image['path'], sha256=image['sha256'], fresh_physical_dump=False)

    def pending(self):
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                return pending_response(self.ssh(pending_command()))
            except (Failure, ValueError):
                time.sleep(2)
        raise Failure('f366_pending_management_timeout')

    def components(self):
        bindings = self.plan['runtime_bindings']
        paths = list(bindings)
        require(all(re.fullmatch(r'/[A-Za-z0-9_./-]+', p) and '..' not in p.split('/') for p in paths), 'runtime_binding_path')
        lines = self.ssh('sha256sum ' + ' '.join(paths), timeout=30).decode('ascii').splitlines()
        require(len(lines) == len(paths) and all(line.split() == [bindings[path], path] for line, path in zip(lines, paths)), 'installed_f366_runtime_hash')
        return dict(status='PASS', count=len(paths))

    def diagnostic(self, token, uart, output):
        """Stream only allowlisted diagnostic lines to disk as they arrive.

        Killing an SSH transport never kills/disarms the independent watchdog
        owner. Any lost/failed activation is followed by watchdog/serial return.
        """
        require(re.fullmatch('[0-9a-f]{32}', token), 'diagnostic_token')
        require(self.network_guard(), 'network_guard_before_activation')
        self.diagnostic_started = time.monotonic()
        process = subprocess.Popen(self.ssh_argv('/usr/sbin/om-f366-diagnostic activate ' + token), stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        self.children.append(process)
        messages = queue.Queue(maxsize=256)
        errors = []

        def reader(stream, kind):
            total = 0
            try:
                while True:
                    line = stream.readline(16385)
                    if not line:
                        break
                    total += len(line)
                    if total > 262144 or len(line) > 16384:
                        errors.append('diagnostic_output_limit')
                        break
                    try:
                        messages.put((kind, line), timeout=1)
                    except queue.Full:
                        errors.append('diagnostic_output_queue_full')
                        break
            finally:
                try:
                    messages.put((kind, None), timeout=1)
                except queue.Full:
                    errors.append('diagnostic_reader_close_queue_full')

        for stream, kind in ((process.stdout, 'stdout'), (process.stderr, 'stderr')):
            thread = threading.Thread(target=reader, args=(stream, kind), daemon=True)
            self.threads.append(thread)
            thread.start()
        start = time.monotonic()
        capture_refresh = start
        done = set()
        stderr_bytes = 0
        ignored_bytes = 0
        transcript = []
        uart.invalidate_prompt()
        uart.stop_autoboot(120)
        with output.open('x', encoding='ascii', newline='\n') as stream:
            try:
                while len(done) < 2:
                    require(time.monotonic()-start < 215, 'diagnostic_transport_deadline')
                    require(not uart.failed, 'uart_capture_failed')
                    require(not errors, errors[0] if errors else 'diagnostic_reader')
                    if time.monotonic()-capture_refresh >= 45:
                        uart.stop_autoboot(120)
                        capture_refresh = time.monotonic()
                    try:
                        kind, raw = messages.get(timeout=.2)
                    except queue.Empty:
                        continue
                    if raw is None:
                        done.add(kind)
                        continue
                    if kind == 'stderr':
                        stderr_bytes += len(raw)
                        continue
                    line = raw.decode('ascii', errors='strict').rstrip('\r\n')
                    if re.match(r'^OMF366_(STATUS |DIAGNOSTIC_COMPLETE |WATCHDOG_ARM_ACK |NATIVE_FAILED |FAILURE |FAILURE_STATUS |ERROR |SOFTWARE_DRAIN |SNAPSHOT )', line):
                        # Helper stdout is already numeric/redacted. Reject
                        # unexpected binary/control characters before saving.
                        require(all(32 <= ord(ch) < 127 for ch in line), 'diagnostic_output_encoding')
                        stream.write(line+'\n')
                        stream.flush()
                        os.fsync(stream.fileno())
                        transcript.append(line)
                    else:
                        ignored_bytes += len(raw)
                process.wait(timeout=3)
            finally:
                if process.poll() is None:
                    process.kill()
                    process.wait(timeout=3)
        report = review_transcript('\n'.join(transcript))
        report.update(transport_exit_code=process.returncode, stderr_bytes=stderr_bytes, nonallowlisted_stdout_bytes=ignored_bytes,
                      watchdog_arm_marker=sum(line == 'OMF366_WATCHDOG_ARM_ACK hardware=1 first_pet=1' for line in transcript),
                      transcript_path=str(output), transcript_sha256=baseline.sha(output))
        return report


def save(path, result):
    path.write_text(json.dumps(result, indent=2)+'\n', encoding='ascii')


def run(plan, out, host_factory=Host, uart_factory=Uart, server_factory=writer.ScopedTftpProcess):
    host = host_factory(plan, out)
    uart = uart_factory(plan, host.guard, out)
    result = dict(schema='openmitrastar.f366-acquisition-result/v1', status='FAILED', stage='baseline', target='mtd4/linux_live', erase_bytes=baseline.PREFIX,
                  diagnostic_attempts=0, callback_authority=0, dfs_transmission_allowed=False, radar_rf_acceptance=False,
                  wifi_client_tests=False, provider_unload_attempted=False, watchdog_may_remain_armed=False,
                  rollback_attempted=False, flash_command_in_flight=False)
    original = None
    store_crc = None
    reboot_started = False
    diagnostic_pass = False
    restore_started = False
    reset_before = 0

    def event(stage):
        result['stage'] = stage
        save(out/'progress.json', dict(stage=stage, monotonic_ms=round(time.monotonic()*1000)))

    def restore():
        nonlocal restore_started
        require(not uart.write_in_flight, 'ambiguous_flash_no_recovery')
        require(not restore_started, 'no_second_restore_attempt')
        restore_started = True
        require(host.contain(), 'prior_helpers_not_contained')
        if not uart.has_prompt():
            if result['diagnostic_attempts']:
                # The helper's session deadline is absolute 180s. Give the
                # owned hardware watchdog its full bounded reset opportunity.
                deadline = max(time.monotonic()+95, getattr(host, 'diagnostic_started', time.monotonic())+200)
                while time.monotonic() < deadline and not uart.has_prompt():
                    uart.stop_autoboot(120)
                    try:
                        uart.wait_prompt(min(45, max(1, deadline-time.monotonic())))
                    except Failure as error:
                        if str(error) != 'topaz_prompt_timeout':
                            raise
                if not uart.has_prompt():
                    result['software_recovery'] = True
                    host.reboot_to_prompt(uart, software_recovery=True)
            else:
                host.reboot_to_prompt(uart, software_recovery=True)
        require(uart.has_prompt(), 'fresh_bootbase_missing')
        result['post_reset_watchdog'] = writer.base.inactive_hardware(uart)
        result['watchdog_may_remain_armed'] = False
        if result['diagnostic_attempts']:
            result['watchdog_reset_observed'] = len(uart.reset_times) > reset_before and not result.get('software_recovery', False)
        require(store_crc is not None, 'original_store_unknown')
        writer.domain(uart, plan, store_crc)
        mutated = uart.erase_requested or uart.write_requested
        if mutated:
            result['rollback_attempted'] = True
            event('restore-f365')
            result['restore_writer'] = writer.write_image(uart, host, plan, plan['images']['f365'], out/'restore', store_crc, server_factory)
        event('boot-f365-return')
        result['returned_identity'] = writer.boot_written(uart, host, plan, 'f365', original['boot_id'], prefix_only=not mutated)
        result['return_platform'] = host.platform('f365', out/'platform-f365-return')
        result['returned_watchdog'] = host.watchdog_inactive()
        result['returned_store'] = host.verify_store()
        result['returned_configuration'] = host.verify_configuration()
        result['returned_ethernet'] = host.verify_ethernet()
        result['returned_thermal'] = host.verify_thermal_disabled()
        result['baseline_returned'] = True

    try:
        require(host.guard(), 'lease')
        original = host.identity('f365')
        require(host.initial_binding(original), 'initial_nonce_boot_mismatch')
        result['baseline'] = original
        result['baseline_watchdog'] = host.watchdog_inactive()
        result['store_before'] = host.verify_store()
        result['configuration_before'] = host.verify_configuration()
        result['rollback_reference'] = host.backup_reference()
        uart.open()
        reboot_started = True
        event('bootbase-preflight')
        host.reboot_to_prompt(uart)
        writer.base.inactive_hardware(uart)
        writer.selector(uart)
        result['protected_before'] = writer.protected(uart, plan)
        store_crc = writer.flash_crc(uart, baseline.STORE, baseline.STORE_BYTES, plan['store']['crc32'])
        result['store_crc32'] = store_crc
        result['current_f365_crc32'] = writer.flash_crc(uart, baseline.LIVE, baseline.SLOT, plan['images']['f365']['full_slot_crc32'])
        event('install-f366')
        result['writer'] = writer.write_image(uart, host, plan, plan['images']['f366'], out/'install', store_crc, server_factory)
        event('boot-f366')
        result['f366_identity'] = writer.boot_written(uart, host, plan, 'f366', original['boot_id'])
        event('f366-pending-preflight')
        result['pending_management'] = host.pending()
        result['runtime_hashes'] = host.components()
        result['configuration_boot'] = host.verify_configuration()
        result['ethernet'] = host.verify_ethernet()
        result['thermal_default'] = host.verify_thermal_disabled()
        result['store_pre_activation'] = host.verify_store()
        result['watchdog_pre_activation'] = host.watchdog_inactive()
        require(host.identity('f366')['boot_id'] == result['f366_identity']['boot_id'], 'boot_changed_before_activation')
        reset_before = len(uart.reset_times)
        event('native-acquisition-once')
        result['diagnostic_attempts'] = 1
        result['watchdog_may_remain_armed'] = True
        result['diagnostic'] = host.diagnostic(secrets.token_hex(16), uart, out/'diagnostic-transcript.log')
        save(out/'diagnostic-before-return.json', result['diagnostic'])
        require(result['diagnostic']['status'] == 'PASS_CAPTURED_DIAGNOSTIC_TELEMETRY' and result['diagnostic']['transport_exit_code'] == 0 and result['diagnostic']['watchdog_arm_marker'] == 1, 'diagnostic_evidence_failed')
        require(not uart.fatal, 'fatal_during_native_acquisition')
        diagnostic_pass = True
    except Exception as error:
        result['error'] = str(error) if isinstance(error, Failure) else type(error).__name__
    finally:
        # This snapshot is local and best-effort before any return/reset action.
        result['failure_snapshot_written'] = save_failure_snapshot(out, result)
        if reboot_started and original is not None and not uart.write_in_flight:
            try:
                restore()
                result['diagnostic_reset_signatures'] = max(0, len(uart.reset_times)-reset_before) if result['diagnostic_attempts'] else 0
                result['status'] = 'PASS_F366_ACQUISITION_WITH_F365_RETURN' if diagnostic_pass and result.get('watchdog_reset_observed') else 'FAIL_F366_WITH_F365_RETURN'
                event('complete-f365-returned')
            except Exception as error:
                result['recovery_error'] = str(error) if isinstance(error, Failure) else type(error).__name__
                result['status'] = 'FAILED_RECOVERY_UNPROVEN_NO_RETRY'
        elif reboot_started:
            result['status'] = 'STOP_UNCERTAIN_NO_AUTOMATIC_WRITE'
        try:
            result['children_contained'] = host.contain()
        except Exception:
            result['children_contained'] = False
        result['break_cleanup_verified'] = writer.clear_pending_break(uart)
        try:
            result['uart'] = uart.close()
        except Exception:
            result['uart'] = {}
        result['containment_confirmed'] = result['children_contained'] and result['uart'].get('reader_stopped') is True and result['uart'].get('port_closed') is True
        try:
            result['final_domain_guard'] = host.guard() is True
        except Exception:
            result['final_domain_guard'] = False
        result['flash_command_in_flight'] = uart.write_in_flight
        result['serial_recovery'] = getattr(uart, 'serial_recovery_record', {})
        result['retain_lease_required'] = not result['containment_confirmed'] or uart.write_in_flight or not result['final_domain_guard'] or result['watchdog_may_remain_armed'] or bool(result['serial_recovery'].get('break_attempted') and not result['serial_recovery'].get('break_cleared'))
        if result['uart'].get('reader_error') or not result['containment_confirmed'] or not result['final_domain_guard']:
            result['status'] = 'FAILED_CONTAINMENT_OR_UART'
        save(out/'result.json', result)
    print(json.dumps(dict(status=result['status'], result=str(out/'result.json'))), flush=True)
    return int(result['status'] != 'PASS_F366_ACQUISITION_WITH_F365_RETURN')


def load_plan(path, digest):
    require(baseline.sha(path) == digest, 'plan_hash')
    plan = json.loads(Path(path).read_text(encoding='ascii'), object_pairs_hook=strict_object)
    require(plan['schema'] == 'openmitrastar.f366-acquisition-plan/v1' and plan['status'] == 'PASS_OFFLINE_REVIEWED_EXECUTOR', 'plan_scope')
    require(plan['images']['f365'] == baseline.images()['f365'] and set(plan['images']) == {'f365', 'f366'}, 'fallback_scope')
    require(plan['store'] == baseline.store_binding() and plan['protected'] == baseline.protected_backups() and plan['bootargs'] == baseline.BOOTARGS, 'storage_contract')
    require(plan['known_hosts'] == plan['images']['f365']['known_hosts_path'] and Path(plan['evidence_root']).resolve() == EVIDENCE_ROOT.resolve(), 'execution_scope')
    require(plan['callback_authority'] == 0 and plan['diagnostic_channel'] == 36 and plan['diagnostic_bandwidth'] == 80 and plan['watchdog_session_ms'] == 180000 and plan['always_restore_f365'] is True, 'diagnostic_scope')
    require(plan['runtime_bindings']['/usr/sbin/om-watchdog-supervisor'] == SUPERVISOR_SHA, 'supervisor_binding')
    for file, expected in plan['sources'].items():
        require(baseline.sha(file) == expected, 'source_drift')
    image = plan['images']['f366']
    require(baseline.sha(image['path']) == image['sha256'] and Path(image['path']).stat().st_size == image['bytes'], 'candidate_hash')
    return plan


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = load_plan(args.plan, args.plan_sha256)
    if not args.execute:
        print('{"status":"OFFLINE_VALID","hardware_actions":false}')
        return 0
    require(os.environ.get('OM_F366_CONTEXT') and args.output_dir and args.output_dir.is_dir() and args.output_dir.resolve().parent == EVIDENCE_ROOT.resolve(), 'owning_launcher_required')
    return run(plan, args.output_dir)


if __name__ == '__main__':
    raise SystemExit(main())
