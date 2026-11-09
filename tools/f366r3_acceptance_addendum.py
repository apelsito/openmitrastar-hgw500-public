"""One file-only acceptance addendum for the exact completed F366r3 campaign.

Preserves the original FAIL. Replaces only a marker-order inference, after
proving actual setter-before-API order in the helper extracted from the sealed
image and its live RAM guard. Never flashes, connects, or edits prior results.
"""
from pathlib import Path
import argparse
import hashlib
import json
import re
import subprocess

import f366r3_native_evidence as parser

IMAGE_SHA = 'ca66ddf07a6a1ef4470a77ca85c4151354e9d7dd831abc7e5f02c1a53a8b5d2d'
FALLBACK_SHA = '43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355'
MANIFEST_SHA = '166a519028c5e2463b12de7e8599f628ae9bf56b86da843691c6eba421027a2f'
FALSE_NEGATIVE = 'radar_filter_not_before_enable'
HELPER = 'usr/libexec/openmitrastar/om-radio5-start-f366-native'


def require(value, reason):
    if not value:
        raise ValueError(reason)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def image_order_proof(qualification):
    q = read(qualification)
    require(q['schema'] == 'openmitrastar.f366r3-native-start-image/v1' and q['status'] == 'PASS_OFFLINE_F366R3_NATIVE_START_IMAGE', 'qualification_scope')
    image = Path(q['artifact']['path'])
    require(q['artifact']['sha256'] == IMAGE_SHA == sha(image) and image.stat().st_size == 5451776, 'exact_image')
    manifest_path = image.parent/'manifest.json'
    require(q['manifest_sha256'] == MANIFEST_SHA == sha(manifest_path), 'manifest_binding')
    manifest = read(manifest_path)
    rootfs = image.parent/manifest['artifacts']['rootfs_squashfs']['file']
    require(sha(rootfs) == manifest['artifacts']['rootfs_squashfs']['sha256'], 'rootfs_binding')
    linux = '/mnt/'+rootfs.drive[0].lower()+rootfs.as_posix()[2:]
    process = subprocess.run(['wsl.exe', '-d', 'podman-mem9-tidb', '-u', 'root', '-e', 'unsquashfs', '-cat', linux, HELPER], capture_output=True, timeout=30)
    require(process.returncode == 0, 'local_helper_extraction')
    digest = hashlib.sha256(process.stdout).hexdigest()
    require(digest == q['runtime_bindings']['/'+HELPER] == manifest['runtime_bindings']['/'+HELPER], 'actual_helper_hash')
    text = process.stdout.decode('ascii')
    needles = {
        'attempt_marker': "printf 'OMF366_NATIVE_START_ATTEMPT command=radar-enable-eu authority=0",
        'setter': '/usr/sbin/iwpriv-qtn wifi0 radar_bw 80 >"$state/radar-bw-set.log" 2>&1 || refuse f366-native-radar-bw-set',
        'filter_marker': "printf 'OMF366_NATIVE_FILTER_CONFIG radar_bw=80 setter=ieee80211-param-235 authority=0",
        'effective_api_call': "control_set 'radar enable eu' native-radar-enable",
    }
    require(all(text.count(needle) == 1 for needle in needles.values()), 'unique_program_statements')
    positions = {key: text.index(value) for key, value in needles.items()}
    require(positions['attempt_marker'] < positions['setter'] < positions['filter_marker'] < positions['effective_api_call'], 'setter_before_actual_api_not_proven')
    require(re.search(r'\nrefuse\(\)\n\{[\s\S]*?\n\s*exit [1-9][0-9]*\n\}', text), 'setter_failure_not_terminal')
    lines = {key: dict(line=text[:positions[key]].count('\n')+1, text=value) for key, value in needles.items()}
    return dict(helper_sha256=digest, installed_helper_path='/'+HELPER, statement_order=lines,
                setter_before_effective_api=True, setter_failure_is_terminal=True,
                attempt_marker_is_api_timestamp=False,
                explanation='START_ATTEMPT announces the operation before preparation. The successful setter and FILTER_CONFIG precede the actual control_set radar-enable call.'), [Path(qualification), image, manifest_path, rootfs]


def build(run_dir, qualification, plan_path):
    run_dir = Path(run_dir)
    result_path = run_dir/'result.json'
    require(result_path.is_file(), 'campaign_not_closed')
    original = read(result_path)
    plan = read(plan_path)
    require(plan['candidate_revision'] == 'f366r3' and plan['images']['f366']['sha256'] == IMAGE_SHA, 'plan_candidate')
    require(original['schema'] == 'openmitrastar.f366-acquisition-result/v1' and original['status'] == 'FAIL_F366_WITH_F365_RETURN' and original['error'] == 'diagnostic_evidence_failed', 'original_outcome_scope')
    require(original['diagnostic']['failures'] == [FALSE_NEGATIVE], 'additional_failures_present')
    require(original['writer']['image'] == IMAGE_SHA and original['writer']['byte_compare'] is True and original['writer']['full_slot_crc32'] == '94ddd37e', 'physical_candidate_write')
    require(original['restore_writer']['image'] == FALLBACK_SHA and original['restore_writer']['byte_compare'] is True and original['restore_writer']['full_slot_crc32'] == '118901d4', 'physical_f365_return_write')
    require(original['baseline_returned'] is True and original['watchdog_reset_observed'] is True and original['diagnostic_reset_signatures'] >= 1 and not original.get('software_recovery'), 'reset_and_return_not_observed')
    require(original['containment_confirmed'] is True and original['retain_lease_required'] is False and original['flash_command_in_flight'] is False and original['watchdog_may_remain_armed'] is False, 'campaign_not_safely_closed')
    require(original['returned_identity']['boot_id'] != original['f366_identity']['boot_id'], 'return_boot_not_new')
    require(original['returned_store']['sha256'] == plan['store']['sha256'] and original['returned_configuration']['sequence'] == 2 and original['returned_configuration']['active_sha256'] == plan['boot_acceptance']['payload_sha256'], 'store_or_configuration_changed')
    platform_path = Path(original['return_platform']['result'])
    require(sha(platform_path) == original['return_platform']['sha256'], 'return_platform_hash')
    platform = read(platform_path)
    require(platform['status'] == 'PASS' and len(platform['checks']) == 27 and all(value is True for value in platform['checks'].values()), 'return_platform_not_pass')
    require(original['returned_thermal']['enabled'] is False and original['returned_thermal']['activation_attempted'] is False, 'thermal_default_changed')
    for phase in ('writer', 'restore_writer'):
        require(original[phase]['prewrite']['protected'] == original[phase]['postwrite']['protected'] == original['protected_before'], 'protected_partition_changed')
    transcript_path = run_dir/'diagnostic-transcript.log'
    event_path = run_dir/'diagnostic-events-r2.jsonl'
    require(sha(transcript_path) == original['diagnostic']['transcript_sha256'] and sha(event_path) == original['diagnostic']['capture']['sha256'], 'physical_transcript_hash')
    transcript = transcript_path.read_text(encoding='ascii')
    events = [json.loads(line) for line in event_path.read_text(encoding='ascii').splitlines()]
    reviewed = parser.review_transcript(transcript, events)
    require(reviewed['failures'] == [FALSE_NEGATIVE], 'replayed_result_changed')
    require(original['diagnostic']['transport_exit_code'] == 0 and original['diagnostic']['watchdog_arm_marker'] == 1 and reviewed['sample_count'] == 20 and reviewed['observed_jobs_delta'] > 0, 'native_execution_not_proven')
    proof, paths = image_order_proof(qualification)
    require(original['runtime_hashes']['status'] == 'PASS' and original['runtime_hashes']['count'] == 16, 'live_runtime_hashes_not_pass')
    require(reviewed['native_guard_snapshot']['reason'] == 'allow' and reviewed['native_guard_snapshot']['radar_bw'] == '80' and reviewed['native_guard_snapshot']['reads'] == 'ram-only', 'live_pre_api_guard_not_pass')
    samples = [json.loads(line.split(' json=', 1)[1]) for line in transcript.splitlines() if line.startswith('OMF366_STATUS index=')]
    require(all(row['hardware_ready'] == row['started'] == row['postfilter_applied'] == 1 and row['ready'] == row['callbacks'] == 0 for row in samples), 'diagnostic_authority_boundary')
    complete = re.findall(r'^OMF366_DIAGNOSTIC_COMPLETE observations=20 jobs_delta=([0-9]+) authority=0 hardware_quiesced=0 reboot_required=1$', transcript, re.M)
    require(len(complete) == 1 and int(complete[0]) > 0, 'completion_marker')
    paths += [result_path, Path(plan_path), platform_path, transcript_path, event_path]
    return dict(schema='openmitrastar.f366r3-acquisition-acceptance-addendum/v1', status='PASS_F366R3_NATIVE_ACQUISITION_WITH_F365_RETURN_ADDENDUM',
                original_result_status=original['status'], original_result_unchanged=True,
                corrected_false_negative=FALSE_NEGATIVE, all_other_gates_unchanged=True,
                exact_candidate_sha256=IMAGE_SHA, exact_fallback_sha256=FALLBACK_SHA,
                program_order_proof=proof, native_guard=reviewed['native_guard_snapshot'],
                samples=20, first_jobs_completed=samples[0]['jobs_completed'], last_jobs_completed=samples[-1]['jobs_completed'], observed_jobs_delta=reviewed['observed_jobs_delta'], controller_jobs_delta=int(complete[0]),
                hardware_ready=1, started=1, ready=0, callbacks=0, postfilter_applied=1,
                ready_zero_explanation='F366 compiles F338_RELEASE_QUALIFIED=0 and loads authoritative_enable=0; provider ready also requires callback authority. Hardware acquisition can run with hardware_ready=1 while DFS authority remains closed.',
                watchdog_reset_observed=original['watchdog_reset_observed'], reset_cause_attested=False,
                candidate_boot_id=original['f366_identity']['boot_id'], returned_boot_id=original['returned_identity']['boot_id'],
                f365_return_platform_checks=27, store_sha256=original['returned_store']['sha256'], containment_confirmed=True,
                dfs_cac_radar_nop_pass=False, real_rf_radar_detection_pass=False, client_traffic_pass=False, release_pass=False,
                new_hardware_actions=False, new_flash_required_for_this_correction=False,
                evidence={str(path.resolve()): sha(path) for path in paths}, addendum_source_sha256=sha(__file__))


def main():
    parser_cli = argparse.ArgumentParser(allow_abbrev=False)
    parser_cli.add_argument('--run-dir', type=Path, required=True)
    parser_cli.add_argument('--qualification', type=Path, required=True)
    parser_cli.add_argument('--plan', type=Path, required=True)
    parser_cli.add_argument('--output-dir', type=Path, required=True)
    args = parser_cli.parse_args()
    require(not args.output_dir.exists(), 'immutable_output_required')
    result = build(args.run_dir, args.qualification, args.plan)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    path = args.output_dir/'result.json'
    path.write_text(json.dumps(result, indent=2)+'\n', encoding='ascii')
    print(json.dumps(dict(result=str(path.resolve()), sha256=sha(path), status=result['status'], new_hardware_actions=False)))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
