#!/usr/bin/env python3
"""F321 RAM-only loader: bounded TX and observable, attach-only YMODEM.

Reuse the original image checks and transfer implementation without changing
that file. Prompt probes end before loady; a failed stage never starts flash.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time

import uart_ymodem_load as original


PROMPT_RETRY_SECONDS = 1.0
PROMPT_RETRIES = 3
OPTIONS = {
    "--port", "--baud", "--file", "--address", "--expected-sha256",
    "--expected-size", "--expected-crc32", "--log", "--status",
    "--attach-topaz", "--prompt-timeout",
}


class UartSession(original.UartSession):
    def write(self, data: bytes, timeout: float = 5) -> int:
        if timeout <= 0:
            raise TimeoutError("F321 UART TX deadline expired before write")
        deadline = time.monotonic() + timeout
        previous_timeout = self.serial.write_timeout
        self.serial.write_timeout = timeout
        try:
            written = self.serial.write(data)
            if written != len(data):
                raise TimeoutError("F321 UART incomplete write")
            # The vendored flush() loops forever while out_waiting is nonzero.
            # Share one deadline between the driver write and queue drain.
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("F321 UART TX queue did not drain before deadline")
                if not self.serial.out_waiting:
                    return written
                time.sleep(min(0.02, remaining))
        except (TimeoutError, original.serial.SerialTimeoutException):
            # Abort queued bytes; do not retry a partial or ambiguous write.
            try:
                self.serial.cancel_write()
                self.serial.reset_output_buffer()
            except Exception:
                pass
            raise
        finally:
            self.serial.write_timeout = previous_timeout


def acquire_topaz(session: UartSession, reboot_sysrq: bool, seconds: int) -> None:
    if reboot_sysrq or not 0 < seconds <= 300:
        raise ValueError("F321 loader requires bounded attach to an existing Topaz prompt")
    deadline = time.monotonic() + seconds
    session.serial.reset_input_buffer()
    session.tail.clear()
    print("OMF321_UART_STAGE=acquiring_prompt", flush=True)

    def probe(payload: bytes) -> None:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("F321 UART prompt deadline expired before probe")
        session.write(payload, timeout=min(5.0, remaining))

    probe(b"\x15\r")
    next_probe = time.monotonic() + PROMPT_RETRY_SECONDS
    retries = 0
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        session.read(timeout=min(0.1, remaining))
        if original.TOPAZ_PROMPT_RE.search(bytes(session.tail)):
            print("OMLYOKO_UART_TOPAZ_READY=1", flush=True)
            return
        if time.monotonic() >= next_probe and retries < PROMPT_RETRIES:
            # Blank CR only; these probes never run during or after loady.
            probe(b"\r")
            retries += 1
            print(f"OMF321_UART_PROMPT_RETRY={retries}", flush=True)
            next_probe = time.monotonic() + PROMPT_RETRY_SECONDS
    raise TimeoutError("F321 UART timeout acquiring topaz prompt; RAM load not started")


class ProgressReporter:
    def __init__(self, path: Path, total: int) -> None:
        self.path = path
        self.total = total
        self.acked = 0
        self.report_error = False

    def update(self, phase: str) -> None:
        value = {
            "schema": "openmitrastar.f321-uart-progress/v1", "phase": phase,
            "updated_at_utc": datetime.now(timezone.utc).isoformat(),
            "monotonic_seconds": time.monotonic(),
            "total_bytes": self.total, "acked_bytes": self.acked,
            "source": "YMODEM sender ACK callback", "flash_writes": 0,
            "progress_is_ram_verification": False,
        }
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            # Close after every callback so progress is observable while the
            # transfer is running, independently of cached directory metadata.
            with self.path.open("a", encoding="ascii") as stream:
                stream.write(json.dumps(value, sort_keys=True) + "\n")
        except OSError:
            # A reader holding a Windows file handle must not abort a transfer.
            if not self.report_error:
                print("OMF321_UART_PROGRESS_FILE_UNAVAILABLE=1", flush=True)
                self.report_error = True

    def callback(self, existing):
        def progress(index: int, name: str, total: int, success: int) -> None:
            existing(index, name, total, success)
            self.total, self.acked = total, success
            self.update("transfer")
        return progress


class F321ModemSocket(original.ModemSocket):
    def write(self, data, timeout: float = 1):
        # The vendor's wrapper catches every exception and retries packets.
        # A failed UART write has unknown delivery; propagate it and stop.
        return self._write(data, timeout)


def main() -> int:
    if any(arg.startswith("--") and arg.split("=", 1)[0] not in OPTIONS for arg in sys.argv[1:]):
        raise SystemExit("F321 loader received an unsupported option")
    parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    parser.add_argument("--attach-topaz", action="store_true")
    parser.add_argument("--reboot-sysrq", action="store_true")
    parser.add_argument("--receiver-ready", action="store_true")
    parser.add_argument("--status", type=Path, required=True)
    parser.add_argument("--expected-size", type=int, required=True)
    args, _ = parser.parse_known_args()
    if not args.attach_topaz or args.reboot_sysrq or args.receiver_ready:
        raise SystemExit("F321 loader permits existing Topaz attach only")
    reporter = ProgressReporter(args.status.with_name("uart-ymodem-progress.jsonl"), args.expected_size)
    previous = original.UartSession, original.acquire_topaz, original.ModemSocket

    class ReportingModem(F321ModemSocket):
        def send(self, paths, callback=None):
            return super().send(paths, reporter.callback(callback or (lambda *_: None)))

    original.UartSession, original.acquire_topaz, original.ModemSocket = UartSession, acquire_topaz, ReportingModem
    reporter.update("starting")
    try:
        result = original.main()
        reporter.update("ram_verified" if result == 0 else "failed")
        return result
    except BaseException:
        reporter.update("failed")
        raise
    finally:
        original.UartSession, original.acquire_topaz, original.ModemSocket = previous


if __name__ == "__main__":
    raise SystemExit(main())
