"""Exact file-only contract/review for the F325 Ethernet parent and writer.

Owner approval is an existing immutable input, never manufactured by a plan.
No native action, firewall change or device connection is performed here.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
import xml.etree.ElementTree as ET

import f325_execution_contract as base
from f325_ethernet_handoff import exact_pair, exact_server, verify_writer_result
from prepare_f325_ethernet_plan import validate_recorded_authorization
import f325_existing_permission_contract as existing_permission


ROOT = base.ROOT
AUTHORIZATION = ROOT / 'outputs/authorizations/f334-executor-20260921T111605Z/network.json'
AUTHORIZATION_SHA = '3e36ac59c12a0ef61d6a0e564be072a91d23b62c98ec28696d5ac2956b32c572'
UART_REVIEW = ROOT / 'outputs/preflight/f334-executor-20260921T111605Z/uart-executor-review.json'
UART_REVIEW_SHA = '324f288fff36109338e6a042cfd6170a76b3768bcc812e99553b8a0e4d77ef19'
EXTRA_FILES = (
    'tools/run_f325_capture.py', 'tools/test_run_f325_capture.py',
    'tools/prepare_f325_ethernet_plan.py', 'tools/f325_scoped_tftp.py',
    'tools/f325_ethernet_ram_gate.py', 'tools/f325_ethernet_handoff.py',
    'tools/f325_ethernet_uart.py', 'tools/f325_ethernet_guard_process.py',
    'tools/f325_ethernet_server_process.py', 'tools/f325_ethernet_native_loader.py',
    'tools/f325_ethernet_load_cli.py', 'tools/f325_ethernet_writer.py',
    'tools/f325_ethernet_execution_contract.py', 'tools/test_f325_ethernet_execution_contract.py',
    'tools/f325_ethernet_runtime.ps1', 'tools/promote_f325_ethernet.ps1',
    'tools/restore_f325_ethernet.ps1', 'tools/test_f325_ethernet_runtime.py',
    'tools/test_f325_ethernet_writer.py', 'tools/test_f325_ethernet_ram_gate.py',
    'tools/test_f325_ethernet_handoff.py', 'tools/test_f325_ethernet_uart.py',
    'tools/test_f325_ethernet_guard_process.py', 'tools/test_f325_ethernet_server_process.py',
    'tools/test_f325_ethernet_native_loader.py', 'tools/test_f325_scoped_tftp.py',
    'tools/test_f325_ethernet_plan.py',
    'tools/f325_existing_firewall.ps1', 'tools/f325_existing_permission_contract.py',
    'tools/test_f325_existing_permission.py',
)
EXECUTOR_FILES = tuple(dict.fromkeys((*base.EXECUTOR_FILES, *EXTRA_FILES)))
REQUIRED_TEST_MODULES = {'test_f325_ethernet_runtime', 'test_f325_ethernet_writer',
                         'test_f325_ethernet_execution_contract', 'test_f325_existing_permission'}
REQUIRED_BEHAVIOR_GATES = {
    'test_capture_campaign_restores_f321_even_when_capture_is_inconclusive',
    'test_failed_capture_restores_once', 'test_failed_planned_recovery_is_not_retried',
    'test_empty_capture_never_claims_radar', 'test_nonempty_capture_is_only_activity',
    'test_ethernet_request_refuses_wrong_ack_review_authority_or_scope_before_effects',
    'test_ethernet_default_entrypoint_has_no_network_firewall_or_hardware_job',
    'test_cycle_orders_host_baseline_lease_binding_firewall_reboot_job_and_writer',
    'test_ambiguous_loader_or_writer_never_starts_automatic_recovery',
    'test_postgate_failure_restores_once_with_same_lease_and_firewall',
    'test_unborrowed_rollback_is_rejected_before_admin_host_or_device_effects',
    'test_failed_f321_restore_never_chains_another_attempt_or_f314',
    'test_cleanup_uncertainty_is_reported_and_blocks_lease_release_or_next_cycle',
    'test_writer_parent_timeout_includes_cleanup_margin',
    'test_complete_preloaded_writer_uses_original_verifier_and_exact_backend_arguments',
    'test_ack_or_preloaded_binding_failure_cannot_open_backend',
    'test_semantic_native_ram_and_server_failures_rejected_even_after_outer_rehash',
    'test_context_change_during_guard_cannot_cross_the_backend_boundary',
    'test_backend_or_proof_failure_never_retries_or_publishes_pass',
    'test_loader_execute_rechecks_context_and_persisted_native_files',
    'test_exact_existing_owner_network_record_is_accepted_without_asking_again',
    'test_existing_permission_cycle_never_requests_admin_or_mutates_rules',
    'test_existing_permission_drift_refuses_before_device_effects',
    'test_existing_permission_cleanup_drift_blocks_success_and_release',
}
PREREQUISITES = (
    ('outputs/preflight/f323-ethernet-preparation-20260911T191417Z/plan/result.json',
     'b3131a572961d8143012295936e31d2cd694199761935c59d381b2e72690559e'),
    ('outputs/preflight/f323-ethernet-handoff-20260911T200026Z/result.json',
     'b5e3c2699bfd6aaa9a100e988d969c64602212d09894ce61d08a648c406767f4'),
    ('outputs/preflight/f323-ethernet-native-20260911T204832Z/result.json',
     '0925bc3364b5b1e9b6257fed97fe602d9c40b27c9a73f534812032cb4b4a009a'),
)


def read_json(path: Path) -> dict:
    def unique(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError('duplicate JSON key')
            value[key] = item
        return value
    value = json.loads(Path(path).read_text(encoding='utf-8'), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError('JSON object required')
    return value


def validate_network_authorization(path: Path, expected_sha: str, *, server_ipv4: str,
                                    interface_index: int) -> dict:
    server_ipv4 = exact_server(server_ipv4)
    if type(interface_index) is not int or interface_index != 18:
        raise ValueError('authorization is bound to Ethernet interface 18')
    if expected_sha != AUTHORIZATION_SHA or base.digest(path) != AUTHORIZATION_SHA:
        raise ValueError('exact recorded owner Ethernet authorization required')
    record = read_json(path)
    expected = {'schema': 'openmitrastar.f325-ethernet-authorization/v1',
        'target_model': 'HGW-500BNA-QCv2 A2', 'target_host': base.HOST,
        'server_ipv4': server_ipv4, 'interface_index': interface_index,
        'candidate_sha256': base.F325['sha256'], 'candidate_bytes': base.F325['bytes'],
        'conditional_recovery_f321_sha256': base.F321['sha256'],
        'bootloader_volatile_parameters': {'ipaddr': base.HOST, 'serverip': server_ipv4},
        'existing_firmware_authorization_sha256': 'a07fd67981a6841d63458315bee455a3df988941b2be7d21f2a53a62bf1e8c39'}
    yes = ('authorized', 'plaintext_private_image_transfer_authorized',
           'temporary_scoped_firewall_authorized', 'volatile_ipaddr_serverip_authorized')
    no = ('saveenv_authorized', 'boot_selection_changes_authorized',
          'host_address_or_route_changes_authorized', 'disable_firewall_authorized',
          'radio_changes_authorized_by_this_record', 'automatic_f314_fallback_authorized')
    if (any(record.get(key) != value for key, value in expected.items())
            or any(record.get(key) is not True for key in yes)
            or any(record.get(key) is not False for key in no)):
        raise ValueError('owner network authorization scope mismatch')
    validate_recorded_authorization()
    return {'path': str(Path(path).resolve()), 'sha256': AUTHORIZATION_SHA,
        'scope': 'exact F325 transfer and conditional F321 restoration, peer/interface-scoped temporary networking'}


def file_bindings() -> list[dict]:
    return [{'path': path, 'sha256': base.digest(ROOT / path)} for path in EXECUTOR_FILES]


def validate_prerequisites() -> list[dict]:
    proofs = []
    for relative, expected in PREREQUISITES:
        path = ROOT / relative
        if base.digest(path) != expected:
            raise ValueError('transport component qualification changed')
        proof = read_json(path)
        test = proof['qualification']
        test_path = path.parent / test['path']
        if base.digest(test_path) != test['sha256']:
            raise ValueError('component test evidence changed')
        tree = ET.parse(test_path)
        cases = tree.findall('.//testcase')
        if len(cases) != test['tests'] or any(tree.findall('.//' + tag) for tag in ('failure','error','skipped')):
            raise ValueError('component tests not all-pass')
        for item in proof['source_files']:
            if base.digest(ROOT / item['path']) != item['sha256']:
                raise ValueError('component source changed since its qualification: ' + item['path'])
        proofs.append({'path': relative, 'sha256': expected})
    return proofs


def qualify_report(path: Path) -> int:
    tree = ET.parse(path)
    cases = tree.findall('.//testcase')
    modules = {part for case in cases for part in (case.get('classname') or '').split('.')}
    names = {(case.get('name') or '').split('[',1)[0] for case in cases}
    if (len(cases) < 30 or tree.findall('.//failure') or tree.findall('.//error')
            or tree.findall('.//skipped') or not REQUIRED_TEST_MODULES.issubset(modules)
            or not REQUIRED_BEHAVIOR_GATES.issubset(names)):
        raise ValueError('full parent/writer/contract qualification is missing or not all-pass')
    return len(cases)


def validate_executor_review(path: Path, expected_sha: str) -> dict:
    if not re.fullmatch(r'[0-9a-f]{64}', expected_sha) or base.digest(path) != expected_sha:
        raise ValueError('exact Ethernet executor review hash required')
    review = read_json(path)
    if (review.get('schema') != 'openmitrastar.f325-ethernet-executor-review/v1'
        or review.get('status') != 'PASS_OFFLINE_ETHERNET_EXECUTOR_REVIEW'
        or review.get('candidate_sha256') != base.F325['sha256']
        or review.get('restore_image_sha256') != base.F321['sha256']
        or review.get('network_authorization_sha256') != AUTHORIZATION_SHA
        or review.get('uart_review_sha256') != UART_REVIEW_SHA
        or review.get('existing_permission_sha256') != existing_permission.PERMISSION_SHA
        or review.get('existing_permission_probe_sha256') != existing_permission.PROBE_SHA
        or review.get('files') != file_bindings()
        or review.get('physical_authorization') is not False
        or review.get('hardware_actions_performed') is not False
        or review.get('radio_actions_authorized') is not False):
        raise ValueError('Ethernet executor review stale or outside exact scope')
    proof = review['qualification']
    if base.digest(Path(proof['path'])) != proof['sha256'] or qualify_report(Path(proof['path'])) != proof['passed']:
        raise ValueError('Ethernet qualification evidence drift')
    base.validate_executor_review(UART_REVIEW, UART_REVIEW_SHA)
    if review.get('prerequisite_qualifications') != validate_prerequisites():
        raise ValueError('transport prerequisites missing from full review')
    return review


def create_review(path: Path, qualification: Path) -> dict:
    base.validate_sealed_inputs()
    base.validate_executor_review(UART_REVIEW, UART_REVIEW_SHA)
    validate_network_authorization(AUTHORIZATION, AUTHORIZATION_SHA,
        server_ipv4='192.168.1.49', interface_index=18)
    existing_permission.validate_permission(existing_permission.PERMISSION, existing_permission.PERMISSION_SHA,
        python_executable=existing_permission.PROGRAM)
    for direction in ('promote', 'rollback'):
        base.generic_preflight(*exact_pair(direction))
    count = qualify_report(qualification)
    review = {'schema': 'openmitrastar.f325-ethernet-executor-review/v1',
        'status': 'PASS_OFFLINE_ETHERNET_EXECUTOR_REVIEW',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'candidate_sha256': base.F325['sha256'], 'restore_image_sha256': base.F321['sha256'],
        'network_authorization_sha256': AUTHORIZATION_SHA, 'uart_review_sha256': UART_REVIEW_SHA,
        'existing_permission_sha256': existing_permission.PERMISSION_SHA,
        'existing_permission_probe_sha256': existing_permission.PROBE_SHA,
        'physical_authorization': False, 'hardware_actions_performed': False,
        'radio_actions_authorized': False, 'files': file_bindings(),
        'prerequisite_qualifications': validate_prerequisites(),
        'qualification': {'path': str(qualification.resolve()), 'sha256': base.digest(qualification), 'passed': count},
        'remaining': ['fresh route and exclusive physical binding', 'RAM transfer and physical readback',
            'platform/UI acceptance and independent client/RF/release gates']}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x', encoding='ascii') as stream:
        stream.write(json.dumps(review, indent=2) + '\n')
    return review


def plan(direction: str, review_path: Path | None = None, review_sha: str = '',
         network_authorization_path: Path | None = None, network_authorization_sha: str = '',
         server_ipv4: str = '192.168.1.49', interface_index: int = 18,
         firewall_mode: str = 'temporary-scoped-rule', existing_permission_path: Path | None = None,
         existing_permission_sha: str = '') -> dict:
    if firewall_mode not in ('temporary-scoped-rule', 'existing-permission'):
        raise ValueError('explicit supported firewall mode required')
    if (existing_permission_path is None) != (not existing_permission_sha):
        raise ValueError('existing permission path and hash must be paired')
    if (firewall_mode == 'existing-permission') != (existing_permission_path is not None):
        raise ValueError('existing permission binding must exactly match selected mode')
    permission = (existing_permission.validate_permission(existing_permission_path, existing_permission_sha,
                  python_executable=str(Path(sys.executable).resolve()))
                  if firewall_mode == 'existing-permission' else None)
    image, current = exact_pair(direction)
    server_ipv4 = exact_server(server_ipv4)
    if type(interface_index) is not int or interface_index != 18 or server_ipv4 != '192.168.1.49':
        raise ValueError('prepared Ethernet execution is bound to current .49/interface18 scope')
    if (review_path is None) != (not review_sha) or (network_authorization_path is None) != (not network_authorization_sha):
        raise ValueError('record path and exact hash must be provided together')
    value = base.plan(direction)
    if review_path is not None:
        validate_executor_review(review_path, review_sha)
    authority = None
    if network_authorization_path is not None:
        authority = validate_network_authorization(network_authorization_path, network_authorization_sha,
            server_ipv4=server_ipv4, interface_index=interface_index)
    preflight = base.generic_preflight(image, current)
    preflight['legacy_preflight_transport_description'] = preflight.get('write_transport')
    preflight['write_transport'] = 'UART Bootbase with independently verified Ethernet RAM preload'
    preflight['requires_execute'] = ['fresh inherited physical lease/binding', 'reviewed scoped Ethernet RAM load', 'exact existing action ACK']
    value.update(schema='openmitrastar.f325-ethernet-plan/v1', transport='ethernet-tftp',
        executor_review_verified=review_path is not None,
        network_authorization_verified=authority is not None,
        network_authorization=authority,
        network={'server_ipv4': server_ipv4, 'client_ipv4': base.HOST, 'interface_index': interface_index,
                 'interface_alias': 'Ethernet', 'python_executable': str(Path(sys.executable).resolve()),
                 'firewall_mode': firewall_mode, 'existing_permission': permission,
                 'plaintext': True, 'host_address_or_route_changes_allowed': False},
        preflight=preflight,
        status=('OFFLINE_READY_FRESH_PHYSICAL_GATES_PENDING' if review_path and authority else
                'NO_GO_EXECUTOR_REVIEW_PENDING' if authority else 'NO_GO_NETWORK_AUTHORITY_OR_REVIEW_MISSING'))
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--direction', choices=('promote','rollback'), default='promote')
    parser.add_argument('--server-ip', default='192.168.1.49')
    parser.add_argument('--interface-index', type=int, default=18)
    parser.add_argument('--executor-review', type=Path)
    parser.add_argument('--executor-review-sha256', default='')
    parser.add_argument('--network-authorization', type=Path)
    parser.add_argument('--network-authorization-sha256', default='')
    parser.add_argument('--firewall-mode', choices=('temporary-scoped-rule','existing-permission'), default='temporary-scoped-rule')
    parser.add_argument('--existing-permission', type=Path)
    parser.add_argument('--existing-permission-sha256', default='')
    parser.add_argument('--verify-writer', type=Path)
    parser.add_argument('--create-review', type=Path)
    parser.add_argument('--reviewed-executor', action='store_true')
    parser.add_argument('--qualification', type=Path)
    args = parser.parse_args(argv)
    if args.create_review:
        if not args.reviewed_executor or not args.qualification:
            parser.error('explicit code review and qualification required')
        result = create_review(args.create_review, args.qualification)
    elif args.verify_writer:
        result = verify_writer_result(args.verify_writer, direction=args.direction, server_ipv4=args.server_ip)
    else:
        result = plan(args.direction, args.executor_review, args.executor_review_sha256,
            args.network_authorization, args.network_authorization_sha256, args.server_ip, args.interface_index,
            args.firewall_mode, args.existing_permission, args.existing_permission_sha256)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(json.dumps({'status': 'REFUSED', 'error_type': type(error).__name__,
            'reason': str(error), 'hardware_actions_performed': False}), file=sys.stderr)
        raise SystemExit(1)
