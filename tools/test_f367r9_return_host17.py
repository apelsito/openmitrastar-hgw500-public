"""Offline host17 observation/launcher delta tests. No host or device probe."""
from pathlib import Path
import argparse
import copy
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace

import f367r9_return_f365_host17 as current


class Tests(unittest.TestCase):
    def setUp(self):
        self.original = current.core.read(current.PREVIOUS_PLAN)
        old = self.original['network']['existing_permission']['projection']
        now = dict(old, connection_interface_index='17')
        self.observation = dict(schema='openmitrastar.r9-host17-observation/v1', status='PASS_HOST17_ONLY_INDEX_REBIND',
            device_access=False, host_mutation=False, firewall_mutation=False, address_route_mutation=False, listener_started=False,
            previous_plan_sha256=current.PREVIOUS_SHA, cause_of_r9_failure='NOT_ATTESTED',
            permission=dict(projection=now, fingerprint_sha256=current.fingerprint(now)),
            comparison=dict(status='PASS_ONLY_CONNECTION_INTERFACE_INDEX_CHANGED', changed_fields=['connection_interface_index'],
                            original_fingerprint_sha256=current.fingerprint(old), current_fingerprint_sha256=current.fingerprint(now)),
            network=dict(identity=dict(current.EXPECTED_IDENTITY), adapter_status='Up', media_type='802.3', address_state='Preferred',
                         skip_as_source=False, old_index18_ipv4_count=0, direct_route=True, host_mutation=False, device_access=False,
                         adapter_description='Synthetic adapter', device_name='Synthetic device'))

    def test_exact_delta_accepted(self):
        current.validate_observation(self.observation, self.original)

    def test_original_fingerprint_matches_existing_permission(self):
        old = self.original['network']['existing_permission']['projection']
        self.assertEqual(current.fingerprint(old), 'df0c7fac07a2dfae253bd0cef8f4b9a76e8b46b6965ba635be6831ccbbd8270f')

    def test_every_unrelated_projection_change_rejected(self):
        for field in self.observation['permission']['projection']:
            changed = copy.deepcopy(self.observation)
            changed['permission']['projection'][field] = 'unrelated'
            with self.subTest(field=field), self.assertRaises(current.core.Failure):
                current.validate_observation(changed, self.original)

    def test_every_adapter_identity_field_pinned(self):
        for field in current.EXPECTED_IDENTITY:
            changed = copy.deepcopy(self.observation)
            changed['network']['identity'][field] = 'wrong'
            with self.subTest(field=field), self.assertRaises(current.core.Failure):
                current.validate_observation(changed, self.original)

    def test_mutation_or_device_probe_disallowed(self):
        for field in ('device_access', 'host_mutation', 'firewall_mutation', 'address_route_mutation', 'listener_started'):
            changed = copy.deepcopy(self.observation)
            changed[field] = True
            with self.subTest(field=field), self.assertRaises(current.core.Failure):
                current.validate_observation(changed, self.original)

    def test_changed_network_shape_rejected(self):
        for field, value in (('adapter_status', 'Down'), ('media_type', 'Native 802.11'), ('address_state', 'Tentative'),
                             ('skip_as_source', True), ('old_index18_ipv4_count', 1), ('direct_route', False)):
            changed = copy.deepcopy(self.observation)
            changed['network'][field] = value
            with self.subTest(field=field), self.assertRaises(current.core.Failure):
                current.validate_observation(changed, self.original)

    def test_new_guard_is_used_for_every_network_call(self):
        host = current.Host({'sources': {}}, Path('.'), admission=True)
        result = SimpleNamespace(returncode=0, stdout=b'PASS_R9_RETURN_HOST17_CONTEXT', stderr=b'')
        with patch.object(current.subprocess, 'run', return_value=result) as run:
            self.assertTrue(host.network_guard())
        arguments = run.call_args.args[0]
        self.assertIn(str(current.ROOT/'tools/assert_f367r9_return_context_host17.ps1'), arguments)
        self.assertIn('-CheckNetwork', arguments)
        self.assertIn('-Admission', arguments)

    def test_launcher_changes_only_versioned_host_binding(self):
        tools = current.ROOT/'tools'
        old = (tools/'run_f367r9_return_f365.ps1').read_text(encoding='utf-8-sig')
        replacements = {
            "'f367r9_return_context.ps1'": "'f367r9_return_context_host17.ps1'",
            "'f367r9_return_f365.py'": "'f367r9_return_f365_host17.py'",
            ". (Join-Path $PSScriptRoot 'f325_existing_firewall.ps1')\n. (Join-Path $PSScriptRoot 'f336_host_network.ps1')": ". (Join-Path $PSScriptRoot 'f367r9_host17_guard.ps1')",
            'Assert-F325ExistingPermission -Plan': 'Assert-R9Host17Permission -Plan',
            'Assert-F336HostNetwork -Plan': 'Assert-R9Host17Network -Plan',
            'Assert-R9ReturnContext': 'Assert-R9ReturnHost17Context',
        }
        for before, after in replacements.items():
            self.assertIn(before, old)
            old = old.replace(before, after)
        self.assertEqual(old, (tools/'run_f367r9_return_f365_host17.ps1').read_text(encoding='utf-8-sig'))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(Tests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    files = [Path(__file__).resolve(), Path(current.__file__).resolve(), current.ROOT/'tools/run_f367r9_return_f365_host17.ps1']
    current.core.save_new(args.result, dict(status='PASS_R9_RETURN_HOST17_DELTA_TESTS' if result.wasSuccessful() else 'FAIL',
                                          tests=result.testsRun, hardware_actions=False,
                                          source_pins={str(file): current.core.sha(file) for file in files}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
