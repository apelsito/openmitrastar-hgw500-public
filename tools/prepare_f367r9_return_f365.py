"""Create a file-only R9 recovery plan; no execution or device access."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import ast
import copy
import json

import f367r9_return_f365 as recovery

ROOT = recovery.ROOT
ORIGINAL = ROOT/'outputs/preflight/f367r9-campaign-20260922T224746Z/plan.json'
FAILED = Path('/workspace/OpenMitraStar/f367-campaign/f367r9-campaign-20260922T224919Z-91a7595c/result.json')


def dependency_files(seeds):
    """Freeze imported local modules; never walk toolchains/rootfs trees."""
    result, todo = set(), list(seeds)
    while todo:
        file = Path(todo.pop()).resolve()
        if file in result:
            continue
        result.add(file)
        if file.suffix != '.py':
            continue
        for node in ast.walk(ast.parse(file.read_text(encoding='utf-8-sig'))):
            names = ([x.name.split('.')[0] for x in node.names] if isinstance(node, ast.Import)
                     else [node.module.split('.')[0]] if isinstance(node, ast.ImportFrom) and node.module else [])
            for name in names:
                local = ROOT/'tools'/(name+'.py')
                if local.is_file():
                    todo.append(local)
    return result


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--fault-test-result', type=Path, required=True)
    parser.add_argument('--quarantine-test-result', type=Path, required=True)
    args = parser.parse_args()
    recovery.require(recovery.sha(ORIGINAL) == '178f62662d01d20388f5e029bd54e452f45a84ce67829b4d0d5eecb1d46f13fa', 'original_plan_hash')
    previous = recovery.read(ORIGINAL)
    fields = ('store', 'protected', 'proofs', 'boot_acceptance', 'thermal_default', 'write_target',
              'offset', 'erase_bytes', 'erase_end_exclusive', 'slot_bytes', 'store_offset', 'store_bytes',
              'erased_prefix_crc32', 'bootargs', 'known_hosts', 'uart_pnp_device_id', 'physical_lock_dir',
              'network', 'images')
    plan = {name: copy.deepcopy(previous[name]) for name in fields}
    parent = Path(plan['physical_lock_dir'])/'owner.json'
    owner = recovery.read(parent)
    recovery.require(owner['pid'] == 38908 and owner['process_start_ticks'] == 639257141569704476, 'retained_owner')
    plan.update(schema=recovery.PLAN_SCHEMA, status='PASS_OFFLINE_RETURN_PLAN',
                original_plan=dict(path=str(ORIGINAL), sha256=recovery.sha(ORIGINAL)),
                failed_result=dict(path=str(FAILED), sha256=recovery.FAILED_SHA),
                parent_lease=dict(path=str(parent), sha256=recovery.sha(parent), pid=owner['pid'], process_start_ticks=owner['process_start_ticks']),
                old_boot_id=recovery.OLD_BOOT, evidence_root=str(recovery.EVIDENCE_ROOT),
                max_attempts=1, context_ttl_seconds=3600, outer_timeout_seconds=3000,
                watchdog_arm_allowed=False, radio_tests_allowed=False, sensor_activation_allowed=False,
                boot_environment_persistence_allowed=False, store_write_allowed=False, serial_reset_fallback_allowed=False,
                hardware_actions=False, physical_acceptance='NOT_RUN',
                reset_policy='One qualified SSH reboot from fresh pinned quiescent R9; no serial BREAK or reset fallback',
                failure_policy='Retain parent quarantine and attempt claim; no automatic second write or image/epoch substitution',
                success_policy='Exact F365 readback/new boot/platform27/journal/Ethernet/inactive watchdog/containment before retirement',
                retention_policy='Both original mutexes held while closing own child and moving intact quarantine to checked sibling')
    source_names = ('f367r9_return_f365.py', 'prepare_f367r9_return_f365.py', 'test_f367r9_return_f365.py',
                    'f367_uart_capture_r2.py', 'run_f367r9_return_f365.ps1', 'f367r9_return_context.ps1',
                    'assert_f367r9_return_context.ps1', 'test_f367r9_quarantine_retirement.ps1',
                    'f319_uart_guard.ps1', 'f319_recovery_guard.ps1', 'f321_ssh_guard.ps1',
                    'f321_mtd4_runtime.ps1', 'f321_process_job.cs', 'f321_native_job_launcher.ps1',
                    'f325_existing_firewall.ps1', 'f336_host_network.ps1', 'f366r3_source_freeze.ps1')
    files = dependency_files(ROOT/'tools'/name for name in source_names)
    files.update({ORIGINAL, FAILED, Path(plan['known_hosts']), Path(plan['store']['path']), Path(plan['protected']['manifest'])})
    for item in plan['protected']['parts']:
        files.add(Path(item['path']))
    for image in plan['images'].values():
        files.update({Path(image['path']), Path(image['directory'])/'manifest.json', Path(image['known_hosts_path'])})
    files.add(Path(plan['network']['python_executable']))
    files.add(Path(plan['network']['existing_permission']['path']))
    for item in plan['proofs']:
        files.add(Path(item['path']))
    plan['recovery_tests'] = []
    for test, status in ((args.fault_test_result, 'PASS_R9_RETURN_FAULT_TESTS'),
                         (args.quarantine_test_result, 'PASS_R9_SYNTHETIC_QUARANTINE_RETIREMENT')):
        test = test.resolve()
        row = recovery.read(test)
        recovery.require(row['status'] == status and row['hardware_actions'] is False, 'return_tests_not_passed')
        for source, digest in row['source_pins'].items():
            recovery.require(recovery.sha(source) == digest, 'tested_source_drift')
            files.add(Path(source))
        files.add(test)
        plan['recovery_tests'].append(dict(path=str(test), sha256=recovery.sha(test), status=status))
    # Parent owner.json is separately pinned and held, not source-frozen: its
    # complete directory is archived under the two still-held mutexes on PASS.
    plan['sources'] = {str(file.resolve()): recovery.sha(file) for file in sorted(files)}
    out = (args.output_dir or ROOT/'outputs/preflight'/('r9-return-f365-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))).resolve()
    recovery.safe_path(out, exists=False)
    recovery.require(not out.exists() and out.parent == ROOT/'outputs/preflight', 'immutable_scoped_output')
    out.mkdir()
    path = out/'plan.json'
    recovery.save_new(path, plan)
    digest = recovery.sha(path)
    recovery.load_plan(path, digest)
    result = dict(schema='openmitrastar.r9-return-preparation/v1', status='PASS_OFFLINE_RETURN_PLAN',
                  plan=str(path), plan_sha256=digest, source_pins=len(plan['sources']), hardware_actions=False,
                  f365_sha256=recovery.F365_SHA, f365_bytes=5382144, f365_fullslot_crc32='118901d4',
                  pending='Fresh root-observed R9 boot ID, live quiescence, pinned SSH/UART nonce and physical return are unrun')
    recovery.save_new(out/'result.json', result)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
