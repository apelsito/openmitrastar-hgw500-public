"""Host control-flow tests with fake devices; no physical/RF validation."""
from contextlib import ExitStack
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import f366_acquisition_executor as gate


class FakeUart:
    def __init__(self, plan, guard, out):
        self.write_in_flight = False
        self.erase_requested = False
        self.write_requested = False
        self.reset_times = []
        self.failed = None
        self.fatal = False
        self.prompt = False
        self.serial_recovery_record = {}
    def open(self): pass
    def has_prompt(self): return self.prompt
    def stop_autoboot(self, seconds): pass
    def wait_prompt(self, seconds):
        self.prompt = True
        self.reset_times.append(1)
    def close(self): return dict(reader_stopped=True, port_closed=True, reader_error=None)


class FakeHost:
    mode = 'pass'
    def __init__(self, plan, out): self.plan = plan
    def guard(self): return True
    def initial_binding(self, identity): return True
    def identity(self, name): return dict(boot_id=name)
    def watchdog_inactive(self): return dict(ready_for_arm=1, device_opened=0)
    def verify_store(self): return dict(sha256='store')
    def verify_configuration(self): return dict(sequence=2)
    def backup_reference(self): return dict(fresh_physical_dump=False)
    def reboot_to_prompt(self, uart, software_recovery=False): uart.prompt=True
    def pending(self): return dict(status='PASS_F366_PENDING_MANAGEMENT')
    def components(self): return dict(status='PASS')
    def verify_ethernet(self): return dict(status='PASS')
    def verify_thermal_disabled(self): return dict(enabled=False)
    def platform(self, name, out): return dict(status='PASS', checks=27)
    def contain(self): return True
    def diagnostic(self, token, uart, output):
        uart.prompt = True
        uart.reset_times.append(2)
        if self.mode == 'diagnostic-fail':
            raise gate.Failure('intentional_fake_fault')
        return dict(status='PASS_CAPTURED_DIAGNOSTIC_TELEMETRY', transport_exit_code=0, watchdog_arm_marker=1)


def execute(mode):
    writes = []
    plan = dict(images={'f365': {'name': 'f365', 'full_slot_crc32': 'old'}, 'f366': {'name': 'f366'}}, store={'crc32': 'store'})
    def write(uart, host, plan, image, out, crc, server):
        writes.append(image['name'])
        uart.erase_requested = True
        if mode == 'ambiguous-write' and image['name'] == 'f366':
            uart.write_in_flight = True
            raise gate.Failure('intentional_fake_ambiguous_write')
        uart.write_requested = True
        return {'image': image['name']}
    def boot(uart, host, plan, name, previous, prefix_only=False):
        uart.prompt = False
        return {'boot_id': name}
    class Host(FakeHost): pass
    Host.mode = mode
    with tempfile.TemporaryDirectory() as folder, ExitStack() as stack:
        output = Path(folder)
        stack.enter_context(patch.object(gate.writer, 'write_image', write))
        stack.enter_context(patch.object(gate.writer, 'boot_written', boot))
        stack.enter_context(patch.object(gate.writer, 'clear_pending_break', return_value=True))
        for module, name, value in ((gate.writer.base, 'inactive_hardware', {}), (gate.writer, 'selector', None), (gate.writer, 'protected', {}), (gate.writer, 'flash_crc', 'crc'), (gate.writer, 'domain', {})):
            stack.enter_context(patch.object(module, name, return_value=value))
        code = gate.run(plan, output, host_factory=Host, uart_factory=FakeUart)
        return code, json.loads((output/'result.json').read_text()), writes, (output/'failure-before-recovery.json').exists()


class AcquisitionTests(unittest.TestCase):
    def test_success_always_restores_f365_once(self):
        code, result, writes, snapshot = execute('pass')
        self.assertEqual(code, 0)
        self.assertEqual(writes, ['f366', 'f365'])
        self.assertTrue(snapshot and result['baseline_returned'])
        self.assertTrue(result['watchdog_reset_observed'])
        self.assertFalse(result['provider_unload_attempted'])
        self.assertFalse(result['retain_lease_required'])

    def test_diagnostic_fault_preserves_failure_and_returns(self):
        code, result, writes, snapshot = execute('diagnostic-fail')
        self.assertEqual(code, 1)
        self.assertEqual(writes, ['f366', 'f365'])
        self.assertTrue(snapshot and result['baseline_returned'])
        self.assertEqual(result['error'], 'intentional_fake_fault')
        self.assertFalse(result['provider_unload_attempted'])

    def test_ambiguous_write_never_starts_second_write(self):
        code, result, writes, snapshot = execute('ambiguous-write')
        self.assertEqual(code, 1)
        self.assertEqual(writes, ['f366'])
        self.assertTrue(snapshot)
        self.assertTrue(result['flash_command_in_flight'])
        self.assertTrue(result['retain_lease_required'])
        self.assertEqual(result['diagnostic_attempts'], 0)

    def test_pending_gate_rejects_old_qdrv_and_duplicate(self):
        good = b'boot=ready\nradio2=ENABLED\nbridge2=1\nqdrv=0\nprovider=0\nwifi0=0\nowner=0\nsocket=0\nfatal=0\n'
        self.assertEqual(gate.pending_response(good)['status'], 'PASS_F366_PENDING_MANAGEMENT')
        for bad in (good.replace(b'qdrv=0', b'qdrv=1'), good+b'qdrv=0\n', good.replace(b'owner=0', b'owner=1')):
            with self.assertRaises((gate.Failure, ValueError)):
                gate.pending_response(bad)


if __name__ == '__main__':
    unittest.main()
