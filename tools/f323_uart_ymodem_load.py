#!/usr/bin/env python3
"""F323 host transport: explicit receiver control during bounded ACK waits.

The original F321 loader still owns argument/image/attach/RAM checks and bounded
UART writes. This adapter corrects control handling; it does not establish why
the physical RX stream became corrupt. It never adds an automatic flash retry.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import time
from typing import Callable

import f321_uart_ymodem_load as previous
from ymodem.Socket import ACK, CAN, CRC, NAK


ACK_WAIT_SECONDS = 10.0
MAX_CONTROL_EVENTS = 8192


class F323ProtocolError(RuntimeError):
    """Receiver cancellation or a byte outside the current control dialogue."""


class ControlEventRecorder:
    """Bounded, payload-free event tail; disk I/O occurs only in write_result."""

    def __init__(self, *, clock: Callable[[], float] | None = None,
                 max_events: int = MAX_CONTROL_EVENTS) -> None:
        if not 1 <= max_events <= MAX_CONTROL_EVENTS:
            raise ValueError("invalid control event memory limit")
        self.clock = clock or time.monotonic
        self.started = self.clock()
        self.started_at_utc = datetime.now(timezone.utc).isoformat()
        self.events: deque[dict] = deque(maxlen=max_events)
        self.counts: Counter[str] = Counter()
        self.total_events = 0

    def record(self, event: str, *, window: int, mode: str, deadline: float,
               control: str | None = None, byte_value: int | None = None,
               error_type: str | None = None) -> None:
        now = self.clock()
        value = {
            "event": event, "window": window, "mode": mode,
            "elapsed_seconds": round(now - self.started, 6),
            "remaining_seconds": round(max(0.0, deadline - now), 6),
        }
        if control is not None:
            value["control"] = control
        if byte_value is not None:
            value["byte_value"] = byte_value
        if error_type is not None:
            value["error_type"] = error_type
        self.events.append(value)
        self.counts[event] += 1
        self.total_events += 1

    def result(self, outcome: str) -> dict:
        return {
            "schema": "openmitrastar.f323-uart-control-events/v1",
            "started_at_utc": self.started_at_utc,
            "finished_at_utc": datetime.now(timezone.utc).isoformat(),
            "outcome": outcome, "ack_wait_seconds": ACK_WAIT_SECONDS,
            "event_capacity": self.events.maxlen,
            "total_events": self.total_events,
            "dropped_oldest_events": self.total_events - len(self.events),
            "counts": dict(self.counts), "events": list(self.events),
            "contains_payloads": False, "contains_filenames": False,
            "flash_writes": 0,
        }

    def write_result(self, path: Path, outcome: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("x", encoding="ascii") as stream:
            stream.write(json.dumps(self.result(outcome), indent=2, allow_nan=False) + "\n")


class F323ModemSocket(previous.F321ModemSocket):
    def __init__(self, *args, recorder: ControlEventRecorder | None = None,
                 clock: Callable[[], float] | None = None, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.clock = clock or (recorder.clock if recorder is not None else time.monotonic)
        self.recorder = recorder if recorder is not None else ControlEventRecorder(clock=self.clock)
        self._window = 0

    def read(self, size: int, timeout: float = 1):
        # The vendor wrapper turns every RX exception into an ordinary timeout.
        # An uncertain RX state must propagate and stop before another write.
        return self._read(size, timeout)

    @staticmethod
    def _wait_budget(wait_chars, wait_time: float | None) -> float:
        ack_wait = tuple(wait_chars) == (ACK,)
        budget = ACK_WAIT_SECONDS if ack_wait and wait_time is None else (1.0 if wait_time is None else float(wait_time))
        if not math.isfinite(budget) or budget <= 0:
            raise ValueError("control wait requires a finite positive deadline")
        return min(budget, ACK_WAIT_SECONDS) if ack_wait else budget

    def _wait_for_control(self, wait_chars, deadline: float, window: int):
        expected = tuple(wait_chars)
        ack_wait = expected == (ACK,)
        mode = "ack" if ack_wait else "receiver_request"
        names = {ACK: "ACK", CRC: "C", NAK: "NAK", CAN: "CAN"}
        while True:
            remaining = deadline - self.clock()
            if remaining <= 0:
                self.recorder.record("timeout", window=window, mode=mode, deadline=deadline)
                return None
            try:
                # Clamp the ACK call too: float subtraction can otherwise make
                # an exact ten-second budget a few ulps larger than ten.
                value = self.read(1, timeout=min(remaining, ACK_WAIT_SECONDS) if ack_wait else remaining)
            except Exception as exc:
                self.recorder.record("rx_error", window=window, mode=mode, deadline=deadline,
                                     error_type=type(exc).__name__)
                raise
            now = self.clock()
            if value is None or value == b"":
                continue
            if not isinstance(value, (bytes, bytearray)) or len(value) != 1:
                self.recorder.record("invalid_rx_shape", window=window, mode=mode, deadline=deadline)
                raise F323ProtocolError("invalid UART control response shape")
            value = bytes(value)
            if value == CAN:
                self.recorder.record("receiver_cancelled", window=window, mode=mode, deadline=deadline, control="CAN")
                raise F323ProtocolError("receiver cancelled UART transfer")
            if value not in expected and not (ack_wait and value in (CRC, NAK)):
                self.recorder.record("unexpected_byte", window=window, mode=mode, deadline=deadline,
                                     byte_value=value[0])
                raise F323ProtocolError("unexpected byte in UART control dialogue")
            # Even a valid ACK is not success if the underlying read overruns.
            if now >= deadline:
                self.recorder.record("late_control", window=window, mode=mode, deadline=deadline,
                                     control=names.get(value, "G"))
                return None
            if ack_wait and value in (CRC, NAK):
                self.recorder.record("retransmit_requested", window=window, mode=mode, deadline=deadline,
                                     control=names[value])
                # Vendor send() retries the same immutable block. A truthy C
                # here would incorrectly advance both sequence and progress.
                return None
            self.recorder.record("accepted_control", window=window, mode=mode, deadline=deadline,
                                 control=names.get(value, "G"))
            return value

    def _read_and_wait(self, wait_chars, wait_time: float | None = None):
        expected = tuple(wait_chars)
        deadline = self.clock() + self._wait_budget(expected, wait_time)
        self._window += 1
        return self._wait_for_control(expected, deadline, self._window)

    def _write_and_wait(self, write_char, wait_chars, wait_time: float | None = None):
        expected = tuple(wait_chars)
        deadline = self.clock() + self._wait_budget(expected, wait_time)
        self._window += 1
        remaining = deadline - self.clock()
        if remaining <= 0:
            raise TimeoutError("UART control deadline expired before write")
        # Preserve F321's one-second modem TX cap and its fail-stop behavior.
        self.write(write_char, timeout=min(1.0, remaining))
        return self._wait_for_control(expected, deadline, self._window)


def main() -> int:
    # F321 remains the authoritative parser; only locate its existing evidence
    # destination. It still validates the exact image before opening UART.
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--status", type=Path, required=True)
    args, _ = parser.parse_known_args()
    recorder = ControlEventRecorder()

    class RecordingModem(F323ModemSocket):
        def __init__(self, *modem_args, **modem_kwargs):
            super().__init__(*modem_args, recorder=recorder, **modem_kwargs)

    previous_class = previous.F321ModemSocket
    outcome = "failed"
    previous.F321ModemSocket = RecordingModem
    try:
        result = previous.main()
        outcome = "ram_verified" if result == 0 else "failed"
        return result
    finally:
        previous.F321ModemSocket = previous_class
        try:
            recorder.write_result(args.status.with_name("uart-ymodem-control-events.json"), outcome)
        except OSError:
            # Telemetry loss must neither mask a transport exception nor cause
            # retransmission. Existing RAM-integrity evidence remains required.
            print("OMF323_UART_CONTROL_EVENTS_UNAVAILABLE=1", flush=True)


if __name__ == "__main__":
    raise SystemExit(main())
