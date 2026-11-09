"""Fault tests for the F372 decision core and the reused prefix writer.

All host, UART, transport, receipt provenance and runtime decisions are synthetic.
This test entrypoint cannot grant hardware admission and never constructs native
host/UART/network adapters. Tests preserve the original F372 plan and artifacts.
"""
from __future__ import annotations

import argparse
import copy
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from contextlib import nullcontext

import f365_install_executor as original
import f372_install_contract as contract


ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = ROOT / 'outputs/preflight/f372-install-20261021T195348642022Z/plan.json'
PLAN_SHA = 'a502abe660e7da3e3d561d3f8995ac0d43701cb683e3b03d919d5234e97c25c1'
OLD_BOOT = '24c647c0-df14-4724-8639-2d3b15a2bdb7'
NEW_BOOT = '2abf57ad-b899-4a0a-9e9a-cff0be9cffd2'
RETURN_BOOT = '10b81c2d-dc29-4c08-a23a-a4c1f5fb3f9c'
NOW = 1792612800.0
OUTPUT: Path | None = None
PLAN: dict | None = None


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def identity(boot=OLD_BOOT):
    return dict(boot_id=boot, uts='#358 @1790006400',
                f340='F340_WATCHDOG_BASELINE', f336='')


def reply(command, rows=()):
    return (command+'\r\n'+'\r\n'.join(rows)+'\r\ntopaz> ').encode('ascii')


class CommandUart:
    """Command-boundary fake; uses the original response parser."""
    execution_scope = 'offline_simulation'

    def __init__(self, image, fault=None):
        self.image = image
        self.fault = fault
        self.calls = []
        self.mutations = []
        self.enabled = False
        self.write_in_flight = False
        self.erase_requested = False
        self.write_requested = False

    def enable_writer(self, image):
        assert image == self.image
        self.enabled = True

    def disable_writer(self):
        self.enabled = False

    def mutate(self, command):
        assert self.enabled
        self.mutations.append(command)
        self.write_in_flight = True
        if command == original.ERASE_COMMAND:
            self.erase_requested = True
            if self.fault == 'erase_timeout':
                raise original.Failure('SYNTHETIC_ERASE_TIMEOUT')
            self.write_in_flight = False
            rows = [f'Erase: flash=0x{contract.LIVE:x} size={contract.PREFIX}']
            if self.fault == 'erase_bad_receipt':
                rows = ['Erase: synthetic wrong scope']
            return reply(command, rows)
        assert command == original.write_command(self.image)
        self.write_requested = True
        if self.fault == 'write_timeout':
            raise original.Failure('SYNTHETIC_WRITE_TIMEOUT')
        self.write_in_flight = False
        rows = [f"Write: flash=0x{contract.LIVE:x} mem=0x{contract.LOAD:x} size={self.image['bytes']} ret_size={self.image['bytes']}"]
        if self.fault == 'write_bad_receipt':
            rows = ['Write: synthetic incomplete receipt']
        return reply(command, rows)

    def command(self, command, **kwargs):
        self.calls.append(command)
        expected = f"cmp.b 0x{contract.LOAD:08x} 0x{contract.READBACK:08x} 0x{self.image['bytes']:08x}"
        assert command == expected, 'unreviewed command requested'
        rows = [f"Total of {self.image['bytes']} bytes were the same"]
        if self.fault == 'compare':
            rows = ['Total of 1 bytes were the same']
        return reply(command, rows)


class OriginalWriterTests(unittest.TestCase):
    """Original write_image exercised; only effects/readback boundary replaced."""

    def exercise(self, fault=None):
        plan = PLAN
        image = plan['images']['f372']
        uart = CommandUart(image, fault)
        trace = []
        host = object()
        def transfer(*args, **kwargs):
            trace.append(('transfer', image['sha256']))
            if fault == 'transfer':
                raise original.Failure('SYNTHETIC_TRANSFER_FAILED')
            return {'synthetic_only': True}
        def domain(*args):
            trace.append(('domain',))
            if fault in ('protected', 'store'):
                raise original.Failure('SYNTHETIC_PROTECTED_OR_STORE_MISMATCH')
            return {'synthetic_only': True}
        def ram_crc(adapter, address, size):
            trace.append(('ram_crc', address, size))
            if address == contract.LOAD:
                return '00000000' if fault == 'candidate_ram' else image['crc32']
            return '00000000' if fault == 'fullslot_crc' else image['full_slot_crc32']
        def flash_crc(adapter, offset, size, expected=None):
            trace.append(('flash_crc', offset, size, expected))
            if fault == 'blank_crc' and offset == contract.LIVE:
                raise original.Failure('SYNTHETIC_BLANK_CRC_MISMATCH')
            if fault == 'store_after_erase' and offset == contract.STORE:
                raise original.Failure('SYNTHETIC_STORE_AFTER_ERASE_MISMATCH')
            return expected
        def flash_read(adapter, offset, size, address=contract.READBACK):
            trace.append(('flash_read', offset, size, address))
        with tempfile.TemporaryDirectory(prefix='writer-case-', dir=OUTPUT) as folder:
            with patch.object(original, 'transfer', side_effect=transfer), \
                 patch.object(original, 'domain', side_effect=domain), \
                 patch.object(original, 'ram_crc', side_effect=ram_crc), \
                 patch.object(original, 'flash_crc', side_effect=flash_crc), \
                 patch.object(original, 'flash_read', side_effect=flash_read):
                error = None
                try:
                    result = original.write_image(uart, host, plan, image, Path(folder),
                                                  plan['store']['crc32'], object)
                except Exception as failure:
                    error = type(failure).__name__
                    result = None
        return result, error, uart, trace

    def test_exact_prefix_success_uses_original_writer_and_parser(self):
        result, error, uart, trace = self.exercise()
        self.assertIsNone(error)
        self.assertEqual(uart.mutations, [original.ERASE_COMMAND,
                                         original.write_command(PLAN['images']['f372'])])
        self.assertFalse(uart.enabled)
        self.assertFalse(uart.write_in_flight)
        self.assertEqual(result['image'], PLAN['images']['f372']['sha256'])
        self.assertTrue(result['byte_compare'])
        self.assertEqual(result['full_slot_crc32'], '9a81d387')
        self.assertEqual(trace[:3], [('transfer', PLAN['images']['f372']['sha256']),
                                    ('domain',), ('ram_crc', contract.LOAD, 5382144)])
        self.assertIn(('flash_crc', contract.LIVE, contract.PREFIX,
                       PLAN['erased_prefix_crc32']), trace)
        self.assertIn(('flash_crc', contract.STORE, contract.STORE_BYTES,
                       PLAN['store']['crc32']), trace)
        self.assertEqual(trace.count(('domain',)), 2)

    def test_transfer_protected_store_or_ram_failure_has_zero_mutations(self):
        for fault in ('transfer', 'protected', 'store', 'candidate_ram'):
            with self.subTest(fault=fault):
                result, error, uart, _ = self.exercise(fault)
                self.assertIsNone(result)
                self.assertIsNotNone(error)
                self.assertEqual(uart.mutations, [])

    def test_erase_failure_or_blank_store_mismatch_never_programs(self):
        for fault in ('erase_timeout', 'erase_bad_receipt', 'blank_crc', 'store_after_erase'):
            with self.subTest(fault=fault):
                result, error, uart, _ = self.exercise(fault)
                self.assertIsNone(result)
                self.assertIsNotNone(error)
                self.assertEqual(uart.mutations, [original.ERASE_COMMAND])
                self.assertFalse(uart.enabled)
                self.assertEqual(uart.write_in_flight, fault == 'erase_timeout')

    def test_write_or_fullslot_compare_fault_never_retries_or_boots(self):
        for fault in ('write_timeout', 'write_bad_receipt', 'fullslot_crc', 'compare'):
            with self.subTest(fault=fault):
                result, error, uart, _ = self.exercise(fault)
                self.assertIsNone(result)
                self.assertIsNotNone(error)
                self.assertEqual(uart.mutations, [original.ERASE_COMMAND,
                                                 original.write_command(PLAN['images']['f372'])])
                self.assertFalse(uart.enabled)
                self.assertEqual(uart.write_in_flight, fault == 'write_timeout')
                self.assertFalse(any(command.startswith('bootm') for command in uart.calls))


class FakeHost:
    execution_scope = 'offline_simulation'

    def __init__(self, plan, out, rig):
        self.plan, self.out, self.rig = plan, out, rig
        self.servers = []
        self.transport_events = []
        self.network_check_failures = 0
        rig.events.append(('host_constructed',))

    def guard(self):
        self.rig.events.append(('guard',))
        return self.rig.fault != 'guard'

    def network_guard(self):
        return self.guard()

    def admission_binding(self, admission, decision):
        return self.rig.fault != 'admission_binding'

    def identity(self, name):
        self.rig.events.append(('identity', name))
        return identity(NEW_BOOT if self.rig.fault == 'baseline_boot' else OLD_BOOT)

    def initial_binding(self, observed):
        return self.rig.fault != 'initial_binding'

    def watchdog_inactive(self):
        if self.rig.fault == 'watchdog':
            raise original.Failure('SYNTHETIC_WATCHDOG_MISMATCH')
        return dict(control='00000000', device_opened=0, ready_for_arm=1)

    def verify_store(self):
        if self.rig.fault == 'baseline_store':
            raise original.Failure('SYNTHETIC_STORE_MISMATCH')
        return dict(sha256=self.plan['store']['sha256'], bytes=self.plan['store']['bytes'], read_only_mtd=True)

    def reboot_to_prompt(self, uart, software_recovery=False):
        assert software_recovery is False, 'serial reset forbidden'
        self.rig.events.append(('reboot',))
        if self.rig.fault == 'reboot_timeout':
            uart.prompt = False
            raise original.Failure('SYNTHETIC_REBOOT_TIMEOUT')
        uart.prompt = True

    def contain(self):
        self.rig.events.append(('contain',))
        return self.rig.fault != 'containment'

    def platform(self, name, out):
        self.rig.events.append(('platform', name))
        return dict(status='PASS', checks=27)

    def verify_configuration(self):
        return dict(sequence=2, source='journal')

    def verify_ethernet(self):
        return dict(status='PASS')

    def verify_thermal_disabled(self):
        return dict(enabled=False, activation_attempted=False)


class FakeUart:
    execution_scope = 'offline_simulation'

    def __init__(self, plan, guard, out, rig):
        self.plan, self.guard, self.out, self.rig = plan, guard, out, rig
        self.prompt = False
        self.failed = None
        self.write_in_flight = False
        self.erase_requested = self.write_requested = False
        self.serial_recovery_record = {}
        self.image = None
        rig.events.append(('uart_constructed',))

    def open(self):
        self.rig.events.append(('uart_open',))

    def has_prompt(self):
        return self.prompt

    def enable_writer(self, image):
        self.image = image

    def disable_writer(self):
        self.image = None

    def mutate(self, command):
        self.rig.events.append(('mutate', command))
        self.write_in_flight = True
        if command == original.ERASE_COMMAND:
            self.erase_requested = True
            if self.rig.fault == 'erase_timeout':
                raise original.Failure('SYNTHETIC_ERASE_TIMEOUT')
            self.write_in_flight = False
            return reply(command, [f'Erase: flash=0x{contract.LIVE:x} size={contract.PREFIX}'])
        assert self.image is not None
        assert command == original.write_command(self.image)
        self.write_requested = True
        if self.rig.fault == 'write_timeout':
            raise original.Failure('SYNTHETIC_WRITE_TIMEOUT')
        self.write_in_flight = False
        return reply(command, [f"Write: flash=0x{contract.LIVE:x} mem=0x{contract.LOAD:x} size={self.image['bytes']} ret_size={self.image['bytes']}"])

    def close(self):
        self.rig.events.append(('uart_close',))
        ok = self.rig.fault != 'uart_containment'
        return dict(reader_stopped=ok, port_closed=ok, reader_error=None)


class Rig:
    def __init__(self, folder, core, fault=None):
        self.folder, self.core, self.fault = Path(folder), core, fault
        self.events = []
        self.receipts = {}
        for name in ('authorization', 'recovery', 'executor_review', 'host_lease',
                     'uart_nonce', 'transport_review', 'live_boot'):
            path = self.folder/(name+'-SYNTHETIC_TEST_ONLY.json')
            path.write_text(json.dumps({'synthetic_test_only': True, 'gate': name})+'\n', encoding='ascii')
            self.receipts[name] = core.EvidenceRef(str(path), sha(path))
        pins = dict(PLAN['sources'])
        for path in (Path(core.__file__), Path(original.__file__), ROOT/'tools/f372_postboot_gate.py'):
            pins[str(path.resolve())] = sha(path)
        self.admission = core.VerifiedAdmission(
            plan_path=str(PLAN_PATH), plan_sha256=PLAN_SHA,
            scope_sha256=PLAN['owner_authorization_scope_sha256'],
            initial_boot_id=OLD_BOOT, lease_id='SYNTHETIC_TEST_LEASE_ONLY',
            nonce_sha256='9'*64, expires_unix=NOW+600,
            source_pins=pins, receipts=self.receipts)
        self.writer = SimpleNamespace(domain=self.domain, flash_crc=self.flash_crc,
                                      write_image=self.write_image, boot_written=self.boot_written)

    def verifier(self, admission, plan):
        self.events.append(('verify_admission',))
        return self.core.AdmissionDecision(
            plan_sha256=admission.plan_sha256, scope_sha256=admission.scope_sha256,
            initial_boot_id=admission.initial_boot_id, lease_id=admission.lease_id,
            nonce_sha256=admission.nonce_sha256, expires_unix=admission.expires_unix,
            execution_scope='offline_simulation',
            verified_receipts={name: ref.sha256 for name, ref in admission.receipts.items()})

    def domain(self, uart, plan, store_crc):
        self.events.append(('domain',))
        if self.fault in ('domain_protected', 'domain_store'):
            raise original.Failure('SYNTHETIC_PROTECTED_OR_STORE_MISMATCH')
        return dict(watchdog={}, protected={}, store_crc32=store_crc)

    def flash_crc(self, uart, offset, size, expected=None):
        self.events.append(('flash_crc', offset, size, expected))
        if self.fault == 'r9_crc':
            raise original.Failure('SYNTHETIC_R9_CRC_MISMATCH')
        return expected

    def write_image(self, uart, host, plan, image, out, store_crc, server_factory):
        name = 'f372' if image['sha256'] == plan['images']['f372']['sha256'] else 'f365'
        self.events.append(('write_image', name))
        if self.fault == 'transfer':
            raise original.Failure('SYNTHETIC_TRANSFER_BEFORE_ERASE_FAILED')
        uart.enable_writer(image)
        try:
            uart.mutate(original.ERASE_COMMAND)
            uart.mutate(original.write_command(image))
        finally:
            uart.disable_writer()
        return dict(image=image['sha256'], bytes=image['bytes'],
                    full_slot_crc32=image['full_slot_crc32'], byte_compare=True,
                    prewrite=dict(store_crc32=store_crc), postwrite=dict(store_crc32=store_crc),
                    tftp={'synthetic_only': True}, hardware_sha256_observed=None)

    def boot_written(self, uart, host, plan, name, previous_boot, **kwargs):
        self.events.append(('boot_written', name))
        if name == 'f372' and self.fault in ('candidate_boot_prompt', 'candidate_boot_no_prompt'):
            uart.prompt = self.fault == 'candidate_boot_prompt'
            raise original.Failure('SYNTHETIC_CANDIDATE_BOOT_FAILED')
        return identity(NEW_BOOT if name == 'f372' else RETURN_BOOT)

    def postboot(self, host, observed, out):
        self.events.append(('postboot',))
        if self.fault in ('postboot_prompt', 'postboot_no_prompt'):
            host.rig.last_uart.prompt = self.fault == 'postboot_prompt'
            return dict(status='FAIL', checks={'synthetic_check': False}, boot_id=observed['boot_id'], release_pass=False)
        return dict(status='PASS_CONTROL_ONLY', checks={'synthetic_check': True},
                    boot_id=observed['boot_id'], release_pass=False,
                    radio_client_gate=False, source_bound_traffic_gate=False,
                    cold_boot_repeatability_gate=False, protected_physical_readback_gate=False,
                    recovery_gate=False)

    def host_factory(self, plan, out):
        return FakeHost(plan, out, self)

    def uart_factory(self, plan, guard, out):
        self.last_uart = FakeUart(plan, guard, out, self)
        return self.last_uart

    def run(self, admission=None, **overrides):
        kwargs = dict(host_factory=self.host_factory, uart_factory=self.uart_factory,
                      server_factory=object, writer=self.writer,
                      admission_verifier=self.verifier, postboot_gate=self.postboot,
                      clock=lambda: NOW)
        kwargs.update(overrides)
        return self.core.run(PLAN, self.folder/'attempt', self.admission if admission is None else admission,
                             **kwargs)

    def run_fresh(self, admission=None, **overrides):
        """Use a new attempt directory while preserving synthetic receipt pins."""
        kwargs = dict(host_factory=self.host_factory, uart_factory=self.uart_factory,
                      server_factory=object, writer=self.writer,
                      admission_verifier=self.verifier, postboot_gate=self.postboot,
                      clock=lambda: NOW)
        kwargs.update(overrides)
        number = len(list(self.folder.glob('attempt-*')))
        return self.core.run(PLAN, self.folder/('attempt-'+str(number)),
                             self.admission if admission is None else admission, **kwargs)


class CoreDecisionTests(unittest.TestCase):
    def setUp(self):
        import f372_install_executor
        self.core = f372_install_executor
        self.temp = tempfile.TemporaryDirectory(prefix='core-case-', dir=OUTPUT)
        self.addCleanup(self.temp.cleanup)
        self.rig = Rig(self.temp.name, self.core)

    def test_concrete_host_configuration_adapter_uses_exact_private_contract(self):
        seen = []
        old = contract.read(contract.OLD_PLAN)
        def factory(plan, out):
            seen.append(copy.deepcopy(plan))
            fake = FakeHost(plan, out, self.rig)
            payload = old['boot_acceptance']['payload_sha256']
            def ssh(command, **kwargs):
                assert command.startswith("printf 'ready='")
                return ('ready=F361_READY\nslot=B\nsequence=2\nsha256='+payload+
                        '\nsource=journal\nactive_sha256='+payload+
                        '\nallow_hw=Y\nallow_program=Y\n').encode('ascii')
            backend = SimpleNamespace(execution_scope='offline_simulation', guard=lambda: True,
                                      network_guard=lambda: True, ssh=ssh)
            actual = self.core.Host(plan, out, backend=backend)
            self.assertEqual(actual.verify_configuration()['active_sha256'], payload)
            return fake
        result = self.rig.run(host_factory=factory)
        self.assertEqual(result['status'], 'PASS_F372_CONTROL_ONLY', result)
        self.assertEqual(seen[0]['boot_acceptance'], old['boot_acceptance'])
        self.assertNotIn('boot_acceptance', PLAN, 'immutable original F372 plan changed')

    def test_concrete_uart_adapter_requires_supplied_factory_and_routes_com4(self):
        with self.assertRaisesRegex(original.Failure, 'uart_backend_unavailable'):
            self.core.Uart(PLAN, lambda: True, self.rig.folder)
        calls = []
        class SerialFake:
            is_open = False
            port = None
            dtr = rts = True
            def open(self):
                calls.append(('open', self.port, self.dtr, self.rts))
                self.is_open = True
            def close(self):
                self.is_open = False
        serial = SerialFake()
        uart = self.core.Uart(PLAN, lambda: True, self.rig.folder,
                              serial_factory=lambda: serial, execution_scope='offline_simulation')
        class ThreadFake:
            def __init__(self, **kwargs):
                self.started = False
            def start(self):
                self.started = True
        with patch.object(original.base.threading, 'Thread', ThreadFake):
            uart.open()
        self.assertEqual(calls, [('open', 'COM4', False, False)])
        self.assertEqual(serial.port, 'COM4')
        serial.close()

    def test_tracked_uart_rejects_wrong_geometry_before_inner_mutation(self):
        raw = FakeUart(PLAN, lambda: True, self.rig.folder, self.rig)
        tracked = self.core._TrackedUart(raw)
        commands = ('spi_flash erase 0x00040000 0x005e0000',
                    'spi_flash write 0x007e0000 0x83000000 0x007a0000',
                    'spi_flash write 0x007e0000 0x83000000 0x00000001',
                    'spi_flash write 0x007e0000 0x83000000 0x00522001',
                    'saveenv', 'bootm 0x83000000')
        for command in commands:
            with self.subTest(command=command):
                with self.assertRaises(Exception):
                    tracked.mutate(command)
                self.assertEqual(self.effect_counts()['mutate'], 0)

    def test_tracked_uart_rejects_ambiguous_receipt_with_fresh_prompt(self):
        raw = FakeUart(PLAN, lambda: True, self.rig.folder, self.rig)
        raw.mutate = lambda command: reply(command, ['Erase: wrong region'])
        tracked = self.core._TrackedUart(raw)
        with self.assertRaises(Exception):
            tracked.mutate(original.ERASE_COMMAND)
        self.assertTrue(tracked.ambiguous_write)

    def effect_counts(self, rig=None):
        events = (rig or self.rig).events
        return {name: sum(event[0] == name for event in events)
                for name in ('host_constructed', 'uart_constructed', 'uart_open',
                             'reboot', 'write_image', 'mutate', 'boot_written')}

    def test_typed_invalid_admission_refuses_before_adapter_construction(self):
        for admission in (True, {}, 'SYNTHETIC_ONLY'):
            with self.subTest(admission_type=type(admission).__name__):
                result = self.rig.run_fresh(admission)
                self.assertEqual(result['status'], 'NO_GO_ADMISSION')
                self.assertEqual(self.effect_counts()['host_constructed'], 0)
                self.assertEqual(self.effect_counts()['uart_constructed'], 0)

    def test_default_backend_or_missing_verifier_refuses_before_effects(self):
        for override in ({'host_factory': None}, {'uart_factory': None}, {'admission_verifier': None}):
            with self.subTest(override=next(iter(override))):
                result = self.rig.run_fresh(**override)
                self.assertEqual(result['status'], 'NO_GO_ADMISSION')
                self.assertEqual(self.effect_counts()['host_constructed'], 0)

    def test_scope_plan_expiry_or_source_pin_drift_refuses_before_effects(self):
        variants = [replace(self.rig.admission, scope_sha256='0'*64),
                    replace(self.rig.admission, plan_sha256='0'*64),
                    replace(self.rig.admission, expires_unix=NOW-1)]
        wrong = dict(self.rig.admission.source_pins)
        wrong[str(Path(self.core.__file__).resolve())] = '0'*64
        variants.append(replace(self.rig.admission, source_pins=wrong))
        for admission in variants:
            with self.subTest(admission=repr(admission)[:80]):
                result = self.rig.run_fresh(admission)
                self.assertEqual(result['status'], 'NO_GO_ADMISSION')
                self.assertEqual(self.effect_counts()['host_constructed'], 0)

    def test_receipt_drift_is_really_hashed_and_refused_before_io(self):
        ref = self.rig.receipts['recovery']
        Path(ref.path).write_text('{"synthetic_test_only":true,"changed":true}\n', encoding='ascii')
        result = self.rig.run()
        self.assertEqual(result['status'], 'NO_GO_ADMISSION', result)
        self.assertEqual(self.effect_counts()['host_constructed'], 0)
        self.assertEqual(result['error'], 'gate_evidence_drift')

    def test_receipt_loss_after_reboot_prevents_erase(self):
        previous = self.rig.flash_crc
        def lose_receipt(*args):
            result = previous(*args)
            ref = self.rig.receipts['uart_nonce']
            Path(ref.path).write_text('{"synthetic_test_only":true,"changed":true}\n', encoding='ascii')
            return result
        self.rig.writer.flash_crc = lose_receipt
        result = self.rig.run()
        self.assertEqual(result['status'], 'FAILED_BEFORE_ERASE_BASELINE_UNCHANGED', result)
        self.assertEqual(self.effect_counts()['mutate'], 0)
        self.assertTrue(result['retain_lease_required'])

    def test_nonce_binding_loss_after_reboot_prevents_erase(self):
        previous = self.rig.flash_crc
        def lose_binding(*args):
            result = previous(*args)
            self.rig.fault = 'admission_binding'
            return result
        self.rig.writer.flash_crc = lose_binding
        result = self.rig.run()
        self.assertEqual(result['status'], 'FAILED_BEFORE_ERASE_BASELINE_UNCHANGED', result)
        self.assertEqual(self.effect_counts()['mutate'], 0)
        self.assertTrue(result['retain_lease_required'])

    def test_synthetic_control_pass_never_claims_client_or_release(self):
        result = self.rig.run()
        self.assertEqual(result['status'], 'PASS_F372_CONTROL_ONLY', result)
        counts = self.effect_counts()
        self.assertEqual((counts['reboot'], counts['write_image'], counts['mutate']), (1, 1, 2))
        self.assertFalse(result['release_pass'])
        self.assertFalse(result.get('radio_client_gate', False))
        self.assertFalse(result.get('source_bound_traffic_gate', False))
        self.assertFalse(result.get('cold_boot_repeatability_gate', False))
        crc = ('flash_crc', contract.LIVE, contract.SLOT, PLAN['images']['f367r9']['full_slot_crc32'])
        self.assertIn(crc, self.rig.events)
        self.assertLess(self.rig.events.index(crc), self.rig.events.index(('write_image', 'f372')))

    def test_baseline_admission_boot_watchdog_store_guard_failures_never_reboot(self):
        for fault in ('admission_binding', 'initial_binding', 'baseline_boot', 'watchdog', 'baseline_store', 'guard'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix='core-case-', dir=OUTPUT) as folder:
                rig = Rig(folder, self.core, fault)
                result = rig.run()
                self.assertNotEqual(result['status'], 'PASS_F372_CONTROL_ONLY')
                counts = self.effect_counts(rig)
                self.assertEqual((counts['reboot'], counts['mutate']), (0, 0))

    def test_physical_domain_or_current_full_r9_crc_mismatch_never_writes(self):
        for fault in ('domain_protected', 'domain_store', 'r9_crc'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix='core-case-', dir=OUTPUT) as folder:
                rig = Rig(folder, self.core, fault)
                result = rig.run()
                self.assertEqual(result['status'], 'FAILED_BEFORE_ERASE_BASELINE_UNCHANGED', result)
                counts = self.effect_counts(rig)
                self.assertEqual((counts['reboot'], counts['mutate']), (1, 0))

    def test_transfer_failure_before_erase_never_writes_or_reboots_again(self):
        self.rig.fault = 'transfer'
        result = self.rig.run()
        self.assertEqual(result['status'], 'FAILED_BEFORE_ERASE_BASELINE_UNCHANGED', result)
        counts = self.effect_counts()
        self.assertEqual((counts['reboot'], counts['mutate'], counts['boot_written']), (1, 0, 0))

    def test_ambiguous_erase_or_write_never_restores_or_resets(self):
        for fault, mutations in (('erase_timeout', 1), ('write_timeout', 2)):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix='core-case-', dir=OUTPUT) as folder:
                rig = Rig(folder, self.core, fault)
                result = rig.run()
                self.assertEqual(result['status'], 'STOP_UNCERTAIN_NO_AUTOMATIC_WRITE', result)
                counts = self.effect_counts(rig)
                self.assertEqual((counts['reboot'], counts['write_image'], counts['mutate'], counts['boot_written']),
                                 (1, 1, mutations, 0))
                self.assertTrue(result['retain_lease_required'])

    def test_candidate_failure_with_fresh_prompt_returns_exact_f365_once(self):
        for fault in ('candidate_boot_prompt', 'postboot_prompt'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix='core-case-', dir=OUTPUT) as folder:
                rig = Rig(folder, self.core, fault)
                result = rig.run()
                self.assertEqual(result['status'], 'FAILED_F372_WITH_EXACT_F365_RETURN', result)
                self.assertEqual([event for event in rig.events if event[0] == 'write_image'],
                                 [('write_image', 'f372'), ('write_image', 'f365')])
                self.assertEqual(self.effect_counts(rig)['reboot'], 1)
                self.assertFalse(result['release_pass'])

    def test_candidate_failure_without_prompt_never_resets_or_rewrites(self):
        for fault in ('candidate_boot_no_prompt', 'postboot_no_prompt'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix='core-case-', dir=OUTPUT) as folder:
                rig = Rig(folder, self.core, fault)
                result = rig.run()
                self.assertEqual(result['status'], 'STOP_NO_FRESH_PROMPT_NO_RESET', result)
                counts = self.effect_counts(rig)
                self.assertEqual((counts['reboot'], counts['write_image'], counts['mutate']), (1, 1, 2))
                self.assertTrue(result['retain_lease_required'])

    def test_containment_failure_retains_lease(self):
        for fault in ('containment', 'uart_containment'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory(prefix='core-case-', dir=OUTPUT) as folder:
                rig = Rig(folder, self.core, fault)
                result = rig.run()
                self.assertNotEqual(result['status'], 'PASS_F372_CONTROL_ONLY')
                self.assertTrue(result['retain_lease_required'])

    def test_repeated_attempt_claim_never_constructs_second_adapter(self):
        first = self.rig.run()
        self.assertEqual(first['status'], 'PASS_F372_CONTROL_ONLY', first)
        before = self.effect_counts()
        with self.assertRaisesRegex(original.Failure, 'new_empty_evidence_directory_required'):
            self.rig.run()
        self.assertEqual(self.effect_counts(), before)


def main():
    global PLAN, OUTPUT
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--memoize-frozen-source-hashes', action='store_true',
                        help='After real plan validation, use its verified original-source hash map in decision tests')
    args = parser.parse_args()
    OUTPUT = args.output.resolve()
    OUTPUT.mkdir(parents=True, exist_ok=False)
    PLAN = contract.load_plan(PLAN_PATH, PLAN_SHA)
    suite = unittest.TestSuite()
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(OriginalWriterTests))
    suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(CoreDecisionTests))
    actual_sha = contract.sha
    actual_load = contract.load_plan
    def verified_snapshot_sha(path):
        # Only the sealed original-source map is substituted. Plan/admission
        # receipts/new core source pins retain real hashing. This is a test
        # performance option and never changes the executor or hardware guard.
        value = PLAN['sources'].get(str(path))
        return value if value is not None else actual_sha(path)
    context = patch.object(contract, 'sha', side_effect=verified_snapshot_sha) \
        if args.memoize_frozen_source_hashes else nullcontext()
    def verified_plan_snapshot(path, digest):
        if Path(path).resolve() != PLAN_PATH.resolve() or digest != PLAN_SHA:
            raise ValueError('plan_sha256')
        return copy.deepcopy(PLAN)
    load_context = patch.object(contract, 'load_plan', side_effect=verified_plan_snapshot) \
        if args.memoize_frozen_source_hashes else nullcontext()
    with context, load_context:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
    # Validate all original sources again from disk after the synthetic cases.
    # A changed file cannot be reported as a passing source qualification.
    actual_load(PLAN_PATH, PLAN_SHA)
    pins = {str(path.resolve()): sha(path) for path in
            (Path(__file__), Path(original.__file__), Path(contract.__file__),
             ROOT/'tools/f372_install_executor.py', ROOT/'tools/f372_postboot_gate.py', PLAN_PATH)}
    summary = dict(schema='openmitrastar.f372-install-executor-tests/v1',
                   status='PASS_OFFLINE_FAULT_TESTS' if result.wasSuccessful() else 'FAIL_OFFLINE_FAULT_TESTS',
                   generated_at_utc=datetime.now(timezone.utc).isoformat(),
                   tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
                   plan_sha256=PLAN_SHA, candidate_sha256=PLAN['images']['f372']['sha256'],
                   source_pins=pins, synthetic_receipts_only=True,
                   native_adapters_constructed=False, hardware_actions=False,
                   physical_acceptance=False, release_pass=False,
                   original_source_hashes_repeated_from_prevalidated_snapshot=args.memoize_frozen_source_hashes,
                   repeated_plan_validation_uses_prevalidated_snapshot=args.memoize_frozen_source_hashes,
                   real_original_source_hash_validation_before_and_after=True,
                   original_writer_scope='Original write_image and response parser; transfer/domain/readback effects replaced',
                   core_writer_scope='Synthetic writer invokes wrapped UART mutations with original receipt parser; no physical effects')
    with (OUTPUT/'result.json').open('x', encoding='ascii') as stream:
        stream.write(json.dumps(summary, indent=2)+'\n')
    print(json.dumps({'status': summary['status'], 'tests': result.testsRun,
                      'output': str(OUTPUT), 'hardware_actions': False}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
