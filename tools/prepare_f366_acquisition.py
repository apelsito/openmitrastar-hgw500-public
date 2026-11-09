"""Seal real F366 inputs for install/acquisition/return; never execute hardware."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys

import f365_install_contract as c
import f365_install_executor as previous
import f366_acquisition_executor as executor
from f366_dfs_campaign import strict_object
from bootbase_contract_emulator import validate_bootbase_slot, image_to_dict


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=strict_object)


def build_candidate(result_path, prior):
    result = read(result_path)
    c.require(result['status'].startswith('PASS_OFFLINE_') and result['reproducible'] is True and result['bootbase'] == 'PASS' and result['slot_fit'] is True, 'f366_offline_qualification')
    diagnostic = result['diagnostic']
    c.require(diagnostic['callback_authority'] == 0 and diagnostic['diagnostic_channel'] == 36 and diagnostic['bandwidth'] == 80 and diagnostic['watchdog_session_ms'] == 180000 and diagnostic['five_ghz_boot_pending'] is True, 'f366_diagnostic_boundary')
    fallback = prior['images']['f365']
    recovery = result['recovery']
    c.require(recovery['sha256'] == fallback['sha256'] and recovery['bytes'] == fallback['bytes'] and recovery['version'] == fallback['version'] and recovery['kernel_build'] == fallback['kernel_build'], 'f366_parent_not_current_f365')
    artifact = result['artifact']
    path = Path(artifact['path']).resolve(strict=True)
    manifest = path.parent/'manifest.json'
    data = path.read_bytes()
    c.require(len(data) == artifact['bytes'] and c.sha(path) == artifact['sha256'] and c.sha(manifest) == result['manifest_sha256'], 'f366_image_binding')
    manifest_data = read(manifest)
    c.require(manifest_data['source']['image_sha256'] == fallback['sha256'] and manifest_data['native_dfs']['release_qualified'] == 0, 'f366_manifest_parent_and_authority')
    c.require(manifest_data['watchdog']['supervisor_sha256'] == executor.SUPERVISOR_SHA, 'f366_manifest_supervisor')
    c.require(0 < len(data) < c.PREFIX, 'f366_slot_fit')
    contract = image_to_dict(validate_bootbase_slot('f366', data, c.SLOT))
    c.require(contract['accepted_by_contract'] and contract['header']['load'] == '0x8493a000' and contract['header']['entry'] == '0x8493e000', 'f366_bootbase_contract')
    store = Path(prior['store']['path']).read_bytes()
    prefix = data+b'\xff'*(c.PREFIX-len(data))
    full = prefix+store
    c.require(c.crc(full) == result['full_slot']['crc32'] and hashlib.sha256(full).hexdigest() == result['full_slot']['sha256'], 'f366_fullslot_store_binding')
    known = path.parent/'known_hosts.f366'
    c.require(known.is_file() and known.read_bytes() == Path(fallback['known_hosts_path']).read_bytes(), 'f366_pinned_ssh_identity')
    c.require(re.fullmatch('[a-zA-Z0-9._-]+', result['product_version']) and '-f366-' in result['product_version'], 'f366_version')
    runtime = dict(result['runtime_bindings'])
    runtime['/usr/sbin/om-watchdog-supervisor'] = manifest_data['watchdog']['supervisor_sha256']
    required = {'/usr/sbin/om-f366-diagnostic', '/usr/sbin/om-f366-stage', '/usr/sbin/om-f366-status', '/usr/sbin/om-radio5-start', '/usr/sbin/om-radar-engine-f366', '/usr/sbin/om-watchdog-supervisor'}
    c.require(isinstance(runtime, dict) and required <= set(runtime) and all(isinstance(value, str) and len(value) == 64 and all(ch in '0123456789abcdef' for ch in value) for value in runtime.values()), 'f366_runtime_bindings')
    c.require(any(path.endswith('/qtn_radar_f366.ko') for path in runtime) and any(path.endswith('/qdrv.ko') for path in runtime), 'f366_native_module_bindings')
    c.require(runtime['/usr/sbin/om-watchdog-supervisor'] == executor.SUPERVISOR_SHA, 'f366_watchdog_changed')
    candidate = dict(directory=str(path.parent), base=path.name.removesuffix('.webformat.bin'), path=str(path), bytes=len(data), sha256=artifact['sha256'], manifest_sha256=result['manifest_sha256'], version=result['product_version'], known_hosts='known_hosts.f366', known_hosts_path=str(known), kernel_build=fallback['kernel_build'], marker=fallback['marker'], crc32=c.crc(data), prefix_crc32=c.crc(prefix), full_slot_crc32=c.crc(full), full_slot_sha256=hashlib.sha256(full).hexdigest(), preserved_store_sha256=prior['store']['sha256'], full_slot_scope='firmware prefix plus exact seq2 store')
    return candidate, runtime, result


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--candidate-result', type=Path, required=True)
    parser.add_argument('--baseline-install', type=Path, required=True)
    parser.add_argument('--baseline-plan', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args()
    c.require(shutil.disk_usage('C:/').free > 500*1024*1024 and shutil.disk_usage('D:/').free > 500*1024*1024, 'disk_admission_floor')
    prior = previous.load_plan(args.baseline_plan, c.sha(args.baseline_plan))
    installed = read(args.baseline_install)
    c.require(installed['status'] == 'PASS_F365_PRESERVED_JOURNAL' and installed['writer']['image'] == prior['images']['f365']['sha256'] and installed['writer']['full_slot_crc32'] == prior['images']['f365']['full_slot_crc32'] and installed['writer']['byte_compare'] is True and installed['store_after']['sha256'] == prior['store']['sha256'] and installed['containment_confirmed'] is True and installed['retain_lease_required'] is False, 'real_f365_acceptance_required')
    candidate, runtime, qualification = build_candidate(args.candidate_result, prior)
    out = args.output_dir or c.ROOT/'outputs/preflight'/('f366-acquisition-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out = out.resolve()
    c.require(not out.exists(), 'immutable_output_already_exists')
    out.mkdir(parents=True, exist_ok=False)
    executor.EVIDENCE_ROOT.mkdir(parents=True, exist_ok=True)
    for item in (executor.EVIDENCE_ROOT, *executor.EVIDENCE_ROOT.parents):
        c.require(not item.is_symlink() and not getattr(item, 'is_junction', lambda: False)(), 'evidence_reparse')
    files = {Path(path).resolve() for path in prior['sources']}
    files.update(Path(module.__file__).resolve() for module in sys.modules.values() if getattr(module, '__file__', None) and Path(module.__file__).resolve().is_relative_to(c.ROOT/'tools'))
    files.update(c.ROOT/'tools'/name for name in ('prepare_f366_acquisition.py', 'f366_acquisition_executor.py', 'f366_dfs_campaign.py', 'test_f366_dfs_campaign.py', 'test_f366_acquisition_executor.py', 'test_f366_context.ps1', 'run_f366_acquisition.py', 'run_f366_acquisition.ps1', 'f366_hardware_context.ps1', 'assert_f366_context.ps1'))
    files.update([args.candidate_result.resolve(), args.baseline_install.resolve(), args.baseline_plan.resolve(), Path(candidate['path']), Path(candidate['directory'])/'manifest.json', Path(candidate['known_hosts_path'])])
    # Candidate qualification and its manifest bind the offline builder evidence;
    # include declared files when supplied, without scanning any rootfs/toolchain.
    for path, digest in qualification.get('sources', {}).items():
        c.require(c.sha(path) == digest, 'f366_qualification_source_drift')
        files.add(Path(path).resolve())
    manifest = read(Path(candidate['directory'])/'manifest.json')
    for path, digest in manifest['source']['inputs'].items():
        c.require(c.sha(path) == digest, 'f366_manifest_input_drift')
        files.add(Path(path).resolve())
    pins = {str(path): c.sha(path) for path in sorted(files)}
    test_outputs = []
    for filename in ('test_f366_dfs_campaign.py', 'test_f366_acquisition_executor.py'):
        test = subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tools', '-p', filename, '-v'], cwd=c.ROOT, capture_output=True, timeout=120)
        test_outputs.append((test.stdout, test.stderr))
        (out/(filename+'.stdout')).write_bytes(test.stdout)
        (out/(filename+'.stderr')).write_bytes(test.stderr)
        c.require(test.returncode == 0, 'f366_adaptation_tests_failed_'+filename)
    (out/'tests.stdout').write_bytes(b''.join(row[0] for row in test_outputs))
    (out/'tests.stderr').write_bytes(b''.join(row[1] for row in test_outputs))
    context_test = subprocess.run([executor.desktop_ps.executable(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass', '-File', str(c.ROOT/'tools/test_f366_context.ps1'), '-ResultPath', str(out/'context-tests.json')], env=executor.desktop_ps.environment(), capture_output=True, timeout=60)
    (out/'context.stdout').write_bytes(context_test.stdout)
    (out/'context.stderr').write_bytes(context_test.stderr)
    c.require(context_test.returncode == 0 and not context_test.stderr, 'f366_context_tests_failed')
    c.require(read(out/'context-tests.json') == dict(passed=True, tests=4, hardware_actions=False), 'context_test_result')
    c.require(all(c.sha(path) == digest for path, digest in pins.items()), 'source_drift_during_tests')
    plan = {key: value for key, value in prior.items() if key not in {'images', 'sources', 'tests', 'success_policy', 'failure_policy', 'limits', 'baseline_proofs'}}
    plan.update(schema='openmitrastar.f366-acquisition-plan/v1', status='PASS_OFFLINE_REVIEWED_EXECUTOR', images={'f366': candidate, 'f365': prior['images']['f365']}, sources=pins,
                runtime_bindings=runtime, evidence_root=str(executor.EVIDENCE_ROOT.resolve()), known_hosts=prior['images']['f365']['known_hosts_path'],
                callback_authority=0, diagnostic_channel=36, diagnostic_bandwidth=80, watchdog_session_ms=180000, always_restore_f365=True,
                watchdog_arm_allowed=True, radio_tests_allowed=True, wifi_client_tests=False, sensor_activation_allowed=False,
                baseline_proofs={'path': str(args.baseline_install.resolve()), 'sha256': c.sha(args.baseline_install)}, candidate_qualification={'path': str(args.candidate_result.resolve()), 'sha256': c.sha(args.candidate_result)},
                tests={'adaptation': {'stdout': str(out/'tests.stdout'), 'stderr': str(out/'tests.stderr'), 'sha256': c.sha(out/'tests.stderr'), 'scope': 'offline host recovery and evidence parser only'}},
                success_policy='Exactly one F366 native acquisition on non-DFS36/80, 20 persisted observations, jobs progress, callback0/errors0, watchdog reset then exact F365 restored and platform27/store/config/Ethernet/thermal-default verified.',
                failure_policy='Persist local failure details before return; no provider unload. Let the absolute180s supervisor reset, then one reviewed serial recovery only if needed. Restore exact F365 once; any ambiguous flash command stops automatic writes.',
                limits=['Diagnostic acquisition is not RF radar, CAC, CSA/NOP, client or traffic acceptance.', 'F366 boot acceptance intentionally requires 5GHz pending; existing platform27 is required again after F365 return.', 'Hardware watchdog reset is distinct from guaranteed recovery of CPU/bus halt.'])
    path = out/'plan.json'
    path.write_text(json.dumps(plan, indent=2)+'\n', encoding='ascii')
    digest = c.sha(path)
    executor.load_plan(path, digest)
    result = dict(status='PASS_OFFLINE_F366_ACQUISITION_EXECUTOR', plan=str(path), plan_sha256=digest, source_pins=len(pins), hardware_actions=False, candidate_sha256=candidate['sha256'], fallback_sha256=prior['images']['f365']['sha256'])
    (out/'result.json').write_text(json.dumps(result, indent=2)+'\n', encoding='ascii')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
