"""Prepare a new timestamped F372 review plan. Offline only, no execute flag."""
from __future__ import annotations

import argparse
import copy
import json
from datetime import datetime, timezone
from pathlib import Path

import f372_install_contract as c


def fault_tests(plan):
    checks = []
    def reject(name, action):
        try:
            action()
        except (ValueError, KeyError, TypeError):
            checks.append(dict(name=name, passed=True))
        else:
            raise ValueError('fault_not_rejected:'+name)
    for name, change in [
        ('physical_mtd_number_confusion', lambda p: p.update(write_target='logical_mtd4/store')),
        ('store_erase_overlap', lambda p: p.update(erase_bytes=c.SLOT)),
        ('slot_write_instead_of_prefix', lambda p: p.update(erase_end_exclusive=0xf80000)),
        ('old_COM3_binding', lambda p: p['host_binding'].update(uart_port='COM3')),
        ('wrong_device_ip', lambda p: p['host_binding'].update(client_ipv4='192.168.1.1')),
        ('different_candidate', lambda p: p['images']['f372'].update(sha256='0'*64)),
        ('different_rollback', lambda p: p['images']['f365'].update(bytes=5382143)),
        ('old_executor_unchanged', lambda p: p['writer_reuse'].update(unchanged_old_executor_permitted=True)),
        ('redundant_backup_copy', lambda p: p['writer_reuse'].update(redundant_backup_copy_permitted=True)),
        ('invented_safety_PASS', lambda p: p['recovery'].update(current_recovery_ready='PASS')),
        ('offline_promoted_to_GO', lambda p: p.update(physical_go=True)),
        ('hardware_execution', lambda p: p.update(hardware_actions=True)),
    ]:
        changed = copy.deepcopy(plan)
        change(changed)
        reject(name, lambda p=changed: c.validate_plan_scope(p))
    expected = plan['owner_authorization_scope']
    reject('boolean_is_not_owner_authorization', lambda: c.validate_owner_receipt(True, expected))
    reject('generic_authorization_is_not_exact', lambda: c.validate_owner_receipt(dict(authorized=True), expected))
    # Synthetic receipt tests stay inside test output; never emit an authorization file.
    synthetic = dict(schema=c.AUTH_SCHEMA, authority='human_user', decision='AUTHORIZE_EXACT_SCOPE',
        scope=copy.deepcopy(expected), scope_sha256=c.scope_sha(expected), reviewed_scope_sha256=c.scope_sha(expected),
        owner_message=dict(reference='SYNTHETIC_TEST_ONLY_NOT_OWNER_MESSAGE', text='SYNTHETIC_TEST_ONLY'),
        hardware_actions_already_performed=False)
    valid = c.validate_owner_receipt(synthetic, expected)
    c.require(valid['confers_physical_go'] is False, 'synthetic_authorization_cannot_GO')
    checks.append(dict(name='scope_receipt_never_confers_GO_and_requires_provenance', passed=True))
    for name, change in [
        ('auth_changed_image', lambda r: r['scope'].update(image_sha256='0'*64)),
        ('auth_changed_target', lambda r: r['scope'].update(physical_write_target='mtd3/linux_safety')),
        ('auth_no_reboot_scope', lambda r: r['scope'].update(actions=[])),
        ('auth_wrong_review', lambda r: r.update(reviewed_scope_sha256='0'*64)),
        ('auth_no_human_reference', lambda r: r.update(owner_message={})),
    ]:
        changed = copy.deepcopy(synthetic)
        change(changed)
        reject(name, lambda r=changed: c.validate_owner_receipt(r, expected))
    reject('duplicate_JSON_fields', lambda: json.loads('{"authorized":true,"authorized":false}', object_pairs_hook=c.unique))
    return dict(schema='openmitrastar.f372-install-contract-tests/v1', status='PASS_OFFLINE_FAULT_TESTS',
        passed=True, checks=checks, count=len(checks), hardware_actions=False,
        synthetic_authorization_is_not_owner_evidence=True)


def main():
    ap = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    ap.add_argument('--plan', type=Path, help='Revalidate an existing plan without creating output')
    ap.add_argument('--plan-sha256')
    ap.add_argument('--authorization', type=Path, help='Optional existing owner receipt; never creates authorization')
    ap.add_argument('--authorization-sha256')
    a = ap.parse_args()
    if a.plan:
        c.require(a.plan_sha256 is not None and not a.authorization, 'validate_arguments')
        plan = c.load_plan(a.plan, a.plan_sha256)
        print(json.dumps(dict(status=plan['status'], physical_go=False, hardware_actions=False)))
        return 0
    c.require(a.plan_sha256 is None, 'plan_path_missing')
    c.require(bool(a.authorization) == bool(a.authorization_sha256), 'authorization_hash_required')
    plan = c.prepare_contract()
    tests = fault_tests(plan)
    if a.authorization:
        p = c.local_path(a.authorization)
        c.require(c.sha(p) == a.authorization_sha256, 'authorization_receipt_hash')
        plan['authorization_receipt_structure'] = c.validate_owner_receipt(c.read(p), plan['owner_authorization_scope'])
        plan['authorization_receipt_structure'].update(path=str(p), sha256=a.authorization_sha256)
        plan['sources'][str(p)] = a.authorization_sha256
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out = c.ROOT/'outputs/preflight'/('f372-install-'+stamp)
    out.mkdir(parents=True, exist_ok=False)
    with (out/'tests.json').open('x', encoding='ascii') as stream:
        stream.write(json.dumps(tests, indent=2)+'\n')
    plan['tests'] = dict(path=str(out/'tests.json'), sha256=c.sha(out/'tests.json'), count=tests['count'])
    plan['sources'][str(out/'tests.json')] = c.sha(out/'tests.json')
    plan['generated_at_utc'] = datetime.now(timezone.utc).isoformat()
    path = out/'plan.json'
    with path.open('x', encoding='ascii') as stream:
        stream.write(json.dumps(plan, indent=2)+'\n')
    digest = c.sha(path)
    c.load_plan(path, digest)
    result = dict(status='PASS_OFFLINE_F372_INSTALL_CONTRACT_PHYSICAL_NO_GO',
        plan=str(path), plan_sha256=digest, source_pins=len(plan['sources']),
        fault_checks=tests['count'], candidate_sha256=plan['images']['f372']['sha256'],
        candidate_bytes=plan['images']['f372']['bytes'], candidate_fullslot_crc32='9a81d387',
        rollback_fullslot_crc32='118901d4', store_crc32='5d2ee646',
        owner_authorization_scope_sha256=plan['owner_authorization_scope_sha256'],
        recovery_history_status=plan['recovery']['status'], physical_go=False,
        executor_implemented=False, hardware_actions=False,
        missing_gates=plan['fresh_physical_gates'])
    with (out/'result.json').open('x', encoding='ascii') as stream:
        stream.write(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
