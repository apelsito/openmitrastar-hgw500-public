"""In-memory receiver tests; no serial port, network or firmware is accessed."""
from __future__ import annotations

from collections import deque
import json
from pathlib import Path
import sys

import pytest

import f325_uart_ymodem_load as loader
from ymodem.Socket import ACK, CAN, CRC, EOT, G, NAK, STX


class Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


class Receiver:
    def __init__(self, events=(), *, write_error_at: int | None = None) -> None:
        self.clock = Clock()
        self.events = deque(events)
        self.writes: list[bytes] = []
        self.read_timeouts: list[float] = []
        self.write_timeouts: list[float] = []
        self.write_error_at = write_error_at
        self.on_read = lambda value: None

    def read(self, size: int, timeout: float):
        assert size == 1 and timeout > 0
        self.read_timeouts.append(timeout)
        if not self.events:
            self.clock.now += timeout
            return b""
        delay, value = self.events[0]
        if delay > timeout:
            self.clock.now += timeout
            self.events[0] = (delay - timeout, value)
            return b""
        self.events.popleft()
        self.clock.now += delay
        self.on_read(value)
        if isinstance(value, Exception):
            raise value
        return value

    def write(self, data: bytes, timeout: float) -> int:
        assert 0 < timeout <= 1.0
        self.writes.append(bytes(data))
        self.write_timeouts.append(timeout)
        if self.write_error_at == len(self.writes):
            raise TimeoutError("synthetic uncertain TX")
        return len(data)

    def modem(self):
        return loader.F325ModemSocket(self.read, self.write, clock=self.clock)


@pytest.fixture(autouse=True)
def forbid_physical_serial(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("physical serial is forbidden in offline tests")
    monkeypatch.setattr(loader.previous.original.serial, "Serial", forbidden)


@pytest.fixture
def one_block(tmp_path: Path) -> Path:
    path = tmp_path / "private-fixture-filename.bin"
    path.write_bytes(b"private synthetic payload".ljust(1024, b"x"))
    return path


def handshake():
    return [(0.01, CRC), (0.01, ACK), (0.01, CRC)]


def data_packets(receiver: Receiver) -> list[bytes]:
    return [packet for packet in receiver.writes if packet[:2] == STX + b"\x01"]


@pytest.mark.parametrize("negative", [CRC, NAK])
def test_negative_response_resends_same_block_without_advancing_progress(one_block, negative):
    receiver = Receiver(handshake() + [(0.02, negative), (0.02, ACK), (0.01, ACK)])
    progress = []
    negative_progress = []
    receiver.on_read = lambda value: negative_progress.append(list(progress)) if value == negative else None
    modem = receiver.modem()
    assert modem.send([str(one_block)], lambda _i, _n, _t, count: progress.append(count))
    packets = data_packets(receiver)
    assert len(packets) == 2 and packets[0] == packets[1]
    assert progress == [1024] and all(snapshot == [] for snapshot in negative_progress)
    assert receiver.clock.now < 0.1
    assert modem.recorder.counts["retransmit_requested"] == 1


@pytest.mark.parametrize("delay", [1.2, 9.999])
def test_late_ack_before_ten_seconds_does_not_resend(one_block, delay):
    receiver = Receiver(handshake() + [(delay, ACK), (0.01, ACK)])
    progress = []
    assert receiver.modem().send([str(one_block)], lambda _i, _n, _t, count: progress.append(count))
    assert len(data_packets(receiver)) == 1 and progress == [1024]


def test_ack_at_deadline_is_not_accepted():
    receiver = Receiver([(10.0, ACK)])
    modem = receiver.modem()
    assert modem._read_and_wait([ACK]) is None
    assert receiver.clock.now == 10.0
    assert modem.recorder.counts["late_control"] == 1


def test_read_that_overruns_deadline_cannot_supply_success():
    receiver = Receiver()
    def overrun(size, timeout):
        receiver.clock.now += timeout + 0.01
        return ACK
    modem = loader.F325ModemSocket(overrun, receiver.write, clock=receiver.clock)
    assert modem._read_and_wait([ACK]) is None
    assert modem.recorder.counts["late_control"] == 1


def test_terminal_observed_sequence_aborts_on_first_unexpected_byte_without_more_tx(one_block):
    observed = bytes.fromhex("02 dd 55 e9 ff ff fe bc f2 ff 43")
    receiver = Receiver(handshake() + [(0.01, bytes([value])) for value in observed])
    progress = []
    modem = receiver.modem()
    with pytest.raises(loader.F325ProtocolError, match="unexpected byte"):
        modem.send([str(one_block)], lambda _i, _n, _t, count: progress.append(count))
    assert len(data_packets(receiver)) == 1 and len(receiver.writes) == 2
    assert not progress and len(receiver.events) == len(observed) - 1
    assert modem.recorder.events[-1]["byte_value"] == 2
    assert modem.recorder.counts["unexpected_byte"] == 1


@pytest.mark.parametrize("response,error", [(CAN, loader.F325ProtocolError), (OSError("private RX detail"), OSError)])
def test_receiver_cancel_and_rx_error_stop_without_retransmission(one_block, response, error):
    receiver = Receiver(handshake() + [(0.01, response)])
    progress = []
    modem = receiver.modem()
    with pytest.raises(error):
        modem.send([str(one_block)], lambda _i, _n, _t, count: progress.append(count))
    assert len(data_packets(receiver)) == 1 and len(receiver.writes) == 2
    assert not progress
    assert "private RX detail" not in json.dumps(modem.recorder.result("failed"))


def test_cancel_during_handshake_does_not_transmit(one_block):
    receiver = Receiver([(0.01, CAN)])
    with pytest.raises(loader.F325ProtocolError, match="cancelled"):
        receiver.modem().send([str(one_block)])
    assert receiver.writes == []


def test_rx_error_is_not_swallowed_by_vendor_read_wrapper():
    receiver = Receiver([(0.01, OSError("synthetic RX error"))])
    with pytest.raises(OSError, match="synthetic RX error"):
        receiver.modem().read(1, 1.0)


def test_silence_keeps_ten_attempts_with_finite_absolute_waits(one_block):
    receiver = Receiver(handshake())
    modem = receiver.modem()
    progress = []
    assert not modem.send([str(one_block)], lambda _i, _n, _t, count: progress.append(count))
    packets = data_packets(receiver)
    assert len(packets) == 10 and all(packet == packets[0] for packet in packets)
    assert receiver.writes[-2:] == [CAN, CAN]  # Existing bounded exhaustion abort.
    assert not progress and modem.recorder.counts["timeout"] == 10
    assert receiver.clock.now == pytest.approx(100.03)
    assert all(0 < timeout <= 10 for timeout in receiver.read_timeouts[3:])


def test_persistent_crc_requests_keep_retry_limit_without_timeout_stalls(one_block):
    receiver = Receiver(handshake() + [(0.01, CRC)] * 10)
    modem = receiver.modem()
    progress = []
    assert not modem.send([str(one_block)], lambda _i, _n, _t, count: progress.append(count))
    packets = data_packets(receiver)
    assert len(packets) == 10 and all(packet == packets[0] for packet in packets)
    assert not progress and receiver.clock.now == pytest.approx(0.13)
    assert modem.recorder.counts["retransmit_requested"] == 10
    assert modem.recorder.counts["timeout"] == 0


def test_tx_error_propagates_without_retry(one_block):
    receiver = Receiver(handshake(), write_error_at=2)
    progress = []
    with pytest.raises(TimeoutError, match="uncertain TX"):
        receiver.modem().send([str(one_block)], lambda _i, _n, _t, count: progress.append(count))
    assert len(data_packets(receiver)) == 1 and len(receiver.writes) == 2
    assert not progress


def test_handshake_preserves_sixty_second_deadline():
    receiver = Receiver([(59.9, CRC)])
    assert receiver.modem()._read_and_wait([NAK, CRC, G, CAN], 60) == CRC
    assert receiver.read_timeouts == [60]
    receiver = Receiver()
    assert receiver.modem()._read_and_wait([NAK, CRC, G, CAN], 60) is None
    assert receiver.clock.now == 60


def test_empty_reads_receive_remaining_budget_without_extending_deadline():
    receiver = Receiver([(3.0, b""), (3.0, b""), (3.0, b"")])
    assert receiver.modem()._read_and_wait([ACK]) is None
    assert receiver.read_timeouts == [10, 7, 4, 1]
    assert receiver.clock.now == 10


def test_write_and_wait_eot_obeys_same_receiver_controls():
    receiver = Receiver([(0.1, NAK), (0.1, ACK)])
    modem = receiver.modem()
    assert modem._write_and_wait(EOT, [ACK]) is None
    assert modem._write_and_wait(EOT, [ACK]) == ACK
    assert receiver.writes == [EOT, EOT]


def test_write_and_wait_accounts_for_time_spent_writing():
    receiver = Receiver()
    def slow_write(data, timeout):
        receiver.clock.now += 0.75
        return receiver.write(data, timeout)
    modem = loader.F325ModemSocket(receiver.read, slow_write, clock=receiver.clock)
    assert modem._write_and_wait(EOT, [ACK]) is None
    assert receiver.read_timeouts == [9.25] and receiver.clock.now == 10


@pytest.mark.parametrize("budget", [0, -1, float("inf"), float("nan")])
def test_invalid_wait_budget_stops_before_tx(budget):
    receiver = Receiver()
    with pytest.raises(ValueError):
        receiver.modem()._write_and_wait(EOT, [ACK], budget)
    assert receiver.writes == []


def test_control_events_are_bounded_redacted_and_only_written_when_requested(tmp_path):
    receiver = Receiver([(0.01, ACK)] * 12)
    recorder = loader.ControlEventRecorder(clock=receiver.clock, max_events=3)
    modem = loader.F325ModemSocket(receiver.read, receiver.write, clock=receiver.clock, recorder=recorder)
    path = tmp_path / "events.json"
    for _ in range(12):
        assert modem._read_and_wait([ACK]) == ACK
        assert not path.exists()
    report = recorder.result("test")
    assert len(report["events"]) == 3 and report["dropped_oldest_events"] == 9
    assert report["counts"] == {"accepted_control": 12}
    assert report["contains_payloads"] is False and report["contains_filenames"] is False
    recorder.write_result(path, "test")
    assert json.loads(path.read_text())["total_events"] == 12
    with pytest.raises(FileExistsError):
        recorder.write_result(path, "test")


@pytest.mark.parametrize("fails", [False, True])
def test_main_restores_previous_class_and_writes_events_once(tmp_path, monkeypatch, fails):
    original_class = loader.previous.F321ModemSocket
    status = tmp_path / "status.json"
    events = tmp_path / "uart-ymodem-control-events.json"
    monkeypatch.setattr(sys, "argv", ["f325_uart_ymodem_load.py", "--status", str(status)])
    def original_main():
        assert loader.previous.F321ModemSocket is not original_class
        assert issubclass(loader.previous.F321ModemSocket, original_class)
        assert not events.exists()
        if fails:
            raise RuntimeError("private filename and payload must not enter events")
        return 0
    monkeypatch.setattr(loader.previous, "main", original_main)
    if fails:
        with pytest.raises(RuntimeError, match="private filename"):
            loader.main()
    else:
        assert loader.main() == 0
    assert loader.previous.F321ModemSocket is original_class
    text = events.read_text()
    assert "private filename" not in text and "payload must" not in text
    assert json.loads(text)["outcome"] == ("failed" if fails else "ram_verified")


def test_event_write_failure_does_not_mask_original_exception_or_prevent_restoration(tmp_path, monkeypatch, capsys):
    original_class = loader.previous.F321ModemSocket
    monkeypatch.setattr(sys, "argv", ["f325_uart_ymodem_load.py", "--status", str(tmp_path / "status.json")])
    def original_main():
        raise RuntimeError("original transfer failure")
    def failed_write(*args, **kwargs):
        raise OSError("synthetic telemetry write failure")
    monkeypatch.setattr(loader.previous, "main", original_main)
    monkeypatch.setattr(loader.ControlEventRecorder, "write_result", failed_write)
    with pytest.raises(RuntimeError, match="original transfer failure"):
        loader.main()
    assert loader.previous.F321ModemSocket is original_class
    assert capsys.readouterr().out.strip() == "OMF325_UART_CONTROL_EVENTS_UNAVAILABLE=1"
