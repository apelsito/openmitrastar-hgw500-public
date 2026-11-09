"""Bounded native UART adapter for the F325 Ethernet RAM core; no CLI.

Construction/import never opens COM3. A separately qualified parent must verify
network authority, acquire/bind the physical lease, stop at Topaz and supply its
live guard. This adapter accepts only the exact RAM-gate command vocabulary, not
flash/reboot commands. Tests inject fake serial objects; do not run on hardware
merely to check status.
"""
from __future__ import annotations

import importlib
import hashlib
import copy
import math
from pathlib import Path
import re
import sys
import time

from f325_ethernet_handoff import exact_pair, exact_server


ROOT = Path(__file__).resolve().parents[1]
MAX_RESPONSE_BYTES = 131072
PROMPT = re.compile(rb'(?:^|[\r\n])topaz>[ \t]*$')
DIAGNOSTIC_SCHEMA = 'openmitrastar.f325-uart-exchange-diagnostic/v1'
DIAGNOSTIC_FAILURE_CODES = frozenset({
    'network_authority_missing', 'channel_terminal', 'guard_failed', 'guard_unconfirmed',
    'uart_deadline_expired', 'short_uart_write', 'invalid_tx_queue', 'uart_tx_failed',
    'invalid_rx_queue', 'invalid_uart_bytes', 'uart_response_overflow', 'uart_not_open',
    'uart_exchange_failed', 'uart_driver_error',
})


class UartFailure(Exception):
    """Messages are fixed local codes, never raw serial/driver output."""


def native_serial_factory():
    """Construct the pinned vendored implementation with port=None, not open."""
    dependencies = str(ROOT / 'work/pydeps')
    inserted = dependencies not in sys.path
    if inserted:
        sys.path.insert(0, dependencies)
    try:
        serial = importlib.import_module('serial')
    finally:
        if inserted:
            sys.path.remove(dependencies)
    if Path(serial.__file__).resolve() != (ROOT / 'work/pydeps/serial/__init__.py').resolve():
        raise UartFailure('unexpected_serial_implementation')
    return serial.Serial(port=None, baudrate=115200, bytesize=8, parity='N', stopbits=1,
        timeout=0.1, write_timeout=2, xonxoff=False, rtscts=False, dsrdtr=False)


def bounded_seconds(value, maximum: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= maximum:
        raise UartFailure('invalid_deadline')
    return float(value)


class BoundedUartChannel:
    def __init__(self, *, direction: str, server_ipv4: str, guard,
                 network_authorized: bool = False, serial_factory=native_serial_factory,
                 clock=time.monotonic, sleep=time.sleep):
        image, _ = exact_pair(direction)
        self.server_ipv4 = exact_server(server_ipv4)
        if not callable(guard) or not callable(serial_factory):
            raise ValueError('guard and serial factory required')
        self.guard = guard
        self.network_authorized = network_authorized
        self.serial_factory, self.clock, self.sleep = serial_factory, clock, sleep
        self.serial = None
        self.open_attempted = False
        self.closed = False
        self.failed = False
        self.prompt_acquired = False
        self.tx_bytes = 0
        self.rx_bytes = 0
        self.commands = 0
        self._last_exchange = None
        self._exchange_state = None
        self._diagnostic_rx = None
        self._allowed = {
            'setenv ipaddr 192.168.1.90', f'setenv serverip {self.server_ipv4}',
            'printenv ipaddr', 'printenv serverip', 'printenv filesize',
            'iminfo 0x83000000',
            f"tftpboot 0x83000000 {image['base']}.webformat.bin",
            f"crc32 0x83000000 0x{image['bytes']:08x} 0x84000000; md.l 0x84000000 1",
        }

    def _begin_diagnostic(self, payload: bytes, seconds: float):
        self._exchange_started = self.clock()
        self._tx_started = self._tx_finished = self._rx_started = None
        self._diagnostic_rx = bytearray()
        # Only an already allowlisted command can be used for echo matching.
        command = payload[:-1].decode('ascii') if payload.endswith(b'\r') else ''
        self._diagnostic_command = command.encode('ascii') if command in self._allowed else None
        self._exchange_state = {
            'schema': DIAGNOSTIC_SCHEMA, 'status': 'in_progress', 'phase': 'guard', 'failure_code': None,
            'timeout_seconds': seconds, 'command_sha256': hashlib.sha256(payload).hexdigest(),
            'tx_requested_bytes': len(payload), 'tx_written_bytes': None,
            'tx_write_complete': False, 'tx_queue_drained': False,
            'rx_bytes': 0, 'rx_late_data_seen': False, 'prompt_accepted': False,
        }

    def _diagnostic_failure(self, error):
        if self._exchange_state['failure_code'] is not None:
            return  # Keep the innermost cause before outer fixed wrappers.
        code = error.args[0] if type(error) is UartFailure and error.args else None
        self._exchange_state['failure_code'] = (code if type(code) is str and code in DIAGNOSTIC_FAILURE_CODES
                                                else 'uart_driver_error')

    def _observe_diagnostic_rx(self, data, deadline: float):
        if type(data) is not bytes:
            return
        self._exchange_state['rx_bytes'] += len(data)
        self._exchange_state['rx_late_data_seen'] |= bool(data) and self.clock() >= deadline
        # Retain at most the existing response bound, including on overflow or
        # a late read. Diagnostic bytes never participate in response approval.
        room = MAX_RESPONSE_BYTES - len(self._diagnostic_rx)
        if room > 0:
            self._diagnostic_rx.extend(data[:room])

    def _finish_diagnostic(self):
        now = self.clock()
        state = self._exchange_state
        data = bytes(self._diagnostic_rx)
        complete = len(data) == state['rx_bytes']
        echo_complete = echo_terminated = False
        if self._diagnostic_command is not None:
            echo = rb'(?:^|[\r\n])(?:topaz> ?)?' + re.escape(self._diagnostic_command)
            echo_complete = re.search(echo + rb'(?=$|[\r\n])', data) is not None
            echo_terminated = re.search(echo + rb'(?=[\r\n])', data) is not None
        state.update(
            status='failed' if state['failure_code'] is not None else 'complete',
            elapsed_seconds=round(max(0.0, now - self._exchange_started), 6),
            tx_elapsed_seconds=(None if self._tx_started is None else
                                round(max(0.0, (self._tx_finished if self._tx_finished is not None else now) - self._tx_started), 6)),
            rx_elapsed_seconds=(None if self._rx_started is None else round(max(0.0, now - self._rx_started), 6)),
            rx_captured_bytes=len(data), rx_sha256=hashlib.sha256(data).hexdigest(), rx_capture_complete=complete,
            rx_c0_histogram={f'0x{value:02x}': count for value in range(32)
                             if (count := data.count(bytes([value])))},
            command_echo_complete=echo_complete, command_echo_terminated=echo_terminated,
            prompt_anywhere_count=data.count(b'topaz>'), prompt_at_end=complete and bool(PROMPT.search(data)),
            crc_word_line_count=len(re.findall(
                rb'(?:^|[\r\n])84000000:[ \t]+[0-9a-fA-F]{8}(?:[ \t]{2,}[ -~]{4})?[ \t]*(?=$|[\r\n])', data)),
        )
        self._last_exchange = state
        self._exchange_state = self._diagnostic_rx = self._diagnostic_command = None

    def _guarded(self):
        if self.network_authorized is not True:
            raise UartFailure('network_authority_missing')
        if self.failed or self.closed:
            raise UartFailure('channel_terminal')
        try:
            confirmed = self.guard() is True
        except Exception:
            self.failed = True
            raise UartFailure('guard_failed') from None
        if not confirmed:
            self.failed = True
            raise UartFailure('guard_unconfirmed')

    def open(self):
        if self.open_attempted or self.closed:
            raise UartFailure('channel_open_is_one_shot')
        self._guarded()
        self.open_attempted = True
        try:
            self.serial = self.serial_factory()
            if self.serial.is_open:
                raise UartFailure('factory_returned_open_port')
            self.serial.port = 'COM3'
            self.serial.dtr = False
            self.serial.rts = False
            self._guarded()
            self.serial.open()
            if self.serial.is_open is not True:
                raise UartFailure('uart_open_unconfirmed')
        except Exception:
            self.failed = True
            self.close()
            raise UartFailure('uart_open_failed') from None

    def _remaining(self, deadline):
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise UartFailure('uart_deadline_expired')
        return remaining

    def _write_once(self, payload: bytes, deadline: float):
        # Never call the vendored flush(), which can wait without a deadline.
        self._exchange_state['phase'] = 'tx_write'
        self._tx_started = self.clock()
        budget = min(2.0, self._remaining(deadline))
        previous = self.serial.write_timeout
        write_deadline = min(deadline, self.clock() + budget)
        if self.serial.write_timeout != budget:
            self.serial.write_timeout = budget
        try:
            written = self.serial.write(payload)
            if type(written) is int and 0 <= written <= len(payload):
                self._exchange_state['tx_written_bytes'] = written
            if type(written) is not int or written != len(payload):
                raise UartFailure('short_uart_write')
            self._exchange_state['tx_write_complete'] = True
            self.tx_bytes += written
            self._exchange_state['phase'] = 'tx_drain'
            while True:
                remaining = self._remaining(write_deadline)
                queued = self.serial.out_waiting
                self._remaining(write_deadline)
                if type(queued) is not int or queued < 0:
                    raise UartFailure('invalid_tx_queue')
                if queued == 0:
                    self._exchange_state['tx_queue_drained'] = True
                    self._tx_finished = self.clock()
                    return
                self.sleep(min(0.01, remaining))
        except Exception as error:
            self._diagnostic_failure(error)
            self.failed = True
            for method in ('cancel_write', 'reset_output_buffer'):
                try:
                    getattr(self.serial, method)()
                except Exception:
                    pass
            raise UartFailure('uart_tx_failed') from None
        finally:
            if self.serial.write_timeout != previous:
                self.serial.write_timeout = previous

    def _receive_prompt(self, deadline: float) -> bytes:
        self._exchange_state['phase'] = 'rx_wait'
        self._rx_started = self.clock()
        response = bytearray()
        previous_timeout = self.serial.timeout
        try:
            while True:
                timeout = min(0.1, self._remaining(deadline))
                if self.serial.timeout != timeout:
                    self.serial.timeout = timeout
                queued = self.serial.in_waiting
                if type(queued) is not int or queued < 0:
                    raise UartFailure('invalid_rx_queue')
                timeout = min(0.1, self._remaining(deadline))
                if self.serial.timeout != timeout:
                    self.serial.timeout = timeout
                data = self.serial.read(min(4096, max(1, queued)))
                self._observe_diagnostic_rx(data, deadline)
                self._remaining(deadline)  # Late data cannot qualify a response.
                if type(data) is not bytes:
                    raise UartFailure('invalid_uart_bytes')
                if data:
                    self.rx_bytes += len(data)
                    response.extend(data)
                    if len(response) > MAX_RESPONSE_BYTES:
                        raise UartFailure('uart_response_overflow')
                    if PROMPT.search(response):
                        self._exchange_state['prompt_accepted'] = True
                        return bytes(response)
        except Exception as error:
            self._diagnostic_failure(error)
            raise
        finally:
            if self.serial.timeout != previous_timeout:
                self.serial.timeout = previous_timeout

    def _exchange(self, payload: bytes, seconds: float) -> bytes:
        self._begin_diagnostic(payload, seconds)
        try:
            self._guarded()
        except Exception as error:
            self._diagnostic_failure(error)
            self._finish_diagnostic()
            raise
        try:
            self._exchange_state['phase'] = 'port_state'
            if self.serial is None or self.serial.is_open is not True:
                raise UartFailure('uart_not_open')
            deadline = self.clock() + seconds
            self._exchange_state['phase'] = 'rx_reset'
            self.serial.reset_input_buffer()
            self._write_once(payload, deadline)
            return self._receive_prompt(deadline)
        except Exception as error:
            self._diagnostic_failure(error)
            self.failed = True
            raise UartFailure('uart_exchange_failed') from None
        finally:
            self._finish_diagnostic()

    def acquire_prompt(self, timeout: float = 20) -> None:
        timeout = bounded_seconds(timeout, 60)
        if self.prompt_acquired:
            raise UartFailure('prompt_already_acquired')
        # One line-clear probe only. No SysRq, reset, break or AT command.
        response = self._exchange(b'\x15\r', timeout)
        if response.strip() != b'topaz>':
            self.failed = True
            raise UartFailure('unexpected_prompt_probe_output')
        self.prompt_acquired = True

    def command(self, text: str, timeout: float) -> bytes:
        timeout = bounded_seconds(timeout, 300)
        if type(text) is not str or text not in self._allowed:
            raise UartFailure('command_outside_ram_gate')
        if not self.prompt_acquired:
            raise UartFailure('fresh_topaz_prompt_required')
        self.commands += 1
        return self._exchange(text.encode('ascii') + b'\r', timeout)

    def close(self) -> bool:
        self.closed = True  # Terminal even if closing raises.
        if self.serial is None:
            return True
        try:
            self.serial.close()
            return self.serial.is_open is False
        except Exception:
            return False

    def is_closed(self) -> bool:
        if self.serial is None:
            return self.closed
        try:
            return self.closed and self.serial.is_open is False
        except Exception:
            return False

    def diagnostics(self) -> dict:
        return {'schema': 'openmitrastar.f325-ethernet-uart-adapter/v1',
            'port': 'COM3', 'open_attempted': self.open_attempted,
            'closed_confirmed': self.is_closed(), 'failed': self.failed,
            'commands': self.commands, 'tx_bytes': self.tx_bytes, 'rx_bytes': self.rx_bytes,
            'last_exchange': copy.deepcopy(self._last_exchange),
            'raw_uart_logged': False, 'flash_commands_supported': False}
