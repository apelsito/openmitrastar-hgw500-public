#!/usr/bin/env python3
"""Load one exact image into Topaz U-Boot RAM over UART/YMODEM.

This tool never writes flash or environment variables. It owns the serial port
for the reboot/autoboot catch, YMODEM transfer, and RAM integrity checks, then
returns with the ``topaz>`` prompt ready for a separate guarded flash step.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
import zlib


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import serial  # type: ignore  # vendored under work/pydeps
from ymodem.Protocol import ProtocolType  # type: ignore
from ymodem.Socket import ModemSocket  # type: ignore


PROMPT_RE = re.compile(rb"(?:topaz|ZHAL)>\s*$")
TOPAZ_PROMPT_RE = re.compile(rb"topaz>\s*$")


class UartSession:
    def __init__(self, port: str, baud: int, log_path: Path) -> None:
        self.serial = serial.Serial(
            port=None,
            baudrate=baud,
            bytesize=8,
            parity="N",
            stopbits=1,
            timeout=0.1,
            write_timeout=5,
            xonxoff=False,
            rtscts=False,
            dsrdtr=False,
        )
        self.serial.port = port
        self.serial.dtr = False
        self.serial.rts = False
        self.serial.open()
        self.log = log_path.open("wb")
        self.tail = bytearray()

    def close(self) -> None:
        self.log.close()
        self.serial.close()

    def read(self, size: int = 4096, timeout: float = 0.1) -> bytes:
        old_timeout = self.serial.timeout
        self.serial.timeout = timeout
        try:
            data = self.serial.read(size)
        finally:
            self.serial.timeout = old_timeout
        if data:
            self.log.write(data)
            self.log.flush()
            self.tail.extend(data)
            if len(self.tail) > 131072:
                del self.tail[:-131072]
        return data

    def write(self, data: bytes, timeout: float = 5) -> int:
        old_timeout = self.serial.write_timeout
        self.serial.write_timeout = timeout
        try:
            written = self.serial.write(data)
            self.serial.flush()
            return written
        finally:
            self.serial.write_timeout = old_timeout

    def line(self, command: str) -> None:
        self.write(command.encode("ascii") + b"\r")

    def wait_for(self, pattern: re.Pattern[bytes], seconds: int, stage: str) -> bytes:
        start = len(self.tail)
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            self.read(timeout=0.1)
            current = bytes(self.tail[start:])
            if pattern.search(current):
                return current
        raise TimeoutError(f"UART timeout during {stage}")

    def command(self, command: str, seconds: int = 60) -> bytes:
        self.tail.clear()
        self.line(command)
        return self.wait_for(TOPAZ_PROMPT_RE, seconds, command)


def acquire_topaz(session: UartSession, reboot_sysrq: bool, seconds: int) -> None:
    session.serial.reset_input_buffer()
    session.tail.clear()
    if reboot_sysrq:
        session.serial.break_condition = True
        time.sleep(0.6)
        session.serial.break_condition = False
        time.sleep(0.15)
        session.write(b"b")
        print("OMLYOKO_UART_SYSRQ_REBOOT_SENT=1", flush=True)
    else:
        session.write(b"\x15\r")

    deadline = time.monotonic() + seconds
    last_break = 0.0
    zhal_escaped = False
    while time.monotonic() < deadline:
        session.read(timeout=0.1)
        tail = bytes(session.tail)
        now = time.monotonic()
        if b"Hit any key" in tail[-4096:] and now - last_break > 0.8:
            session.write(b" \r")
            last_break = now
        if re.search(rb"ZHAL>\s*$", tail) and not zhal_escaped:
            session.write(b"\x15\x08ATGU\r")
            zhal_escaped = True
            session.tail.clear()
        if TOPAZ_PROMPT_RE.search(bytes(session.tail)):
            print("OMLYOKO_UART_TOPAZ_READY=1", flush=True)
            return
    raise TimeoutError("UART timeout acquiring topaz prompt")


def parse_crc(output: bytes) -> str:
    matches = re.findall(rb"[0-9a-fA-F]{8}:\s+([0-9a-fA-F]{8})", output)
    if not matches:
        raise ValueError("CRC32 result word missing")
    return matches[-1].decode("ascii").lower()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--address", default="0x83000000")
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-size", required=True, type=int)
    parser.add_argument("--expected-crc32", required=True)
    parser.add_argument("--log", required=True, type=Path)
    parser.add_argument("--status", required=True, type=Path)
    parser.add_argument("--reboot-sysrq", action="store_true")
    parser.add_argument("--attach-topaz", action="store_true")
    parser.add_argument("--receiver-ready", action="store_true")
    parser.add_argument("--prompt-timeout", type=int, default=240)
    args = parser.parse_args()

    image = args.file.resolve()
    data = image.read_bytes()
    observed_sha = hashlib.sha256(data).hexdigest()
    observed_crc = f"{zlib.crc32(data) & 0xffffffff:08x}"
    if len(data) != args.expected_size:
        raise SystemExit("candidate size mismatch before UART")
    if observed_sha != args.expected_sha256.lower():
        raise SystemExit("candidate SHA-256 mismatch before UART")
    if observed_crc != args.expected_crc32.lower():
        raise SystemExit("candidate CRC32 mismatch before UART")

    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.status.parent.mkdir(parents=True, exist_ok=True)
    session = UartSession(args.port, args.baud, args.log)
    sent = 0
    started = time.monotonic()
    try:
        if args.receiver_ready:
            print("OMLYOKO_UART_YMODEM_RECEIVER_ALREADY_READY=1", flush=True)
        else:
            acquire_topaz(session, args.reboot_sysrq, args.prompt_timeout)
            session.tail.clear()
            session.line(f"loady {int(args.address, 0):08x}")
            session.wait_for(re.compile(rb"Ready for binary \(ymodem\) download", re.I), 20, "loady ready")

        def modem_read(size: int, timeout: float = 3) -> bytes:
            return session.read(size=size, timeout=timeout)

        def modem_write(payload: bytes, timeout: float = 3) -> int:
            nonlocal sent
            sent += len(payload)
            return session.write(payload, timeout=timeout)

        last_percent = -1

        def progress(_index: int, _name: str, total: int, success: int) -> None:
            nonlocal last_percent
            percent = int(success * 100 / total) if total else 100
            if percent >= last_percent + 5 or percent == 100:
                last_percent = percent
                print(f"OMLYOKO_UART_YMODEM_PROGRESS={percent} bytes={success}/{total}", flush=True)

        modem = ModemSocket(modem_read, modem_write, packet_size=1024, protocol_type=ProtocolType.YMODEM)
        if not modem.send([str(image)], progress):
            raise RuntimeError("YMODEM sender reported failure")

        if TOPAZ_PROMPT_RE.search(bytes(session.tail)):
            transfer_output = bytes(session.tail)
        else:
            transfer_output = session.wait_for(TOPAZ_PROMPT_RE, 90, "loady completion")
        sizes = re.findall(rb"Total Size\s*=\s*0x[0-9a-fA-F]+\s*=\s*([0-9]+) Bytes", transfer_output)
        if sizes and int(sizes[-1]) != args.expected_size:
            raise ValueError(f"U-Boot received unexpected byte count: {int(sizes[-1])}")

        filesize_output = session.command("printenv filesize", 20)
        expected_hex = f"{args.expected_size:x}".encode("ascii")
        if not re.search(rb"(?m)^filesize=" + re.escape(expected_hex) + rb"\r?$", filesize_output, re.I):
            raise ValueError("U-Boot filesize does not match candidate")
        iminfo = session.command(f"iminfo {int(args.address, 0):08x}", 90)
        if b"Verifying Checksum ... OK" not in iminfo:
            raise ValueError("U-Boot iminfo rejected candidate")
        crc_output = session.command(
            f"crc32 {int(args.address, 0):08x} {args.expected_size:08x} 84000000; md.l 84000000 1",
            120,
        )
        target_crc = parse_crc(crc_output)
        if target_crc != args.expected_crc32.lower():
            raise ValueError(f"RAM CRC mismatch expected={args.expected_crc32} actual={target_crc}")

        result = {
            "schema": "openmitrastar.uart-ymodem-load/v1",
            "status": "PASS",
            "port": args.port,
            "address": f"0x{int(args.address, 0):08x}",
            "candidate": str(image),
            "bytes": args.expected_size,
            "sha256": observed_sha,
            "crc32": observed_crc,
            "serial_bytes_written": sent,
            "elapsed_seconds": round(time.monotonic() - started, 3),
            "flash_writes": 0,
            "environment_writes": 0,
        }
        args.status.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(
            f"OMLYOKO_UART_YMODEM_RAM_LOAD_PASS=1 address={result['address']} "
            f"bytes={args.expected_size} crc32={observed_crc} flash_writes=0",
            flush=True,
        )
        return 0
    finally:
        session.close()


if __name__ == "__main__":
    raise SystemExit(main())
