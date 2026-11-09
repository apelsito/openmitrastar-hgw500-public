"""Versioned host-only recovery adapter; no device/network I/O on construction.

Use both factories with the qualified campaign pipeline from the FIRST byte of
a NEW capture. There is no execute CLI and no recovery of a closed capture.
The native reader, semantic capture, redactors, command ring, flash vocabulary,
R9 host/identity/lease checks, clock capture and normal SSH reboot are inherited.
"""
from pathlib import Path
import hashlib
import json
import os
import re
import threading
import time

import f336_wdt_ram_executor as base
import f367_uart_capture_r2 as capture
import f367r9_campaign_worker as qualified
import f367_uart_epoch_r2 as epochs
from f362_uart_reboot_probe import native_break

require = base.require
REVISION = 2
QUIESCE_SECONDS = 2.0


def validate_binding(plan):
    require(plan.get('host_recovery_revision') == REVISION, 'recovery_revision_binding')
    for path in (Path(__file__).resolve(), Path(epochs.__file__).resolve()):
        require(plan.get('sources', {}).get(str(path)) ==
                hashlib.sha256(path.read_bytes()).hexdigest(), 'recovery_source_binding')


class SerialGate:
    """One transparent read path and a shared exclusion gate for EVERY write."""
    __slots__ = ('_inner', '_uart')

    def __init__(self, inner, uart):
        object.__setattr__(self, '_inner', inner)
        object.__setattr__(self, '_uart', uart)

    def __getattr__(self, name):
        return getattr(self._inner, name)

    def __setattr__(self, name, value):
        if name in self.__slots__:
            object.__setattr__(self, name, value)
        else:
            setattr(self._inner, name, value)

    def read(self, size):
        uart = self._uart
        with uart._recovery_cv:
            if threading.current_thread() is not uart.thread:
                uart.epoch.invalidate('unexpected_reader')
                raise base.Failure('recovery_wrong_reader')
            # Entry into the NEXT read proves the previous _read iteration,
            # including every automatic write it selected, has completed.
            if uart._recovery_mode == 'quiescing':
                uart._autoboot = False
                uart._reader_ack = uart._recovery_request
                uart._recovery_mode = 'exclusive'
                uart._recovery_cv.notify_all()
        try:
            data = self._inner.read(size)
            with uart._recovery_cv:
                uart.epoch.feed(data)
            return data
        except Exception:
            with uart._recovery_cv:
                uart.epoch.invalidate('reader_failed')
                uart._recovery_cv.notify_all()
            raise

    def write(self, data):
        uart = self._uart
        with uart._recovery_cv:
            reader = threading.current_thread() is uart.thread
            if uart._recovery_mode in ('quiescing', 'exclusive', 'failed') and reader:
                # A legacy auto-write selected before cancellation is discarded
                # BEFORE native I/O; it is not reported as a physical write.
                uart._suppressed_auto_writes += 1
                return 0
            if uart._recovery_mode != 'idle':
                sysrq = (uart._sysrq_writing and data == b'b' and
                         threading.get_ident() == uart._recovery_owner)
                returning = uart._recovery_mode == 'return' and reader
                require(sysrq or returning, 'uart_writer_excluded')
            require(not uart.failed and not uart.stop.is_set() and self._inner.is_open,
                    'uart_writer_reader_or_port')
            return self._inner.write(data)

    def close(self):
        with self._uart._recovery_cv:
            self._uart.epoch.invalidate('capture_closed')
            self._uart._recovery_cv.notify_all()
        return self._inner.close()


class Uart(capture.Uart):
    def __init__(self, plan, guard, out):
        validate_binding(plan)
        self._recovery_cv = threading.Condition(threading.RLock())
        self._recovery_mode = 'idle'
        self._recovery_owner = None
        self._recovery_request = self._reader_ack = 0
        self._suppressed_auto_writes = 0
        self._sysrq_writing = False
        self._opened_once = False
        self.epoch = epochs.Epoch()
        super().__init__(plan, guard, out)
        factory = self.factory
        self.factory = lambda: SerialGate(factory(), self)

    @property
    def autoboot(self):
        with self._recovery_cv:
            return self._autoboot

    @autoboot.setter
    def autoboot(self, value):
        with self._recovery_cv:
            require(not value or self._recovery_mode == 'idle', 'autoboot_writer_excluded')
            self._autoboot = value

    @property
    def write_in_flight(self):
        with self._recovery_cv:
            return self._write_in_flight

    @write_in_flight.setter
    def write_in_flight(self, value):
        with self._recovery_cv:
            require(not value or self._recovery_mode == 'idle', 'flash_writer_excluded')
            self._write_in_flight = value

    def stop_autoboot(self, seconds):
        with self._recovery_cv:
            require(self._recovery_mode == 'idle', 'autoboot_writer_excluded')
            return super().stop_autoboot(seconds)

    def open(self):
        require(not self._opened_once, 'continuous_capture_cannot_reopen')
        self._opened_once = True
        self.epoch.start()
        try:
            return super().open()
        except Exception:
            self.epoch.invalidate('capture_open_failed')
            raise

    def close(self):
        with self._recovery_cv:
            self.epoch.invalidate('capture_closed')
            self._autoboot = False
            self._recovery_cv.notify_all()
        result = super().close()
        result['host_recovery_revision'] = REVISION
        result['continuous_epoch'] = self.epoch.proof(self.kernel_handoff_start)
        result['suppressed_auto_writes'] = self._suppressed_auto_writes
        return result

    def _reader_healthy(self):
        return (not self.failed and not self.stop.is_set() and self.thread is not None
                and self.thread.is_alive() and self.serial is not None
                and self.serial.is_open and not self.epoch.failure)

    def _proof_locked(self):
        proof = self.epoch.proof(self.kernel_handoff_start)
        require(self._reader_healthy() and not self.write_in_flight,
                'serial_recovery_domain')
        require(proof['eligible'] and not self.has_prompt() and not self.autoboot,
                'fresh_linux_epoch_required')
        require(self.serial.out_waiting == 0, 'serial_not_idle')
        return proof

    def quiesce_recovery(self, timeout=QUIESCE_SECONDS):
        require(0 < timeout <= QUIESCE_SECONDS, 'recovery_quiesce_deadline')
        began = time.monotonic()
        require(self._recovery_cv.acquire(timeout=timeout), 'recovery_writer_busy')
        try:
            require(self._recovery_mode == 'idle' and self._reader_healthy()
                    and not self.write_in_flight, 'serial_recovery_domain')
            require(not self.serial_recovery_record.get('break_attempted'),
                    'serial_recovery_no_retry')
            self._recovery_request += 1
            self._recovery_owner = threading.get_ident()
            self._recovery_mode = 'quiescing'
            self._autoboot = False
            while self._reader_ack != self._recovery_request:
                require(self._reader_healthy(), 'serial_recovery_domain')
                remaining = timeout - (time.monotonic() - began)
                require(remaining > 0, 'recovery_reader_ack_timeout')
                self._recovery_cv.wait(remaining)
            proof = self._proof_locked()
            self.serial_recovery_record.update(
                schema='openmitrastar.serial-recovery/v2', epoch=proof,
                reader_ack=self._reader_ack, writers_excluded=True,
                reader_ack_kind='next-read-after-all-prior-dispatch',
                suppressed_auto_writes=self._suppressed_auto_writes,
                break_attempted=False, b_attempted=False)
            self.recovery_receipt('admitted')
            return proof
        except Exception:
            if self._recovery_mode != 'idle':
                self._recovery_mode = 'failed'
                self._autoboot = False
            raise
        finally:
            self._recovery_cv.release()

    def recovery_receipt(self, stage):
        # New evidence only, fsync before BREAK and before the single b write.
        path = self.out / 'serial-recovery-r2.jsonl'
        mode = 'a' if getattr(self, '_receipt_started', False) else 'x'
        with path.open(mode, encoding='ascii') as stream:
            stream.write(json.dumps(dict(stage=stage, record=self.serial_recovery_record)) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        self._receipt_started = True


def serial_reboot_to_prompt(host, uart, drive=native_break, sleep=time.sleep,
                           clock=time.monotonic):
    require(isinstance(uart, Uart), 'continuous_recovery_uart_required')
    require(host.guard() and not uart.failed and not uart.write_in_flight,
            'serial_recovery_domain')
    proof = uart.quiesce_recovery()
    record = uart.serial_recovery_record
    try:
        # Recheck the unchanged live source/lease/identity guard AFTER handoff.
        require(host.guard(), 'serial_recovery_domain')
        with uart._recovery_cv:
            current = uart._proof_locked()
            require(current['linux_offset'] == proof['linux_offset'], 'serial_epoch_changed')
            start = uart.checkpoint()
            reset_count = uart.epoch.reset_count
            record.update(break_attempted=True, break_asserted=False, break_cleared=False,
                          b_attempted=False, b_written=False)
            uart.recovery_receipt('before-break')
            began = clock()
            try:
                drive(uart.serial, True)
                record['break_asserted'] = True
            except Exception:
                # A failed assertion may still have changed the native line.
                drive(uart.serial, False)
                record['break_cleared'] = True
                raise
        try:
            sleep(.600)
        finally:
            drive(uart.serial, False)
            record['break_cleared'] = True
        sleep(.150)
        require(host.guard(), 'serial_recovery_domain')
        with uart._recovery_cv:
            current = uart._proof_locked()
            require(clock() - began < 4 and current['linux_offset'] == proof['linux_offset']
                    and uart.epoch.reset_count == reset_count, 'serial_epoch_changed')
            uart._autoboot = True
            uart.auto_floor = uart.checkpoint()
            uart.auto_until = time.monotonic() + 120
            uart.auto_seen.clear()
            uart.auto_count = 0
            uart.invalidate_prompt()
            record['b_attempted'] = True
            uart.recovery_receipt('before-b')
            require(clock() - began < 4 and uart._reader_healthy()
                    and not uart.write_in_flight, 'serial_epoch_changed')
            uart._sysrq_writing = True
            try:
                require(uart.serial.write(b'b') == 1, 'sysrq_short_write')
            finally:
                uart._sysrq_writing = False
            record['b_written'] = True
            uart._recovery_mode = 'return'
        uart.wait_prompt(120, start)
        require(uart.epoch.reset_count > reset_count and
                re.search(rb'sysrq\s*:\s*Resetting', uart.since(start), re.I),
                'serial_reset_not_demonstrated')
        record['new_prompt_and_dispatch'] = True
        uart.recovery_receipt('new-prompt-and-dispatch')
        with uart._recovery_cv:
            uart._recovery_mode = 'idle'
            uart._recovery_owner = None
        return record
    except Exception:
        with uart._recovery_cv:
            uart._recovery_mode = 'failed'
            uart._autoboot = False
        raise


class Host(qualified.Host):
    def __init__(self, plan, out):
        validate_binding(plan)
        super().__init__(plan, out)

    def reboot_to_prompt(self, uart, software_recovery=False):
        if software_recovery:
            return serial_reboot_to_prompt(self, uart)
        return super().reboot_to_prompt(uart, software_recovery=False)
