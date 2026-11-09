"""Versioned host-index binding; exact previous recovery flow/writer unchanged."""
from pathlib import Path
import argparse
import base64
import hashlib
import json
import os
import subprocess

import f367r9_return_f365 as core

ROOT = core.ROOT
PREVIOUS_PLAN = ROOT/'outputs/preflight/r9-return-f365-20260923T081235Z/plan.json'
PREVIOUS_SHA = '6cbc06e281b36dcdbe282c96a063b67424816d74b7ed10bb9c25929792594f5e'
EXPECTED_IDENTITY = dict(interface_index=17, interface_alias='Ethernet',
    interface_guid='b75315d5-9f01-448f-a259-c9d8f25d2233',
    pnp_device_id=r'PCI\VEN_10EC&DEV_8168&SUBSYS_E0001458&REV_16\6E8F9B4DC018000000',
    source_ipv4='192.168.1.49', prefix_length=24, target_ipv4='192.168.1.90',
    route_prefix='192.168.1.0/24', next_hop='0.0.0.0', link_speed_bps=1000000000)


def fingerprint(projection):
    lines = [key+'='+base64.b64encode(str(projection[key]).encode()).decode('ascii') for key in sorted(projection)]
    return hashlib.sha256('\n'.join(lines).encode()).hexdigest()


def validate_observation(observation, original):
    core.require(observation['schema'] == 'openmitrastar.r9-host17-observation/v1'
                 and observation['status'] == 'PASS_HOST17_ONLY_INDEX_REBIND', 'host17_observation_status')
    for field in ('device_access', 'host_mutation', 'firewall_mutation', 'address_route_mutation', 'listener_started'):
        core.require(observation[field] is False, 'host17_forbidden_observation_action')
    core.require(observation['previous_plan_sha256'] == PREVIOUS_SHA and observation['cause_of_r9_failure'] == 'NOT_ATTESTED', 'host17_history_binding')
    permission = observation['permission']
    old = original['network']['existing_permission']['projection']
    now = permission['projection']
    core.require(set(old) == set(now) and old['connection_interface_index'] == '18'
                 and now['connection_interface_index'] == '17', 'host17_projection_scope')
    changed = [key for key in old if old[key] != now[key]]
    core.require(changed == ['connection_interface_index'], 'host17_unrelated_permission_change')
    core.require(fingerprint(old) == original['network']['existing_permission']['fingerprint_sha256'], 'host17_original_fingerprint')
    core.require(fingerprint(now) == permission['fingerprint_sha256'], 'host17_current_fingerprint')
    comparison = observation['comparison']
    core.require(comparison['status'] == 'PASS_ONLY_CONNECTION_INTERFACE_INDEX_CHANGED'
                 and comparison['changed_fields'] == changed
                 and comparison['original_fingerprint_sha256'] == fingerprint(old)
                 and comparison['current_fingerprint_sha256'] == fingerprint(now), 'host17_comparison_receipt')
    network = observation['network']
    core.require(network['identity'] == EXPECTED_IDENTITY and network['adapter_status'] == 'Up'
                 and network['media_type'] == '802.3' and network['address_state'] == 'Preferred'
                 and network['skip_as_source'] is False and network['old_index18_ipv4_count'] == 0
                 and network['direct_route'] is True and network['host_mutation'] is False
                 and network['device_access'] is False, 'host17_network_identity')
    core.require(isinstance(network['adapter_description'], str) and network['adapter_description']
                 and isinstance(network['device_name'], str) and network['device_name'], 'host17_adapter_description')
    return observation


def load_plan(path, digest):
    plan = core.load_plan(path, digest)
    core.require(core.sha(PREVIOUS_PLAN) == PREVIOUS_SHA, 'host17_previous_plan_hash')
    previous = core.read(PREVIOUS_PLAN)
    for key, value in previous.items():
        if key not in ('network', 'sources'):
            core.require(plan[key] == value, 'host17_recovery_contract_changed_'+key)
    core.require(plan['host_binding_revision'] == 'r9-recovery-host17-v2', 'host17_plan_revision')
    network = dict(plan['network'])
    reference = network.pop('host17_observation')
    network['interface_index'] = 18
    core.require(network == previous['network'], 'host17_network_changed_beyond_index')
    core.require(plan['network']['interface_index'] == 17, 'host17_exact_index')
    core.require(core.sha(reference['path']) == reference['sha256'], 'host17_observation_hash')
    observation = validate_observation(core.read(reference['path']), previous)
    for source, expected in observation['source_pins'].items():
        core.require(plan['sources'].get(source) == expected == core.sha(source), 'host17_observed_source_drift')
    for field, status in (('host17_tests', 'PASS_R9_HOST17_BINDING_TESTS'),
                          ('host17_delta_tests', 'PASS_R9_RETURN_HOST17_DELTA_TESTS')):
        proof = plan[field]
        core.require(core.sha(proof['path']) == proof['sha256'], 'host17_test_hash')
        tests = core.read(proof['path'])
        core.require(tests['status'] == status and tests['hardware_actions'] is False, 'host17_tests_failed')
        for source, expected in tests['source_pins'].items():
            core.require(plan['sources'].get(source) == expected == core.sha(source), 'host17_tested_source_drift')
    return plan


class Host(core.Host):
    def _guard(self, network):
        for path, digest in self.plan['sources'].items():
            core.require(core.sha(path) == digest, 'source_drift')
        args = [core.desktop_ps.executable(), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(ROOT/'tools/assert_f367r9_return_context_host17.ps1')]
        if network:
            args.append('-CheckNetwork')
        if self.admission:
            args.append('-Admission')
        result = subprocess.run(args, env=core.desktop_ps.environment(), capture_output=True, timeout=30,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        return result.returncode == 0 and result.stdout.strip() == b'PASS_R9_RETURN_HOST17_CONTEXT' and not result.stderr


def main():
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--plan-sha256', required=True)
    parser.add_argument('--output-dir', type=Path)
    parser.add_argument('--fresh-boot-id')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--admit', action='store_true')
    mode.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    plan = load_plan(args.plan, args.plan_sha256)
    if not (args.admit or args.execute):
        print(json.dumps(dict(status='OFFLINE_VALID_R9_RETURN_F365', host_binding_revision='r9-recovery-host17-v2', hardware_actions=False, f365_sha256=core.F365_SHA)))
        return 0
    core.require(os.environ.get('OM_R9_RETURN_CONTEXT') and args.output_dir is not None, 'owning_launcher_required')
    out = core.safe_path(args.output_dir)
    core.require(out.parent == core.EVIDENCE_ROOT and out.is_dir(), 'evidence_scope')
    context = json.loads(os.environ['OM_R9_RETURN_CONTEXT'], object_pairs_hook=core.unique)
    core.require(context['initial_boot_id'] == args.fresh_boot_id and context['plan_sha256'] == args.plan_sha256, 'launcher_epoch_binding')
    if args.admit:
        host = Host(plan, out, admission=True)
        try:
            result = host.admission_proof(args.fresh_boot_id)
        finally:
            core.require(host.contain(), 'admission_children_uncontained')
        core.save_new(out/'admission.json', result)
    else:
        core.save_new(out/'execution-claimed.json', dict(plan_sha256=args.plan_sha256, boot_id=args.fresh_boot_id))
        result = core.run(plan, out, args.fresh_boot_id, host_factory=Host)
    print(json.dumps(dict(status=result['status'], hardware_actions=not args.admit)))
    return int(result['status'].startswith('FAILED'))


if __name__ == '__main__':
    raise SystemExit(main())
