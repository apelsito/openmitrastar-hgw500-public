"""Bounded UART contracts with fake serial, clock/sleep, factory and guard.

No native serial factory, driver import, COM port, socket, SSH or image is used.
The clean prompt fixture is the observed offline prefix CR CR LF topaz>.
"""
from __future__ import annotations

from collections import deque
import hashlib
import json
from types import SimpleNamespace

import pytest

import f325_ethernet_uart as uart


CLEAN_PROMPT = b"\r\r\ntopaz>"
SERVER = "192.168.1.249"


class Clock:
    def __init__(self):
        self.now = 0.0
        self.sleeps = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        assert seconds > 0
        self.sleeps.append(seconds)
        self.now += seconds


class FakeSerial:
    def __init__(self, clock, trace):
        self.clock, self.trace = clock, trace
        self.port = None
        self.dtr = self.rts = True
        self._timeout = 0.25
        self._write_timeout = 7.0
        self.timeout_setters = []
        self.write_timeout_setters = []
        self._is_open = False
        self.is_open_error = False
        self.open_error = False
        self.close_error = False
        self.close_leaves_open = False
        self.writes = []
        self.write_timeouts = []
        self.read_timeouts = []
        self.flush_calls = 0
        self.responses = deque()
        self.rx = deque()
        self.write_duration = 0.0
        self.write_failure = None
        self.drain_after = 0.0
        self.drain_until = 0.0
        self.queue_forever = False
        self.queue_query_delay = 0.0
        self.read_error = False
        self.late_read_delay = 0.0

    @property
    def timeout(self):
        return self._timeout

    @timeout.setter
    def timeout(self, value):
        self.timeout_setters.append(value)
        self._timeout = value

    @property
    def write_timeout(self):
        return self._write_timeout

    @write_timeout.setter
    def write_timeout(self, value):
        self.write_timeout_setters.append(value)
        self._write_timeout = value

    @property
    def is_open(self):
        if self.is_open_error:
            raise RuntimeError("private driver state detail")
        return self._is_open

    def open(self):
        self.trace.append(("open", self.port, self.dtr, self.rts))
        if self.open_error:
            raise RuntimeError("private open detail")
        self._is_open = True

    def close(self):
        self.trace.append(("close",))
        if self.close_error:
            raise RuntimeError("private close detail")
        if not self.close_leaves_open:
            self._is_open = False

    def reply(self, data=CLEAN_PROMPT, delay=0.01):
        self.responses.append((delay, data))

    def reset_input_buffer(self):
        self.trace.append(("reset_input",))
        self.rx = deque((when, data) for when, data in self.rx if when > self.clock.now)

    def write(self, payload):
        self.trace.append(("write", payload))
        self.writes.append(payload)
        self.write_timeouts.append(self.write_timeout)
        self.clock.now += self.write_duration
        self.drain_until = self.clock.now + self.drain_after
        if self.write_failure == "error":
            raise RuntimeError("private write detail")
        if self.write_failure == "partial":
            return len(payload) - 1
        if self.responses:
            delay, data = self.responses.popleft()
            self.rx.append((self.clock.now + delay, data))
        return len(payload)

    @property
    def out_waiting(self):
        self.clock.now += self.queue_query_delay
        return 1 if self.queue_forever or self.clock.now < self.drain_until else 0

    @property
    def in_waiting(self):
        if self.rx and self.rx[0][0] <= self.clock.now:
            return len(self.rx[0][1])
        return 0

    def read(self, size):
        assert 1 <= size <= 4096
        self.read_timeouts.append(self.timeout)
        if self.read_error:
            raise RuntimeError("private RX detail")
        if self.late_read_delay:
            self.clock.now += self.late_read_delay
            return CLEAN_PROMPT
        if not self.rx or self.rx[0][0] > self.clock.now + self.timeout:
            self.clock.now += self.timeout
            return b""
        when, data = self.rx.popleft()
        self.clock.now = max(self.clock.now, when)
        part, remaining = data[:size], data[size:]
        if remaining:
            self.rx.appendleft((self.clock.now, remaining))
        return part

    def flush(self):
        self.flush_calls += 1
        raise AssertionError("unbounded flush must never be used")

    def cancel_write(self):
        self.trace.append(("cancel_write",))

    def reset_output_buffer(self):
        self.trace.append(("reset_output",))


class Rig:
    def __init__(self, *, direction="promote", authorized=True):
        self.clock = Clock()
        self.trace = []
        self.serial = FakeSerial(self.clock, self.trace)
        self.guard_results = deque()
        self.guard_calls = 0
        self.factory_calls = 0
        self.factory_error = False
        self.channel = uart.BoundedUartChannel(
            direction=direction, server_ipv4=SERVER, guard=self.guard,
            network_authorized=authorized, serial_factory=self.factory,
            clock=self.clock, sleep=self.clock.sleep,
        )

    def guard(self):
        self.guard_calls += 1
        self.trace.append(("guard", self.guard_calls))
        value = self.guard_results.popleft() if self.guard_results else True
        if isinstance(value, Exception):
            raise value
        return value

    def factory(self):
        self.factory_calls += 1
        self.trace.append(("factory",))
        if self.factory_error:
            raise RuntimeError("private factory detail")
        return self.serial

    def ready(self):
        self.channel.open()
        self.serial.reply()
        self.channel.acquire_prompt()
        return self


@pytest.fixture(autouse=True)
def block_native_driver_import(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("native serial factory/driver import forbidden")
    # Keep the module's lazy native dependency route inert even if a regression
    # accidentally bypasses one of these tests' explicitly supplied factories.
    monkeypatch.setattr(uart, "importlib", SimpleNamespace(import_module=forbidden))


def test_constructor_has_no_factory_guard_clock_or_serial_effects():
    rig = Rig()
    assert rig.trace == [] and rig.factory_calls == 0 and rig.guard_calls == 0
    assert rig.clock.now == 0 and rig.clock.sleeps == []
    assert rig.serial.writes == [] and rig.serial._is_open is False


def test_missing_or_nonboolean_authority_has_no_factory_or_guard_effects():
    for value in (False, None, 1, "true"):
        rig = Rig(authorized=value)
        with pytest.raises(uart.UartFailure): rig.channel.open()
        assert rig.trace == [] and rig.factory_calls == 0 and rig.guard_calls == 0


def test_guard_precedes_factory_and_open_with_exact_com_and_inactive_lines():
    rig = Rig()
    rig.channel.open()
    assert rig.trace == [("guard", 1), ("factory",), ("guard", 2), ("open", "COM3", False, False)]
    assert rig.serial._is_open is True and rig.serial.writes == []


def test_open_and_closed_channel_are_one_shot():
    rig = Rig()
    rig.channel.open()
    with pytest.raises(uart.UartFailure): rig.channel.open()
    assert rig.channel.close() is True and rig.channel.is_closed() is True
    with pytest.raises(uart.UartFailure): rig.channel.open()
    assert rig.factory_calls == 1 and sum(event[0] == "open" for event in rig.trace) == 1


def test_factory_failure_is_sanitized_terminal_and_never_retried():
    rig = Rig()
    rig.factory_error = True
    with pytest.raises(uart.UartFailure) as error: rig.channel.open()
    assert "private" not in str(error.value) and rig.channel.failed is True
    with pytest.raises(uart.UartFailure): rig.channel.open()
    assert rig.factory_calls == 1 and rig.serial.writes == []


@pytest.mark.parametrize("stage", ["factory", "open"])
def test_false_guard_blocks_factory_or_open(stage):
    rig = Rig()
    rig.guard_results.extend([False] if stage == "factory" else [True, False])
    with pytest.raises(uart.UartFailure): rig.channel.open()
    assert rig.factory_calls == (0 if stage == "factory" else 1)
    assert not any(event[0] == "open" for event in rig.trace)
    assert rig.serial.writes == []


def test_guard_exception_is_sanitized_terminal_and_cannot_be_retried():
    for phase in ("open", "command"):
        rig = Rig()
        if phase == "command": rig.ready()
        before = len(rig.serial.writes)
        rig.guard_results.append(RuntimeError("private guard detail"))
        with pytest.raises(uart.UartFailure) as error:
            rig.channel.open() if phase == "open" else rig.channel.command("printenv filesize", 1)
        assert "private" not in str(error.value) and rig.channel.failed is True
        with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 1)
        assert len(rig.serial.writes) == before


def test_driver_open_state_error_is_sanitized_terminal_before_tx():
    rig = Rig().ready()
    before = len(rig.serial.writes)
    rig.serial.is_open_error = True
    with pytest.raises(uart.UartFailure) as error: rig.channel.command("printenv filesize", 1)
    assert "private" not in str(error.value) and rig.channel.failed is True
    rig.serial.is_open_error = False
    with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 1)
    assert len(rig.serial.writes) == before


def test_false_guard_before_command_prevents_rx_reset_and_tx():
    rig = Rig().ready()
    before = len(rig.serial.writes)
    rig.guard_results.append(False)
    with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 1)
    assert rig.trace[-1] == ("guard", rig.guard_calls)
    assert len(rig.serial.writes) == before and rig.channel.failed is True


def test_prompt_probe_is_only_ctrl_u_cr_and_accepts_observed_clean_prefix():
    rig = Rig().ready()
    assert rig.serial.writes == [b"\x15\r"]
    assert rig.channel.prompt_acquired is True and rig.channel.rx_bytes == len(CLEAN_PROMPT)
    assert rig.trace[-2:] == [("reset_input",), ("write", b"\x15\r")]
    with pytest.raises(uart.UartFailure): rig.channel.acquire_prompt()
    assert rig.serial.writes == [b"\x15\r"]


def test_prompt_probe_rejects_unclean_duplicate_or_other_console_output():
    for response in (b"\x15\r\ntopaz>", b"topaz>\r\ntopaz>", b"ZHAL>"):
        rig = Rig()
        rig.channel.open()
        rig.serial.reply(response)
        with pytest.raises(uart.UartFailure): rig.channel.acquire_prompt(timeout=1)
        assert rig.channel.failed is True and rig.channel.prompt_acquired is False
        assert rig.serial.writes == [b"\x15\r"]


def test_command_requires_prompt_acquired_on_this_channel():
    rig = Rig()
    rig.channel.open()
    with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 1)
    assert rig.serial.writes == []


@pytest.mark.parametrize("direction", ["promote", "rollback"])
def test_exact_ram_vocabulary_checks_guard_resets_rx_and_writes_once(direction):
    rig = Rig(direction=direction).ready()
    image, _ = uart.exact_pair(direction)
    commands = ["setenv ipaddr 192.168.1.90", f"setenv serverip {SERVER}", "printenv ipaddr",
                "printenv serverip", "printenv filesize", "iminfo 0x83000000",
                f"tftpboot 0x83000000 {image['base']}.webformat.bin",
                f"crc32 0x83000000 0x{image['bytes']:08x} 0x84000000; md.l 0x84000000 1"]
    for command in commands:
        previous_guard = rig.guard_calls
        previous_writes = len(rig.serial.writes)
        rig.serial.reply(CLEAN_PROMPT)
        assert rig.channel.command(command, 1) == CLEAN_PROMPT
        assert rig.guard_calls == previous_guard + 1 and len(rig.serial.writes) == previous_writes + 1
        assert rig.trace[-3:] == [("guard", rig.guard_calls), ("reset_input",), ("write", command.encode() + b"\r")]
    assert rig.channel.commands == len(commands) and rig.serial.flush_calls == 0


@pytest.mark.parametrize("kind", ["flash", "boot", "wrong_scope", "injection"])
def test_flash_reboot_other_scope_and_injected_commands_never_transmit(kind):
    cases = {
        "flash": ["spi_flash erase 0x007e0000 0x005e0000", "spi_flash write 0x007e0000 0x83000000 0x10", "sf write 0 0 1"],
        "boot": ["reboot", "bootselect", "saveenv"],
        "wrong_scope": ["setenv ipaddr 192.168.1.1", "setenv serverip 192.168.1.248", "tftpboot 0x83000000 other.bin"],
        "injection": ["printenv filesize\nreboot", "printenv filesize; saveenv", "iminfo 0x83000000\r", "setenv serverip 192.168.1.249; echo extra"],
    }
    rig = Rig().ready()
    before = list(rig.trace)
    for command in cases[kind]:
        with pytest.raises(uart.UartFailure): rig.channel.command(command, 1)
    assert rig.trace == before and rig.serial.writes == [b"\x15\r"]


def test_stale_prompt_is_reset_before_probe_and_before_each_command():
    for phase in ("probe", "command"):
        rig = Rig()
        rig.ready() if phase == "command" else rig.channel.open()
        rig.serial.rx.append((rig.clock.now, CLEAN_PROMPT))
        with pytest.raises(uart.UartFailure):
            rig.channel.command("printenv filesize", 0.5) if phase == "command" else rig.channel.acquire_prompt(0.5)
        assert rig.channel.failed is True
        assert rig.trace[-2:] == [("reset_input",), ("write", b"printenv filesize\r" if phase == "command" else b"\x15\r")]


@pytest.mark.parametrize("failure", ["partial", "error"])
def test_partial_or_failed_tx_aborts_queue_and_never_retries(failure):
    rig = Rig().ready()
    before = len(rig.serial.writes)
    rig.serial.write_failure = failure
    with pytest.raises(uart.UartFailure) as error: rig.channel.command("printenv filesize", 3)
    assert "private" not in str(error.value) and rig.channel.failed is True
    assert len(rig.serial.writes) == before + 1
    assert rig.trace[-2:] == [("cancel_write",), ("reset_output",)]
    assert rig.serial.write_timeout == 7.0 and rig.serial.flush_calls == 0
    with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 3)
    assert len(rig.serial.writes) == before + 1


def test_driver_write_and_queue_drain_share_one_two_second_budget():
    for drain, succeeds in ((0.4, True), (0.6, False)):
        rig = Rig().ready()
        began = rig.clock.now
        rig.serial.write_duration = 1.5
        rig.serial.drain_after = drain
        rig.serial.reply()
        if succeeds:
            assert rig.channel.command("printenv filesize", 3) == CLEAN_PROMPT
        else:
            with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 3)
        assert rig.clock.now - began <= 2.000001
        assert rig.serial.write_timeouts[-1] <= 2.0
        assert rig.serial.write_timeout == 7.0 and rig.serial.flush_calls == 0


def test_stuck_queue_stops_at_shared_deadline_without_flush_or_retry():
    rig = Rig().ready()
    rig.serial.queue_forever = True
    began = rig.clock.now
    with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 3)
    assert rig.clock.now - began == pytest.approx(2.0)
    assert rig.serial.writes == [b"\x15\r", b"printenv filesize\r"]
    assert rig.serial.flush_calls == 0 and max(rig.clock.sleeps) <= 0.01


def test_late_empty_queue_query_cannot_qualify_tx_success():
    rig = Rig().ready()
    rig.serial.queue_query_delay = 2.1
    rig.serial.reply()
    with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 3)
    assert rig.channel.failed is True
    assert rig.serial.writes == [b"\x15\r", b"printenv filesize\r"]


@pytest.mark.parametrize("overflow", [False, True])
def test_rx_response_limit_accepts_exact_bound_and_rejects_overflow(overflow):
    rig = Rig().ready()
    ending = b"\ntopaz>"
    response = b"x" * (uart.MAX_RESPONSE_BYTES - len(ending) + int(overflow)) + ending
    rig.serial.reply(response)
    if overflow:
        with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 3)
        assert rig.channel.failed is True
    else:
        assert len(rig.channel.command("printenv filesize", 3)) == uart.MAX_RESPONSE_BYTES
    assert rig.serial.timeout == 0.25


def test_prompt_returned_after_absolute_rx_deadline_never_passes():
    rig = Rig().ready()
    rig.serial.late_read_delay = 1.1
    with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 1)
    assert rig.channel.failed is True and rig.serial.timeout == 0.25


def test_rx_driver_failure_is_terminal_sanitized_and_not_retried():
    rig = Rig().ready()
    rig.serial.read_error = True
    with pytest.raises(uart.UartFailure) as error: rig.channel.command("printenv filesize", 1)
    assert "private" not in str(error.value) and rig.channel.failed is True
    with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", 1)
    assert rig.serial.writes == [b"\x15\r", b"printenv filesize\r"]


@pytest.mark.parametrize("failure", ["still_open", "driver_error", "state_error"])
def test_close_failure_or_unknown_driver_state_never_reports_closed(failure):
    rig = Rig().ready()
    rig.serial.close_leaves_open = failure == "still_open"
    rig.serial.close_error = failure == "driver_error"
    rig.serial.is_open_error = failure == "state_error"
    assert rig.channel.close() is False and rig.channel.is_closed() is False
    assert rig.channel.diagnostics()["closed_confirmed"] is False
    with pytest.raises(uart.UartFailure): rig.channel.open()
    assert rig.factory_calls == 1


def test_invalid_deadlines_fail_before_guard_or_tx():
    rig = Rig().ready()
    before = list(rig.trace)
    for timeout in (0, -1, True, float("nan"), float("inf"), 301):
        with pytest.raises(uart.UartFailure): rig.channel.command("printenv filesize", timeout)
    assert rig.trace == before


def test_diagnostics_contains_only_counts_and_flags_not_serial_content():
    rig = Rig().ready()
    rig.serial.reply(b"private-rx-marker\r\ntopaz>")
    rig.channel.command("printenv filesize", 1)
    report = rig.channel.diagnostics()
    assert "private-rx-marker" not in json.dumps(report)
    assert "printenv" not in json.dumps(report)
    assert report["raw_uart_logged"] is False and report["flash_commands_supported"] is False
    assert report["commands"] == 1 and report["port"] == "COM3"


@pytest.mark.parametrize("terminated", [False, True])
def test_complete_echo_without_prompt_preserves_partial_rx_and_deadline_cause(terminated):
    rig = Rig().ready()
    command = "printenv filesize"
    response = command.encode() + (b"\r\n" if terminated else b"")
    rig.serial.reply(response)
    with pytest.raises(uart.UartFailure):
        rig.channel.command(command, 1)
    report = rig.channel.diagnostics()["last_exchange"]
    assert report["status"] == "failed" and report["phase"] == "rx_wait"
    assert report["failure_code"] == "uart_deadline_expired"
    assert report["tx_write_complete"] and report["tx_queue_drained"]
    assert report["tx_written_bytes"] == len(command) + 1
    assert report["rx_bytes"] == report["rx_captured_bytes"] == len(response)
    assert report["rx_sha256"] == hashlib.sha256(response).hexdigest()
    assert report["rx_capture_complete"] and report["command_echo_complete"]
    assert report["command_echo_terminated"] is terminated
    assert report["prompt_anywhere_count"] == 0 and not report["prompt_at_end"]
    assert report["elapsed_seconds"] == pytest.approx(1) and not report["prompt_accepted"]


def test_empty_rx_is_distinguishable_from_echo_or_partial_response():
    rig = Rig().ready()
    with pytest.raises(uart.UartFailure):
        rig.channel.command("printenv filesize", 1)
    report = rig.channel.diagnostics()["last_exchange"]
    assert report["failure_code"] == "uart_deadline_expired" and report["phase"] == "rx_wait"
    assert report["rx_bytes"] == report["rx_captured_bytes"] == 0
    assert report["rx_sha256"] == hashlib.sha256(b"").hexdigest()
    assert report["rx_c0_histogram"] == {} and not report["command_echo_complete"]
    assert report["rx_elapsed_seconds"] == pytest.approx(1)


@pytest.mark.parametrize("failure,code", [("partial", "short_uart_write"), ("error", "uart_driver_error")])
def test_tx_failure_keeps_innermost_fixed_cause_and_never_logs_driver_message(failure, code):
    rig = Rig().ready()
    rig.serial.write_failure = failure
    with pytest.raises(uart.UartFailure) as error:
        rig.channel.command("printenv filesize", 1)
    report = rig.channel.diagnostics()["last_exchange"]
    assert report["failure_code"] == code and report["phase"] == "tx_write"
    assert not report["tx_write_complete"] and not report["tx_queue_drained"]
    assert report["rx_bytes"] == 0 and report["rx_elapsed_seconds"] is None
    assert "private" not in json.dumps(report) and "private" not in str(error.value)


def test_late_prompt_is_recorded_but_never_accepted():
    rig = Rig().ready()
    rig.serial.late_read_delay = 1.1
    with pytest.raises(uart.UartFailure):
        rig.channel.command("printenv filesize", 1)
    report = rig.channel.diagnostics()["last_exchange"]
    assert report["failure_code"] == "uart_deadline_expired"
    assert report["rx_late_data_seen"] and report["prompt_at_end"]
    assert report["prompt_anywhere_count"] == 1 and not report["prompt_accepted"]
    assert report["rx_sha256"] == hashlib.sha256(CLEAN_PROMPT).hexdigest()
    assert report["rx_bytes"] == len(CLEAN_PROMPT)


def test_fragmented_echo_crc_word_and_prompt_produce_only_derived_facts():
    rig = Rig().ready()
    command = next(value for value in rig.channel._allowed if value.startswith("crc32 "))
    response = command.encode() + b"\r\n84000000: 1d9146bc    ....\r\ntopaz>"
    for index, value in enumerate(response, 1):
        rig.serial.rx.append((rig.clock.now + index / 1000, bytes([value])))
    assert rig.channel.command(command, 1) == response
    report = rig.channel.diagnostics()["last_exchange"]
    assert report["status"] == "complete" and report["failure_code"] is None
    assert report["command_echo_complete"] and report["command_echo_terminated"]
    assert report["prompt_anywhere_count"] == 1 and report["prompt_at_end"] and report["prompt_accepted"]
    assert report["crc_word_line_count"] == 1 and report["rx_c0_histogram"] == {"0x0a": 2, "0x0d": 2}
    assert report["rx_sha256"] == hashlib.sha256(response).hexdigest()
    assert command not in json.dumps(report) and "1d9146bc" not in json.dumps(report)
    report["rx_c0_histogram"]["private"] = 1
    assert "private" not in json.dumps(rig.channel.diagnostics())


def test_prompt_with_trailing_private_noise_is_seen_but_not_accepted_or_logged():
    rig = Rig().ready()
    response = b"printenv filesize\r\n84000000: 1d9146bc    ....\r\ntopaz>\r\nPRIVATE-RX-MARKER"
    rig.serial.reply(response)
    with pytest.raises(uart.UartFailure):
        rig.channel.command("printenv filesize", 1)
    report = rig.channel.diagnostics()["last_exchange"]
    assert report["prompt_anywhere_count"] == 1 and report["crc_word_line_count"] == 1
    assert not report["prompt_at_end"] and not report["prompt_accepted"]
    assert report["failure_code"] == "uart_deadline_expired"
    assert "PRIVATE-RX-MARKER" not in json.dumps(report)


def test_unknown_local_exception_text_is_not_used_as_a_diagnostic_code():
    rig = Rig().ready()
    def fail(_):
        raise uart.UartFailure("PRIVATE-EXCEPTION-MARKER")
    rig.serial.write = fail
    with pytest.raises(uart.UartFailure):
        rig.channel.command("printenv filesize", 1)
    report = rig.channel.diagnostics()["last_exchange"]
    assert report["failure_code"] == "uart_driver_error"
    assert "PRIVATE-EXCEPTION-MARKER" not in json.dumps(report)


def test_diagnostic_partial_buffer_stays_bounded_on_overflow():
    rig = Rig().ready()
    response = b"x" * (uart.MAX_RESPONSE_BYTES + 1)
    rig.serial.reply(response)
    with pytest.raises(uart.UartFailure):
        rig.channel.command("printenv filesize", 1)
    report = rig.channel.diagnostics()["last_exchange"]
    assert report["failure_code"] == "uart_response_overflow"
    assert report["rx_bytes"] == len(response) and report["rx_captured_bytes"] == uart.MAX_RESPONSE_BYTES
    assert not report["rx_capture_complete"]
    assert report["rx_sha256"] == hashlib.sha256(response[:uart.MAX_RESPONSE_BYTES]).hexdigest()


def test_ordinary_exchange_does_not_reapply_unchanged_serial_timeouts():
    rig = Rig()
    rig.serial.timeout = 0.1
    rig.serial.write_timeout = 2.0
    rig.ready()
    rig.serial.timeout_setters.clear(); rig.serial.write_timeout_setters.clear()
    rig.serial.reply(delay=0.25)
    assert rig.channel.command("printenv filesize", 3) == CLEAN_PROMPT
    assert rig.serial.timeout_setters == [] and rig.serial.write_timeout_setters == []
    assert rig.serial.timeout == 0.1 and rig.serial.write_timeout == 2.0


def test_short_deadline_still_adjusts_and_restores_timeouts_without_extension():
    rig = Rig()
    rig.serial.timeout = 0.1
    rig.serial.write_timeout = 2.0
    rig.ready()
    rig.serial.timeout_setters.clear(); rig.serial.write_timeout_setters.clear()
    began = rig.clock.now
    with pytest.raises(uart.UartFailure):
        rig.channel.command("printenv filesize", 0.04)
    assert rig.clock.now - began == pytest.approx(0.04)
    assert rig.serial.write_timeout_setters == pytest.approx([0.04, 2.0])
    assert rig.serial.timeout_setters == pytest.approx([0.04, 0.1])
    assert rig.serial.timeout == 0.1 and rig.serial.write_timeout == 2.0
