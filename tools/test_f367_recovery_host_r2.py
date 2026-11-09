"""Offline: inherited production reader over explicitly fake serial only."""
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import argparse
import hashlib
import json
import queue
import tempfile
import threading
import time
import unittest

import f367_recovery_host_r2 as recovery
import f367_uart_epoch_r2 as epochs
import f362_recovery_delta as old

LINUX = b'Linux version 5.10.260-openmitrastar-radiohw test\n'
RESET = b'Info: Quantenna U-Boot version:v36.7.0.30\n'


def eventually(predicate, timeout=2):
    until = time.monotonic() + timeout
    while not predicate() and time.monotonic() < until:
        time.sleep(.002)
    if not predicate():
        raise AssertionError('fake reader did not reach expected state')


def plan():
    paths = [Path(recovery.__file__).resolve(), Path(epochs.__file__).resolve()]
    return dict(host_recovery_revision=2, bootargs='', protected=dict(parts=[]),
                images={'f365': dict(path='SYNTHETIC-NOT-A-FIRMWARE.bin', bytes=1)},
                sources={str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths})


class FakeSerial:
    is_open = False
    out_waiting = 0
    in_waiting = 4096

    def __init__(self):
        self.frames = queue.Queue()
        self.reads = 0
        self.writes = []
        self.auto_return = True
        self.short_b = False
        self.write_entered = threading.Event()
        self.release_write = threading.Event()
        self.block_auto = False

    def open(self):
        self.is_open = True

    def close(self):
        self.is_open = False

    def feed(self, data):
        for offset in range(0, len(data), 4096):
            self.frames.put(data[offset:offset + 4096])

    def read(self, size):
        self.reads += 1
        try:
            value = self.frames.get(timeout=.01)
        except queue.Empty:
            return b''
        if isinstance(value, Exception):
            raise value
        assert len(value) <= size
        return value

    def write(self, data):
        if data == b' \r' and self.block_auto:
            self.write_entered.set()
            if not self.release_write.wait(1):
                raise RuntimeError('fake auto-writer release missing')
        self.writes.append(data)
        if data == b'b':
            if self.short_b:
                return 0
            if self.auto_return:
                self.feed(b'sysrq: Resetting\n' + RESET + b'Hit any key to stop autoboot: 3\n')
        elif data == b' \r' and self.auto_return:
            self.feed(b'topaz> ')
        return len(data)


@contextmanager
def fixture(initial=LINUX, long=False):
    with tempfile.TemporaryDirectory() as folder:
        uart = recovery.Uart(plan(), lambda: True, Path(folder))
        raw = FakeSerial()
        # Same two read observers and new gate, with the native endpoint replaced
        # explicitly. Never invoke the captured native_serial_factory closure.
        def factory():
            serial = recovery.capture.reset.ObservedSerial(raw, uart.r3_observer)
            serial = recovery.capture.reset.ObservedSerial(serial, uart.semantic)
            return recovery.SerialGate(serial, uart)
        uart.factory = factory
        uart.open()
        uart.kernel_handoff_start = 0
        raw.feed(initial)
        if long:
            raw.feed((b'STATUS ' + b'1' * 3993 + b'\n') * 127)
        expected = len(initial) + (4001 * 127 if long else 0)
        eventually(lambda: uart.total == expected)
        try:
            yield uart, raw
        finally:
            raw.release_write.set()
            uart.close()


class RecoveryTests(unittest.TestCase):
    def run_recovery(self, uart, *, sleep_hook=None, guard=lambda: True, fail_clear=False):
        actions = []
        now = [0.]
        def drive(port, enabled):
            actions.append(('break', enabled))
            if not enabled and fail_clear:
                raise recovery.base.Failure('break_api_failed')
        def sleep(seconds):
            actions.append(('sleep', seconds))
            now[0] += seconds
            if sleep_hook:
                sleep_hook(seconds, now)
        try:
            result = recovery.serial_reboot_to_prompt(
                SimpleNamespace(guard=guard), uart, drive, sleep, lambda: now[0])
            return result, actions
        finally:
            self.actions = actions

    def test_long_continuous_route_and_unchanged_command_window(self):
        with fixture(long=True) as (uart, raw):
            self.assertGreater(uart.total, 507866)
            self.assertEqual(len(uart.buffer), 262144)
            self.assertIs(recovery.Uart.since, recovery.base.Capture.since)
            self.assertIs(recovery.Uart._read, recovery.base.Capture._read)
            with self.assertRaisesRegex(recovery.base.Failure, 'uart_window_overflow'):
                uart.since(0)
            uart.stop_autoboot(120)
            before_reads = raw.reads
            result, actions = self.run_recovery(uart)
            self.assertTrue(result['new_prompt_and_dispatch'])
            self.assertEqual(actions, [('break', True), ('sleep', .600),
                                       ('break', False), ('sleep', .150)])
            self.assertEqual(raw.writes, [b'b', b' \r'])
            self.assertGreater(raw.reads, before_reads)
            self.assertEqual(result['reader_ack'], 1)
            self.assertEqual(result['epoch']['linux_offset'], 0)
            self.assertEqual(uart._recovery_mode, 'idle')
            records = [json.loads(line) for line in
                       (uart.out / 'serial-recovery-r2.jsonl').read_text().splitlines()]
            self.assertEqual([r['stage'] for r in records],
                             ['admitted', 'before-break', 'before-b', 'new-prompt-and-dispatch'])
            self.assertFalse(records[0]['record']['break_attempted'])
            self.assertFalse(records[2]['record']['b_written'])
            self.assertTrue(uart.has_prompt())
            with self.assertRaises(recovery.base.Failure):
                self.run_recovery(uart)
            self.assertEqual(raw.writes.count(b'b'), 1)

    def test_silent_reader_ack_cancels_active_interceptor(self):
        with fixture() as (uart, raw):
            uart.stop_autoboot(120)
            total = uart.total
            proof = uart.quiesce_recovery()
            self.assertTrue(proof['eligible'])
            self.assertEqual(uart.total, total)
            self.assertFalse(uart.autoboot)
            self.assertEqual(uart._recovery_mode, 'exclusive')
            self.assertEqual(raw.writes, [])
            for action in (lambda: uart.stop_autoboot(120),
                           lambda: setattr(uart, 'autoboot', True),
                           lambda: setattr(uart, 'write_in_flight', True),
                           lambda: uart.serial.write(b'forbidden-command\r')):
                with self.assertRaises(recovery.base.Failure):
                    action()
            self.assertEqual(raw.writes, [])

    def test_outstanding_auto_writer_must_finish_before_ack(self):
        with fixture() as (uart, raw):
            raw.auto_return = False
            raw.block_auto = True
            uart.stop_autoboot(120)
            raw.feed(b'Hit any key to stop autoboot: 3\n')
            self.assertTrue(raw.write_entered.wait(1))
            done = threading.Event()
            result = []
            def request():
                try:
                    result.append(uart.quiesce_recovery())
                except Exception as error:
                    result.append(error)
                finally:
                    done.set()
            thread = threading.Thread(target=request)
            thread.start()
            self.assertFalse(done.wait(.03))
            self.assertEqual(uart._reader_ack, 0)
            raw.release_write.set()
            self.assertTrue(done.wait(2))
            thread.join()
            self.assertEqual(raw.writes, [b' \r'])
            self.assertEqual(uart._reader_ack, 1)

    def test_selected_old_auto_write_cannot_cross_rearm_but_new_prompt_can(self):
        with fixture() as (uart, raw):
            selected = threading.Event()
            release = threading.Event()
            class PausedSet(set):
                def add(self, value):
                    selected.set()
                    if not release.wait(1):
                        raise RuntimeError('fake selection release missing')
                    return super().add(value)
            uart.stop_autoboot(120)
            uart.auto_seen = PausedSet()
            raw.feed(b'Hit any key to stop autoboot: 3\n')
            self.assertTrue(selected.wait(1))
            done = threading.Event()
            errors = []
            results = []
            def request():
                try:
                    results.append(self.run_recovery(uart))
                except Exception as error:
                    errors.append(error)
                finally:
                    done.set()
            thread = threading.Thread(target=request)
            thread.start()
            eventually(lambda: uart._recovery_mode == 'quiescing')
            self.assertEqual(uart._reader_ack, 0)
            self.assertFalse(uart.serial_recovery_record.get('break_attempted'))
            release.set()
            self.assertTrue(done.wait(2))
            thread.join()
            self.assertEqual(errors, [])
            self.assertTrue(results[0][0]['new_prompt_and_dispatch'])
            self.assertEqual(raw.writes, [b'b', b' \r'])
            self.assertEqual(uart._suppressed_auto_writes, 1)
            self.assertEqual(uart._reader_ack, 1)
            self.assertTrue(uart.has_prompt())

    def test_admission_failures_have_no_break_or_serial_write(self):
        cases = ['lease', 'reader', 'flash', 'handoff', 'reset', 'prompt',
                 'tx_queue', 'stopped', 'closed', 'missing_linux', 'partial', 'oversize']
        for case in cases:
            with self.subTest(case=case), fixture() as (uart, raw):
                guard = lambda: True
                if case == 'lease': guard = lambda: False
                if case == 'reader': uart.failed = 'uart_reader_failed'
                if case == 'flash': uart.write_in_flight = True
                if case == 'handoff': uart.kernel_handoff_start = None
                if case == 'tx_queue': raw.out_waiting = 1
                if case == 'stopped':
                    uart.stop.set(); uart.thread.join(1)
                if case == 'closed': uart.serial.close()
                if case == 'missing_linux': uart.kernel_handoff_start = uart.total
                payloads = {'reset': RESET, 'prompt': b'topaz> ',
                            'partial': b'U-Boot ', 'oversize': b'x' * 8200}
                if case in payloads:
                    target = uart.total + len(payloads[case])
                    raw.feed(payloads[case]); eventually(lambda: uart.total == target)
                with self.assertRaises(recovery.base.Failure):
                    self.run_recovery(uart, guard=guard)
                self.assertEqual(self.actions, [])
                self.assertEqual(raw.writes, [])

    def test_reader_that_does_not_ack_cannot_admit(self):
        with fixture() as (uart, raw):
            # Actual live reader stalled after selecting an auto event.
            selected = threading.Event(); release = threading.Event()
            class PausedSet(set):
                def add(self, value):
                    selected.set(); release.wait(1); return super().add(value)
            uart.stop_autoboot(120); uart.auto_seen = PausedSet()
            raw.feed(b'Hit any key to stop autoboot: 3\n')
            self.assertTrue(selected.wait(1))
            try:
                with self.assertRaisesRegex(recovery.base.Failure, 'recovery_reader_ack_timeout'):
                    uart.quiesce_recovery(timeout=.03)
                self.assertEqual(raw.writes, [])
            finally:
                release.set()
            eventually(lambda: uart._suppressed_auto_writes == 1)

    def test_reset_prompt_and_reader_error_during_break_never_send_b(self):
        for event in ('reset', 'prompt', 'reader', 'new_linux'):
            with self.subTest(event=event), fixture() as (uart, raw):
                def inject(seconds, now):
                    if seconds != .600: return
                    if event == 'reader':
                        raw.frames.put(RuntimeError('synthetic-reader-failure'))
                        eventually(lambda: uart.failed is not None)
                    else:
                        data = {'reset': RESET, 'prompt': b'topaz> ', 'new_linux': LINUX}[event]
                        target = uart.total + len(data)
                        raw.feed(data); eventually(lambda: uart.total == target)
                with self.assertRaises(recovery.base.Failure):
                    self.run_recovery(uart, sleep_hook=inject)
                self.assertEqual([a for a in self.actions if a[0] == 'break'],
                                 [('break', True), ('break', False)])
                self.assertEqual(raw.writes, [])

    def test_clear_failure_and_expired_four_seconds_never_send_b(self):
        for case in ('clear', 'deadline', 'lease_lost'):
            with self.subTest(case=case), fixture() as (uart, raw):
                calls = [0]
                def guard():
                    calls[0] += 1
                    return not (case == 'lease_lost' and calls[0] == 3)
                def delay(seconds, now):
                    if case == 'deadline': now[0] += 4
                with self.assertRaises(recovery.base.Failure):
                    self.run_recovery(uart, fail_clear=case == 'clear',
                                      sleep_hook=delay, guard=guard)
                self.assertEqual(raw.writes, [])
                self.assertTrue(uart.serial_recovery_record['break_attempted'])

    def test_failed_receipt_prevents_action(self):
        with fixture() as (uart, raw), patch.object(uart, 'recovery_receipt', side_effect=OSError):
            with self.assertRaises(OSError): self.run_recovery(uart)
            self.assertEqual(self.actions, [])
            self.assertEqual(raw.writes, [])

    def test_no_second_reader_or_reopen_can_reconstruct_an_epoch(self):
        with fixture() as (uart, raw):
            with self.assertRaisesRegex(recovery.base.Failure, 'recovery_wrong_reader'):
                uart.serial.read(1)
            self.assertFalse(uart.epoch.proof(0)['eligible'])
            with self.assertRaises(recovery.base.Failure): self.run_recovery(uart)
            self.assertEqual(raw.writes, [])
            with self.assertRaisesRegex(recovery.base.Failure, 'continuous_capture_cannot_reopen'):
                uart.open()

    def test_short_b_is_not_retried(self):
        with fixture() as (uart, raw):
            raw.short_b = True
            with self.assertRaisesRegex(recovery.base.Failure, 'sysrq_short_write'):
                self.run_recovery(uart)
            with self.assertRaises(recovery.base.Failure): self.run_recovery(uart)
            self.assertEqual(raw.writes, [b'b'])
            self.assertEqual(uart._recovery_mode, 'failed')

    def test_old_modules_unchanged_and_normal_host_reboot_inherited(self):
        self.assertIs(recovery.Host.campaign, recovery.qualified.Host.campaign)
        self.assertIs(recovery.Host.guard, recovery.qualified.Host.guard)
        self.assertIs(recovery.Host.initial_binding, recovery.qualified.Host.initial_binding)
        self.assertIs(recovery.Uart.mutate, recovery.capture.Uart.mutate)
        with patch.object(recovery.qualified.Host, 'reboot_to_prompt', return_value='normal') as method:
            host = recovery.Host.__new__(recovery.Host)
            self.assertEqual(host.reboot_to_prompt(object()), 'normal')
            method.assert_called_once()

    def test_factory_requires_explicit_revision_and_hash(self):
        for key in ('revision', 'hash'):
            candidate = plan()
            if key == 'revision': candidate.pop('host_recovery_revision')
            else: candidate['sources'] = {}
            with self.assertRaises(recovery.base.Failure):
                recovery.Uart(candidate, lambda: True, Path('.'))


class EpochTests(unittest.TestCase):
    def test_every_chunk_split_same_offsets_and_no_substrings(self):
        payload = b'echo Linux version 5.10.260-openmitrastar-radiohw\n' + LINUX + b'status=ok\n'
        for split in range(1, len(payload)):
            epoch = epochs.Epoch(); epoch.start()
            epoch.feed(payload[:split]); epoch.feed(payload[split:])
            self.assertTrue(epoch.proof(0)['eligible'])
            self.assertEqual(epoch.linux_count, 1)
            self.assertEqual(epoch.linux_offset, payload.index(LINUX))

    def test_reset_prompt_and_close_are_not_revived_by_later_linux(self):
        for invalidator in (RESET, b'topaz>\n', b'ZHAL>\n'):
            epoch = epochs.Epoch(); epoch.start(); epoch.feed(LINUX)
            epoch.feed(invalidator + LINUX)
            self.assertFalse(epoch.proof(0)['eligible'])
            handoff = epoch.total
            epoch.feed(LINUX)
            self.assertTrue(epoch.proof(handoff)['eligible'])
        for cause in ('reader_failed', 'capture_closed'):
            epoch = epochs.Epoch(); epoch.start(); epoch.feed(LINUX)
            epoch.invalidate(cause); handoff = epoch.total; epoch.feed(LINUX)
            self.assertFalse(epoch.proof(handoff)['eligible'])
            epoch.start(); self.assertFalse(epoch.proof(handoff)['eligible'])
        epoch = epochs.Epoch(); epoch.start(); epoch.feed(LINUX + LINUX)
        self.assertFalse(epoch.proof(0)['eligible'])

    def test_oversized_complete_and_split_frames_fail_closed(self):
        for chunks in ((b'x' * 9000 + b'\n' + LINUX,),
                       (b'x' * 8200, LINUX, b'\n', LINUX)):
            epoch = epochs.Epoch(); epoch.start(); epoch.feed(LINUX)
            for chunk in chunks: epoch.feed(chunk)
            self.assertLessEqual(len(epoch.pending), epochs.MAX_LINE + 1)
            self.assertFalse(epoch.proof(0)['eligible'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument('--result', type=Path, required=True)
    args = parser.parse_args()
    if args.result.exists(): parser.error('new result path required')
    suite = unittest.defaultTestLoader.loadTestsFromModule(__import__(__name__))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    args.result.write_text(json.dumps(dict(
        schema='openmitrastar.f367-host-recovery-tests/v2',
        status='PASS_OFFLINE' if result.wasSuccessful() else 'FAIL_OFFLINE',
        tests=result.testsRun, failures=len(result.failures), errors=len(result.errors),
        hardware_actions=False, firmware_changed=False,
        serial_endpoint='explicit FakeSerial; original inherited reader'), indent=2) + '\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
