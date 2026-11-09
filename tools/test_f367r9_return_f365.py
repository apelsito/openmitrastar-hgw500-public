"""Offline fault injection for the bounded recovery; never construct real I/O."""
from pathlib import Path
import argparse
import copy
import json
import tempfile
import unittest
from unittest.mock import patch

import f367r9_return_f365 as recovery

BOOT = 'a104df0a-24e3-4b56-a62b-541a0f95d872'


def identity(boot=BOOT):
    return dict(boot_id=boot, uts='#358 @1790006400', f340='F340_WATCHDOG_BASELINE', f336='')


def quiet():
    return b'boot=ready\nqdrv=0\nprovider=0\nprovider366=0\nwifi0=0\nowner=0\nsocket=0\nowners=0\nsysrq=1\nfatal=0\n'


class FakeHost(recovery.Host):
    boot = BOOT
    quiet_data = quiet()
    store_ok = True
    config_ok = True
    watchdog_ok = True
    reboot_count = 0

    def _guard(self, network):
        return True

    def identity(self, name):
        return identity(self.boot)

    def ssh(self, command, *args, **kwargs):
        if command == recovery.quiescence_command():
            return self.quiet_data
        raise AssertionError('unexpected real command')

    def watchdog_inactive(self):
        recovery.require(self.watchdog_ok, 'watchdog_not_inactive')
        return dict(control='00000000', device_opened=0)

    def verify_store(self):
        recovery.require(self.store_ok, 'preserved_store_changed')
        return {'sha256': self.plan['store']['sha256']}

    def verify_configuration(self):
        recovery.require(self.config_ok, 'journal_not_applied_or_backend_unready')
        return dict(sequence=2, source='journal')

    def verify_ethernet(self):
        return dict(status='PASS')

    def storage_gate(self):
        return dict(persist_readonly=True)

    def reboot_to_prompt(self, uart, software_recovery=False):
        if software_recovery:
            raise AssertionError('serial fallback forbidden')
        type(self).reboot_count += 1

    def platform(self, name, out):
        return dict(status='PASS', checks=27)

    def verify_thermal_disabled(self):
        return dict(enabled=False, activation_attempted=False)

    def contain(self):
        return True


class FakeUart:
    opens = 0
    write_in_flight = False
    failed = None

    def __init__(self, *args):
        pass

    def open(self):
        type(self).opens += 1

    def has_prompt(self):
        return True

    def close(self):
        return dict(reader_stopped=True, port_closed=True, reader_error=None)


class RecoveryTests(unittest.TestCase):
    def setUp(self):
        FakeHost.boot = BOOT
        FakeHost.quiet_data = quiet()
        FakeHost.store_ok = FakeHost.config_ok = FakeHost.watchdog_ok = True
        FakeHost.reboot_count = FakeUart.opens = 0
        FakeUart.write_in_flight = False
        self.plan = dict(store=dict(sha256='fixture', crc32='5d2ee646'),
                         images=dict(f365=dict(path='fixture', sha256=recovery.F365_SHA)))

    def run_fake(self, **patches):
        with tempfile.TemporaryDirectory(prefix='r9-return-test-') as folder:
            with patch.object(recovery.writer, 'domain', return_value={'protected': 'fixture'}), \
                 patch.object(recovery.writer, 'flash_crc', **patches.get('flash_crc', {'return_value': '4fa4640f'})) as crc, \
                 patch.object(recovery.writer, 'write_image', **patches.get('write_image', {'return_value': {'image': recovery.F365_SHA, 'byte_compare': True, 'full_slot_crc32': '118901d4'}})) as write, \
                 patch.object(recovery.writer, 'boot_written', return_value=identity('b104df0a-24e3-4b56-a62b-541a0f95d872')):
                result = recovery.run(self.plan, Path(folder), BOOT, host_factory=FakeHost, uart_factory=FakeUart)
                self.assertTrue((Path(folder)/'result.json').exists())
                return result, write.call_count, crc.call_count

    def test_same_old_epoch_rejected_without_uart(self):
        FakeHost.boot = recovery.OLD_BOOT
        result, writes, _ = self.run_fake()
        self.assertEqual(result['error'], 'new_r9_epoch_required')
        self.assertEqual((FakeUart.opens, writes), (0, 0))

    def test_wrong_new_epoch_rejected_without_uart(self):
        FakeHost.boot = 'b104df0a-24e3-4b56-a62b-541a0f95d872'
        result, writes, _ = self.run_fake()
        self.assertEqual(result['error'], 'new_r9_epoch_required')
        self.assertEqual((FakeUart.opens, writes), (0, 0))

    def test_wrong_kernel_rejected(self):
        row = identity()
        row['uts'] = '#359 @1790006400'
        with self.assertRaisesRegex(recovery.Failure, 'r9_kernel_identity'):
            recovery.fresh_epoch(row, BOOT)

    def test_all_busy_or_incomplete_fields_block_uart(self):
        for key in ('qdrv', 'provider', 'provider366', 'wifi0', 'owner', 'socket', 'owners', 'fatal'):
            with self.subTest(key=key):
                FakeHost.quiet_data = quiet().replace((key+'=0\n').encode(), (key+'=1\n').encode())
                result, writes, _ = self.run_fake()
                self.assertEqual(result['error'], 'r9_not_quiescent')
                self.assertEqual((FakeUart.opens, writes), (0, 0))

    def test_boot_not_ready_blocks_uart(self):
        FakeHost.quiet_data = quiet().replace(b'boot=ready', b'boot=pending')
        result, writes, _ = self.run_fake()
        self.assertEqual(result['error'], 'r9_not_quiescent')
        self.assertEqual((FakeUart.opens, writes), (0, 0))

    def test_duplicate_and_missing_quiescence_rejected(self):
        for raw in (quiet()+b'owner=0\n', quiet().replace(b'owner=0\n', b'')):
            with self.assertRaises(recovery.Failure):
                recovery.validate_quiescence(raw)

    def test_reboot_capability_required(self):
        with self.assertRaisesRegex(recovery.Failure, 'qualified_ssh_reboot_not_enabled'):
            recovery.validate_quiescence(quiet().replace(b'sysrq=1', b'sysrq=0'))

    def test_watchdog_store_configuration_each_block_uart(self):
        for attr in ('watchdog_ok', 'store_ok', 'config_ok'):
            with self.subTest(attr=attr):
                setattr(FakeHost, attr, False)
                result, writes, _ = self.run_fake()
                self.assertTrue(result['retain_lease_required'])
                self.assertEqual((FakeUart.opens, writes), (0, 0))
                setattr(FakeHost, attr, True)

    def test_physical_r9_crc_mismatch_never_erases(self):
        result, writes, _ = self.run_fake(flash_crc={'side_effect': recovery.Failure('flash_crc_mismatch')})
        self.assertEqual((FakeHost.reboot_count, writes), (1, 0))
        self.assertTrue(result['retain_lease_required'])

    def test_writer_failure_never_retries_or_reboots_again(self):
        result, writes, _ = self.run_fake(write_image={'side_effect': recovery.Failure('candidate_byte_compare')})
        self.assertEqual((FakeHost.reboot_count, writes), (1, 1))
        self.assertFalse(result['f365_return_confirmed'])
        self.assertTrue(result['retain_lease_required'])

    def test_ambiguous_write_always_retains_lease(self):
        def fail(*args):
            FakeUart.write_in_flight = True
            raise recovery.Failure('topaz_prompt_timeout')
        result, writes, _ = self.run_fake(write_image={'side_effect': fail})
        self.assertEqual(writes, 1)
        self.assertTrue(result['flash_command_in_flight'])
        self.assertTrue(result['retain_lease_required'])

    def test_complete_return_allows_retirement(self):
        result, writes, _ = self.run_fake()
        self.assertEqual(result['status'], 'PASS_R9_EXACT_F365_RETURN')
        self.assertEqual((FakeHost.reboot_count, writes), (1, 1))
        self.assertFalse(result['retain_lease_required'])

    def test_containment_failure_overrides_success(self):
        with patch.object(FakeHost, 'contain', return_value=False):
            result, _, _ = self.run_fake()
        self.assertEqual(result['status'], 'FAILED_RETURN_NO_RETRY')
        self.assertTrue(result['retain_lease_required'])

    def test_lease_loss_overrides_success(self):
        with patch.object(FakeHost, 'guard', side_effect=[True, False]):
            result, _, _ = self.run_fake()
        self.assertEqual(result['status'], 'FAILED_RETURN_NO_RETRY')
        self.assertTrue(result['retain_lease_required'])

    def test_core_writer_vocabulary_never_exposes_oem_or_store_writes(self):
        self.assertEqual(recovery.writer.ERASE_COMMAND, 'spi_flash erase 0x007e0000 0x005e0000')
        self.assertEqual(recovery.writer.write_command(dict(bytes=5382144)), 'spi_flash write 0x007e0000 0x83000000 0x00522000')

    def test_unqualified_plan_actions_rejected(self):
        original = recovery.read(recovery.ROOT/'outputs/preflight/f367r9-campaign-20260922T224746Z/plan.json')
        original.update(schema=recovery.PLAN_SCHEMA, status='PASS_OFFLINE_RETURN_PLAN', max_attempts=1, old_boot_id=recovery.OLD_BOOT,
                        context_ttl_seconds=3600, outer_timeout_seconds=3000, evidence_root=str(recovery.EVIDENCE_ROOT),
                        parent_lease=dict(pid=38908, process_start_ticks=639257141569704476), serial_reset_fallback_allowed=False)
        for name in ('watchdog_arm_allowed', 'radio_tests_allowed', 'sensor_activation_allowed', 'boot_environment_persistence_allowed', 'store_write_allowed'):
            original[name] = False
        recovery.validate_scope(original)
        for key in ('watchdog_arm_allowed', 'radio_tests_allowed', 'store_write_allowed', 'serial_reset_fallback_allowed'):
            changed = copy.deepcopy(original)
            changed[key] = True
            with self.subTest(key=key), self.assertRaises(recovery.Failure):
                recovery.validate_scope(changed)
        for field, value in (('sha256', '0'*64), ('bytes', 5382145), ('full_slot_crc32', '00000000')):
            changed = copy.deepcopy(original)
            changed['images']['f365'][field] = value
            with self.subTest(field=field), self.assertRaises(recovery.Failure):
                recovery.validate_scope(changed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(RecoveryTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    pins = {str(p): recovery.sha(p) for p in (Path(__file__).resolve(), Path(recovery.__file__).resolve())}
    recovery.save_new(args.result, dict(status='PASS_R9_RETURN_FAULT_TESTS' if result.wasSuccessful() else 'FAIL',
                                      tests=result.testsRun, failures=len(result.failures), errors=len(result.errors), hardware_actions=False,
                                      source_pins=pins))
    raise SystemExit(0 if result.wasSuccessful() else 1)
