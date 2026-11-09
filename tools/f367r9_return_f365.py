"""One bounded R9 -> exact F365 recovery. Import/default CLI are offline.

Execution is available only under run_f367r9_return_f365.ps1's retained-parent
child lease. No campaign, radio activation, watchdog arm or serial reset retry.
The original F365 writer owns all erase/write/readback/Bootbase operations.
"""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import os
import re
import stat
import subprocess
import time

import f365_install_executor as writer
import f365_install_contract as baseline
import f346_powershell as desktop_ps
from bootbase_contract_emulator import validate_bootbase_slot, image_to_dict

ROOT = Path(__file__).resolve().parent.parent
EVIDENCE_ROOT = Path('/workspace/OpenMitraStar/f367-recovery')
PLAN_SCHEMA = 'openmitrastar.f367r9-return-f365-plan/v1'
CONTEXT_SCHEMA = 'openmitrastar.f367r9-return-f365-context/v1'
FAILED_SHA = '2ed7d2c75142a9ca3176302d4cb14c11d52d76dec056d6295a8ce7fd131b38d3'
OLD_BOOT = 'cf18e917-7a46-4a60-a352-eef2572adff7'
R9_SHA = '6bf5a08edd5b18adf1597efbd5367d5ad439363c7f7a13a035efc615b4cee440'
F365_SHA = '43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355'
R9_VERSION = 'lyoko-foundation-6.11.8-f367r9-transition-observation-device'
F365_VERSION = 'lyoko-foundation-6.9.13-f365-temperature-data-device'
Failure, require = writer.Failure, writer.require
sha = baseline.sha


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'duplicate_json_field')
        result[key] = value
    return result


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'), object_pairs_hook=unique)


def safe_path(path, *, exists=True):
    """Reject aliases, traversal, device/UNC paths and every reparse ancestor."""
    p = Path(path)
    require(p.is_absolute() and p.drive.lower() in ('c:', 'd:'), 'absolute_local_path_required')
    require('..' not in p.parts and not str(p).startswith('\\\\'), 'path_traversal')
    require(str(p.resolve()).lower() == str(p).lower(), 'path_alias')
    for item in (p, *p.parents):
        if item.exists():
            require(not item.stat(follow_symlinks=False).st_file_attributes & stat.FILE_ATTRIBUTE_REPARSE_POINT,
                    'path_reparse')
    if exists:
        require(p.exists(), 'path_missing')
    return p


def validate_failed(plan):
    ref = plan['failed_result']
    require(ref['sha256'] == FAILED_SHA and sha(ref['path']) == FAILED_SHA, 'r9_failed_result_binding')
    r = read(ref['path'])
    require(r['status'] == 'FAILED_RECOVERY_UNPROVEN_NO_RETRY' and r['recovery_error'] == 'uart_window_overflow', 'r9_failure_scope')
    require(r['flash_command_in_flight'] is False and r['containment_confirmed'] is True
            and r['children_contained'] is True and r['uart']['port_closed'] is True
            and r['uart']['reader_stopped'] is True and r['serial_recovery'] == {}, 'r9_old_operation_not_contained')
    require(r['writer']['image'] == R9_SHA and r['writer']['byte_compare'] is True
            and r['writer']['full_slot_crc32'] == '4fa4640f', 'r9_installed_artifact')
    return r


def validate_scope(plan):
    require(plan['schema'] == PLAN_SCHEMA and plan['status'] == 'PASS_OFFLINE_RETURN_PLAN', 'return_plan_scope')
    require(plan['write_target'] == 'mtd4/linux_live' and plan['offset'] == baseline.LIVE
            and plan['erase_bytes'] == baseline.PREFIX == 0x5e0000
            and plan['erase_end_exclusive'] == baseline.STORE
            and plan['slot_bytes'] == baseline.SLOT, 'prefix_only_scope')
    for field in ('watchdog_arm_allowed', 'radio_tests_allowed', 'sensor_activation_allowed',
                  'boot_environment_persistence_allowed', 'store_write_allowed', 'serial_reset_fallback_allowed'):
        require(plan[field] is False, 'forbidden_action_' + field)
    require(plan['max_attempts'] == 1 and plan['old_boot_id'] == OLD_BOOT
            and plan['context_ttl_seconds'] == 3600 and plan['outer_timeout_seconds'] == 3000, 'bounded_recovery_scope')
    require(set(plan['images']) == {'f367', 'f365'}, 'image_set')
    for name, digest, length, version, crc in (
        ('f367', R9_SHA, 5468160, R9_VERSION, '4fa4640f'),
        ('f365', F365_SHA, 5382144, F365_VERSION, '118901d4')):
        image = plan['images'][name]
        require((image['sha256'], image['bytes'], image['version'], image['kernel_build'], image['full_slot_crc32'])
                == (digest, length, version, '#358', crc), 'exact_image_' + name)
    require(plan['known_hosts'] == plan['images']['f365']['known_hosts_path'], 'pinned_ssh')
    require(plan['store']['sha256'] == 'fcbeb5ab9f1fde273632a0f1a2f0a5d8b1304aa361439c24d1fe8e29cbb1c873'
            and plan['store']['crc32'] == '5d2ee646' and plan['store']['bytes'] == baseline.STORE_BYTES, 'store_scope')
    require([p['partition'] for p in plan['protected']['parts']] == ['mtd0', 'mtd1', 'mtd2', 'mtd3', 'mtd5'], 'protected_scope')
    require(plan['bootargs'] == baseline.BOOTARGS and Path(plan['evidence_root']) == EVIDENCE_ROOT, 'boot_environment_scope')
    require(plan['parent_lease']['pid'] == 38908 and plan['parent_lease']['process_start_ticks'] == 639257141569704476
            and Path(plan['physical_lock_dir']) == ROOT/'outputs/locks/f301-physical-radio.lock', 'parent_lease_scope')


def load_plan(path, digest):
    safe_path(path)
    require(sha(path) == digest, 'plan_hash')
    plan = read(path)
    validate_scope(plan)
    validate_failed(plan)
    for file, expected in plan['sources'].items():
        safe_path(file)
        require(sha(file) == expected, 'source_drift')
    store = safe_path(plan['store']['path']).read_bytes()
    require(hashlib.sha256(store).hexdigest() == plan['store']['sha256'], 'store_backup_hash')
    for name, image in plan['images'].items():
        data = safe_path(image['path']).read_bytes()
        require(len(data) == image['bytes'] and hashlib.sha256(data).hexdigest() == image['sha256'], 'image_hash')
        require(len(data) < baseline.PREFIX, 'image_prefix_fit')
        full = data + b'\xff' * (baseline.PREFIX-len(data)) + store
        require(baseline.crc(data) == image['crc32'] and baseline.crc(full) == image['full_slot_crc32'], 'image_crc')
        require(sha(Path(image['directory'])/'manifest.json') == image['manifest_sha256'], 'image_manifest')
        require(image_to_dict(validate_bootbase_slot(name, data, baseline.SLOT))['accepted_by_contract'], 'bootbase_contract')
    require(safe_path(plan['images']['f367']['known_hosts_path']).read_bytes()
            == safe_path(plan['known_hosts']).read_bytes(), 'ssh_key_changed')
    require(plan['protected'] == baseline.protected_backups(), 'protected_backup_binding')
    original = read(plan['original_plan']['path'])
    require(plan['original_plan']['sha256'] == '178f62662d01d20388f5e029bd54e452f45a84ce67829b4d0d5eecb1d46f13fa'
            and sha(plan['original_plan']['path']) == plan['original_plan']['sha256'], 'original_r9_plan_binding')
    for name in ('f365_install_executor.py', 'f367_uart_capture_r2.py', 'f366r3_reset_observation.py',
                 'f336_wdt_ram_executor.py', 'f319_uart_guard.ps1'):
        source = str((ROOT/'tools'/name).resolve())
        require(plan['sources'][source] == original['sources'][source] == sha(source), 'qualified_writer_capture_changed')
    require([test['status'] for test in plan['recovery_tests']] ==
            ['PASS_R9_RETURN_FAULT_TESTS', 'PASS_R9_SYNTHETIC_QUARANTINE_RETIREMENT'], 'focused_test_scope')
    for test in plan['recovery_tests']:
        require(sha(test['path']) == test['sha256'], 'test_evidence_hash')
        report = read(test['path'])
        require(report['status'] == test['status'] and report['hardware_actions'] is False, 'focused_tests_failed')
        for source, digest in report['source_pins'].items():
            require(plan['sources'][source] == digest == sha(source), 'test_source_binding')
    return plan


def quiescence_command():
    # No runtime mutation, signal, module load/unload, sensor or radio command.
    return r'''set -eu
printf 'boot='; cat /run/openmitrastar/boot-state
for pair in 'qdrv:/sys/module/qdrv' 'provider:/sys/module/qtn_radar_f367' 'provider366:/sys/module/qtn_radar_f366' 'wifi0:/sys/class/net/wifi0' 'owner:/run/openmitrastar/watchdog/owner.lock' 'socket:/run/openmitrastar/watchdog/supervisor.sock'; do
 key=${pair%%:*}; path=${pair#*:}; if [ -e "$path" ]; then printf '%s=1\n' "$key"; else printf '%s=0\n' "$key"; fi
done
active=0
for f in /proc/[0-9]*/comm; do
 [ -r "$f" ] || continue
 IFS= read -r comm < "$f" || continue
 case "$comm" in om-watchdog*|om-f367-keeper*|om-f367-control*|om-radio5-start*|om-radio5-native*) active=$((active+1));; esac
done
printf 'owners=%s\n' "$active"
printf 'sysrq='; cat /proc/sys/kernel/sysrq
printf 'fatal='; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access|VFS: Unable to mount root' || true
'''


def validate_quiescence(raw):
    pairs = [line.split('=', 1) for line in raw.decode('ascii').splitlines()]
    require(all(len(row) == 2 for row in pairs), 'quiescence_response')
    rows = unique(pairs)
    require(set(rows) == {'boot', 'qdrv', 'provider', 'provider366', 'wifi0', 'owner', 'socket', 'owners', 'sysrq', 'fatal'}, 'quiescence_fields')
    require(rows['boot'] == 'ready' and all(rows[k] == '0' for k in ('qdrv', 'provider', 'provider366', 'wifi0', 'owner', 'socket', 'owners', 'fatal')), 'r9_not_quiescent')
    mask = int(rows['sysrq'])
    require(mask == 1 or bool(mask & 128), 'qualified_ssh_reboot_not_enabled')
    return rows


def fresh_epoch(identity, expected):
    require(re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', expected or '') is not None, 'fresh_boot_id_required')
    require(identity['boot_id'] == expected and expected != OLD_BOOT, 'new_r9_epoch_required')
    require(identity['uts'].split()[:1] == ['#358'] and identity['f340'] == 'F340_WATCHDOG_BASELINE'
            and identity['f336'] == '', 'r9_kernel_identity')


class Host(writer.Host):
    def __init__(self, plan, out, admission=False):
        super().__init__(plan, out)
        self.admission = admission

    def _guard(self, network):
        for path, digest in self.plan['sources'].items():
            require(sha(path) == digest, 'source_drift')
        args = [desktop_ps.executable(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(ROOT/'tools/assert_f367r9_return_context.ps1')]
        if network:
            args.append('-CheckNetwork')
        if self.admission:
            args.append('-Admission')
        result = subprocess.run(args, env=desktop_ps.environment(), capture_output=True, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0 and result.stdout.strip() == b'PASS_R9_RETURN_CONTEXT' and not result.stderr

    def admission_proof(self, expected):
        first = self.identity('f367')
        fresh_epoch(first, expected)
        row = dict(identity=first, quiescence=validate_quiescence(self.ssh(quiescence_command())),
                   watchdog=self.watchdog_inactive(), store=self.verify_store(), configuration=self.verify_configuration(),
                   ethernet=self.verify_ethernet(), storage=self.storage_gate())
        fresh_epoch(self.identity('f367'), expected)
        row.update(schema='openmitrastar.f367r9-return-admission/v1', status='PASS_FRESH_R9_QUIESCENT',
                   observed_utc=datetime.now(timezone.utc).isoformat(), read_only=True, uart_opened=False,
                   expected_boot_id=expected)
        return row


def save_new(path, value):
    with Path(path).open('x', encoding='ascii') as stream:
        stream.write(json.dumps(value, indent=2) + '\n')
        stream.flush()
        os.fsync(stream.fileno())


def run(plan, out, expected_boot, *, host_factory=Host, uart_factory=None, server_factory=writer.ScopedTftpProcess):
    if uart_factory is None:
        from f367_uart_capture_r2 import Uart
        uart_factory = Uart
    host = host_factory(plan, out)
    uart = uart_factory(plan, host.guard, out)
    result = dict(schema='openmitrastar.f367r9-return-result/v1', status='FAILED_RETURN_NO_RETRY',
                  write_target='mtd4/linux_live', erase_bytes=baseline.PREFIX, hardware_started=False,
                  radio_tests_performed=False, watchdog_arm_requested=False, serial_reset_attempted=False,
                  flash_command_in_flight=False, f365_return_confirmed=False, retain_lease_required=True)
    try:
        require(host.guard(), 'bound_child_lease_required')
        result['admission'] = host.admission_proof(expected_boot)
        save_new(out/'execution-admission.json', result['admission'])
        result['rollback_reference'] = dict(path=plan['images']['f365']['path'], sha256=F365_SHA, fresh_physical_dump=False)
        # A separate nonce proof was established in this same epoch by the
        # owning launcher. Revalidate again immediately before the single reboot.
        uart.open()
        result['hardware_started'] = True
        fresh_epoch(host.identity('f367'), expected_boot)
        validate_quiescence(host.ssh(quiescence_command()))
        host.watchdog_inactive()
        host.reboot_to_prompt(uart, software_recovery=False)
        require(uart.has_prompt() and not uart.failed, 'fresh_bootbase_missing')
        result['domain_before'] = writer.domain(uart, plan, plan['store']['crc32'])
        result['r9_before_crc32'] = writer.flash_crc(uart, baseline.LIVE, baseline.SLOT, '4fa4640f')
        result['writer'] = writer.write_image(uart, host, plan, plan['images']['f365'], out/'return-f365', plan['store']['crc32'], server_factory)
        result['returned_identity'] = writer.boot_written(uart, host, plan, 'f365', expected_boot)
        result['return_platform'] = host.platform('f365', out/'platform-f365-return')
        result['returned_watchdog'] = host.watchdog_inactive()
        result['returned_store'] = host.verify_store()
        result['returned_configuration'] = host.verify_configuration()
        result['returned_ethernet'] = host.verify_ethernet()
        result['returned_thermal'] = host.verify_thermal_disabled()
        result['f365_return_confirmed'] = True
        result['status'] = 'PASS_R9_EXACT_F365_RETURN'
    except Exception as error:
        result['error'] = str(error) if isinstance(error, Failure) else type(error).__name__
    finally:
        try:
            result['children_contained'] = host.contain() is True
        except Exception:
            result['children_contained'] = False
        try:
            result['uart'] = uart.close()
        except Exception:
            result['uart'] = {}
        result['containment_confirmed'] = (result['children_contained'] and result['uart'].get('reader_stopped') is True
                                           and result['uart'].get('port_closed') is True)
        try:
            result['final_domain_guard'] = host.guard() is True
        except Exception:
            result['final_domain_guard'] = False
        result['flash_command_in_flight'] = uart.write_in_flight
        result['retain_lease_required'] = not (result['f365_return_confirmed'] and result['containment_confirmed']
                                              and result['final_domain_guard'] and not uart.write_in_flight
                                              and not result['uart'].get('reader_error'))
        if result['retain_lease_required']:
            result['status'] = 'FAILED_RETURN_NO_RETRY'
        save_new(out/'result.json', result)
    return result


def main():
    p = argparse.ArgumentParser(allow_abbrev=False)
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--plan-sha256', required=True)
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--fresh-boot-id')
    mode = p.add_mutually_exclusive_group()
    mode.add_argument('--admit', action='store_true')
    mode.add_argument('--execute', action='store_true')
    args = p.parse_args()
    plan = load_plan(args.plan, args.plan_sha256)
    if not (args.admit or args.execute):
        print(json.dumps(dict(status='OFFLINE_VALID_R9_RETURN_F365', hardware_actions=False, f365_sha256=F365_SHA)))
        return 0
    require(os.environ.get('OM_R9_RETURN_CONTEXT') and args.output_dir is not None, 'owning_launcher_required')
    out = safe_path(args.output_dir)
    require(out.parent == EVIDENCE_ROOT and out.is_dir(), 'evidence_scope')
    context = json.loads(os.environ['OM_R9_RETURN_CONTEXT'], object_pairs_hook=unique)
    require(context['initial_boot_id'] == args.fresh_boot_id and context['plan_sha256'] == args.plan_sha256, 'launcher_epoch_binding')
    if args.admit:
        host = Host(plan, out, admission=True)
        try:
            result = host.admission_proof(args.fresh_boot_id)
        finally:
            require(host.contain(), 'admission_children_uncontained')
        save_new(out/'admission.json', result)
    else:
        save_new(out/'execution-claimed.json', dict(plan_sha256=args.plan_sha256, boot_id=args.fresh_boot_id))
        result = run(plan, out, args.fresh_boot_id)
    print(json.dumps(dict(status=result['status'], hardware_actions=not args.admit)))
    return int(result['status'].startswith('FAILED'))


if __name__ == '__main__':
    raise SystemExit(main())
