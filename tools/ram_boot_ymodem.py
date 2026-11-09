#!/usr/bin/env python3
"""Safely load a pinned OpenMitraStar image into RAM through U-Boot YMODEM.

This tool is intentionally narrower than a general serial console. It accepts
only the HGW-500BNA-QCv2 RAM staging address and emits only ``loady``,
``iminfo`` and (when explicitly requested) ``bootm``. It never writes flash or
the U-Boot environment.
"""

from __future__ import annotations

import argparse
import binascii
import hashlib
import re
import struct
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import BinaryIO, Iterable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import serial  # noqa: E402
import ymodem  # noqa: E402
from ymodem.Protocol import ProtocolStyleManagement, ProtocolType  # noqa: E402
from ymodem.Socket import ModemSocket  # noqa: E402


SLOT_BYTES = 0x7A0000
SAFE_LOAD_ADDRESS = 0x87000000
SAFE_STAGING_END = SAFE_LOAD_ADDRESS + SLOT_BYTES
UIMAGE_HEADER_BYTES = 64
UIMAGE_MAGIC = 0x27051956
RAS_PAYLOAD_OFFSET = 0x2000
OEM_ARC_ARCH = 0x13
TOPAZ_PROMPT = b"topaz>"
DEFAULT_READY_MARKER = b"OMSSH_READY port=22"
EXPECTED_YMODEM_VERSION = "1.5.3"
YMODEM_STYLE_ID = "UNIX_RZ_SZ"
ALLOWED_UBOOT_COMMANDS = frozenset({"loady", "iminfo", "bootm"})
FORBIDDEN_UBOOT_WORDS = frozenset(
    {
        "cp",
        "erase",
        "env",
        "mtd",
        "nand",
        "protect",
        "saveenv",
        "setenv",
        "sf",
        "write",
    }
)
SHA256_RE = re.compile(r"[0-9a-fA-F]{64}\Z")
TRANSFER_BYTES_RE = re.compile(r"Bytes transferred\s*=\s*(\d+)")
IMINFO_CRC_OK_RE = re.compile(r"Verifying Checksum\s*\.\.\.\s*OK")


class SafetyError(ValueError):
    """A local safety gate rejected the requested operation."""


@dataclass(frozen=True)
class ImageManifest:
    path: Path
    size: int
    sha256: str
    load_address: int
    uimage_payload_size: int
    uimage_name: str


class Transcript:
    """Tee human-readable events and UART output to a durable artifact."""

    def __init__(self, path: Path, stream: BinaryIO | None = None):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._stream = stream or self.path.open("xb")
        self._owns_stream = stream is None

    def close(self) -> None:
        self._stream.flush()
        if self._owns_stream:
            self._stream.close()

    def __enter__(self) -> "Transcript":
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def event(self, message: str) -> None:
        line = f"[{utc_now()}] {message}\n"
        self._stream.write(line.encode("utf-8", "replace"))
        self._stream.flush()
        print(message, flush=True)

    def uart(self, data: bytes) -> None:
        if not data:
            return
        self._stream.write(data)
        self._stream.flush()
        print(data.decode("utf-8", "replace"), end="", flush=True)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def default_log_path() -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
    return ROOT / "outputs" / "uart-live" / f"ram-boot-ymodem-{stamp}.log"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def parse_load_address(value: str | int) -> int:
    if isinstance(value, int):
        address = value
    else:
        try:
            address = int(value, 0)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("load address must be an integer") from exc
    if address != SAFE_LOAD_ADDRESS:
        raise argparse.ArgumentTypeError(
            f"only safe RAM staging address 0x{SAFE_LOAD_ADDRESS:08x} is allowed"
        )
    return address


def parse_positive_size(value: str | int) -> int:
    try:
        size = int(value, 0) if isinstance(value, str) else value
    except ValueError as exc:
        raise argparse.ArgumentTypeError("expected size must be an integer") from exc
    if size <= 0 or size > SLOT_BYTES:
        raise argparse.ArgumentTypeError(
            f"expected size must be within 1..{SLOT_BYTES} bytes"
        )
    return size


def normalize_expected_sha256(value: str) -> str:
    if not SHA256_RE.fullmatch(value):
        raise SafetyError("expected SHA-256 must contain exactly 64 hex characters")
    return value.lower()


def inspect_uimage(path: Path) -> tuple[int, str]:
    """Validate the HGW-500BNA Bootbase RAS header and payload CRC locally."""

    with path.open("rb") as stream:
        header = stream.read(UIMAGE_HEADER_BYTES)
        if len(header) != UIMAGE_HEADER_BYTES:
            raise SafetyError("image is shorter than a uImage header")
        fields = struct.unpack(">7I4B32s", header)
        magic, header_crc, _timestamp, payload_size, *_rest = fields
        if magic != UIMAGE_MAGIC:
            raise SafetyError(f"bad uImage magic 0x{magic:08x}")

        zeroed_header = header[:4] + b"\0\0\0\0" + header[8:]
        actual_header_crc = binascii.crc32(zeroed_header) & 0xFFFFFFFF
        if actual_header_crc != header_crc:
            raise SafetyError(
                "uImage header CRC mismatch "
                f"expected=0x{header_crc:08x} actual=0x{actual_header_crc:08x}"
            )

        data_crc = fields[6]
        os_id, arch, image_type, compression = fields[7:11]
        if arch != OEM_ARC_ARCH:
            raise SafetyError(
                f"unexpected image architecture 0x{arch:02x}; expected ARC 0x13"
            )
        if os_id != 5 or image_type != 2 or compression not in (0, 3):
            raise SafetyError(
                "unexpected RAS image tuple "
                f"os={os_id} type={image_type} compression={compression}"
            )
        expected_file_size = RAS_PAYLOAD_OFFSET + payload_size
        actual_file_size = path.stat().st_size
        if actual_file_size != expected_file_size:
            raise SafetyError(
                "RAS image length mismatch "
                f"expected={expected_file_size} actual={actual_file_size}"
            )
        stream.seek(RAS_PAYLOAD_OFFSET)
        remaining = payload_size
        running_crc = 0
        while remaining:
            chunk = stream.read(min(1024 * 1024, remaining))
            if not chunk:
                raise SafetyError(
                    f"uImage payload truncated expected={payload_size} bytes"
                )
            running_crc = binascii.crc32(chunk, running_crc)
            remaining -= len(chunk)
        running_crc &= 0xFFFFFFFF
        if running_crc != data_crc:
            raise SafetyError(
                "uImage data CRC mismatch "
                f"expected=0x{data_crc:08x} actual=0x{running_crc:08x}"
            )

    name = fields[-1].split(b"\0", 1)[0].decode("ascii", "replace")
    return payload_size, name


def preflight_image(
    image: Path,
    expected_sha256: str,
    expected_size: int,
    load_address: int,
) -> ImageManifest:
    image = image.resolve(strict=True)
    if not image.is_file():
        raise SafetyError(f"not a regular image: {image}")
    if "NO-FLASH" not in image.name:
        raise SafetyError("refusing image without explicit NO-FLASH marker")

    expected_digest = normalize_expected_sha256(expected_sha256)
    size = image.stat().st_size
    if size != expected_size:
        raise SafetyError(f"size mismatch expected={expected_size} actual={size}")
    if size <= 0 or size > SLOT_BYTES:
        raise SafetyError(f"image outside one slot: {size}")
    if load_address != SAFE_LOAD_ADDRESS:
        raise SafetyError(f"unsafe load address 0x{load_address:08x}")
    if load_address + size > SAFE_STAGING_END:
        raise SafetyError("image exceeds the validated RAM staging window")

    digest = sha256(image)
    if digest != expected_digest:
        raise SafetyError(
            f"sha256 mismatch expected={expected_digest} actual={digest}"
        )
    payload_size, image_name = inspect_uimage(image)
    return ImageManifest(
        path=image,
        size=size,
        sha256=digest,
        load_address=load_address,
        uimage_payload_size=payload_size,
        uimage_name=image_name,
    )


def assert_manifest_unchanged(manifest: ImageManifest) -> None:
    """Close the preflight-to-transfer TOCTOU window as far as practical."""

    current_size = manifest.path.stat().st_size
    if current_size != manifest.size:
        raise SafetyError(
            f"image changed after preflight: size was={manifest.size} now={current_size}"
        )
    current_digest = sha256(manifest.path)
    if current_digest != manifest.sha256:
        raise SafetyError(
            "image changed after preflight: "
            f"sha256 was={manifest.sha256} now={current_digest}"
        )


def uboot_command(command: str, address: int) -> bytes:
    """Build one command from the fixed RAM-only allowlist."""

    if command not in ALLOWED_UBOOT_COMMANDS:
        raise SafetyError(f"U-Boot command is not allowlisted: {command!r}")
    if command.lower() in FORBIDDEN_UBOOT_WORDS:
        raise SafetyError(f"persistent U-Boot command rejected: {command!r}")
    if address != SAFE_LOAD_ADDRESS:
        raise SafetyError(f"unsafe command address 0x{address:08x}")
    return f"{command} 0x{address:08x}\r".encode("ascii")


def read_until(
    port: serial.Serial,
    needle: bytes,
    timeout: float,
    transcript: Transcript | None = None,
) -> bytes:
    deadline = time.monotonic() + timeout
    output = bytearray()
    while time.monotonic() < deadline:
        chunk = port.read(port.in_waiting or 1)
        if chunk:
            output.extend(chunk)
            if transcript:
                transcript.uart(chunk)
            if needle in output:
                return bytes(output)
    raise TimeoutError(f"timeout waiting for {needle!r}")


def write_serial(port: serial.Serial, data: bytes) -> None:
    written = port.write(data)
    port.flush()
    if written != len(data):
        raise IOError(f"short serial write expected={len(data)} actual={written}")


def recover_topaz_prompt(
    port: serial.Serial,
    transcript: Transcript,
    timeout_per_attempt: float = 3.0,
) -> bytes:
    """Leave idle command mode or an interrupted ``loady`` at ``topaz>``."""

    sequences: Iterable[tuple[str, bytes]] = (
        ("newline", b"\r"),
        ("ctrl_c", b"\x03\r"),
        ("ymodem_can", b"\x18" * 8 + b"\x08" * 8 + b"\x03\r"),
        ("ctrl_c_burst", b"\x03" * 3 + b"\r"),
    )
    captured = bytearray()
    for attempt, (name, sequence) in enumerate(sequences, start=1):
        transcript.event(f"OMYMODEM_RECOVER attempt={attempt} sequence={name}")
        write_serial(port, sequence)
        try:
            captured.extend(
                read_until(port, TOPAZ_PROMPT, timeout_per_attempt, transcript)
            )
            transcript.event(
                f"OMYMODEM_STAGE_PASS=topaz_prompt attempt={attempt} sequence={name}"
            )
            return bytes(captured)
        except TimeoutError:
            continue
    raise RuntimeError("unable to recover topaz prompt after YMODEM abort sequence")


def validate_transfer_receipt(output: bytes, expected_size: int) -> None:
    decoded = output.decode("utf-8", "replace")
    matches = TRANSFER_BYTES_RE.findall(decoded)
    if not matches:
        raise RuntimeError("U-Boot did not report a YMODEM byte count")
    actual_size = int(matches[-1])
    if actual_size != expected_size:
        raise RuntimeError(
            f"U-Boot transfer size mismatch expected={expected_size} actual={actual_size}"
        )


def validate_iminfo(output: bytes) -> None:
    decoded = output.decode("utf-8", "replace")
    if not IMINFO_CRC_OK_RE.search(decoded):
        raise RuntimeError("U-Boot iminfo checksum gate failed")
    lowered = decoded.lower()
    if "bad data crc" in lowered or "bad header checksum" in lowered:
        raise RuntimeError("U-Boot iminfo reported a CRC failure")


def ymodem_send(
    port: serial.Serial,
    manifest: ImageManifest,
    transcript: Transcript,
) -> None:
    styles = ProtocolStyleManagement().get_available_styles()
    if YMODEM_STYLE_ID not in styles:
        raise RuntimeError(
            f"YMODEM dependency lacks required style {YMODEM_STYLE_ID!r}"
        )

    def getc(size: int, timeout: float = 3) -> bytes:
        port.timeout = timeout
        return port.read(size)

    def putc(data: bytes | bytearray, timeout: float = 3) -> int:
        port.write_timeout = timeout
        written = port.write(data)
        port.flush()
        return written

    modem = ModemSocket(
        getc,
        putc,
        protocol_type=ProtocolType.YMODEM,
        packet_size=1024,
        style_id=YMODEM_STYLE_ID,  # Unix rz/sz framing accepted by U-Boot loady.
    )
    last_percent = -1

    def progress(_index: int, _name: str, total: int, sent: int) -> None:
        nonlocal last_percent
        percent = int(sent * 100 / total) if total else 100
        if percent >= last_percent + 5 or percent == 100:
            last_percent = percent
            transcript.event(
                f"OMYMODEM_PROGRESS percent={percent} sent={sent} total={total}"
            )

    if not modem.send([str(manifest.path)], progress):
        raise RuntimeError("YMODEM transfer failed")


def run_serial_boot(
    port: serial.Serial,
    manifest: ImageManifest,
    transcript: Transcript,
    boot: bool,
    ready_marker: bytes,
    boot_timeout: float,
) -> None:
    assert_manifest_unchanged(manifest)
    recover_topaz_prompt(port, transcript)

    port.reset_input_buffer()
    write_serial(port, uboot_command("loady", manifest.load_address))
    transcript.event(
        f"OMYMODEM_LOADY_SENT address=0x{manifest.load_address:08x} flash=0 env=0"
    )
    try:
        ymodem_send(port, manifest, transcript)
        transfer_tail = read_until(port, TOPAZ_PROMPT, 30, transcript)
        validate_transfer_receipt(transfer_tail, manifest.size)
        assert_manifest_unchanged(manifest)
        transcript.event("OMYMODEM_STAGE_PASS=transfer_size")
    except BaseException:
        transcript.event("OMYMODEM_TRANSFER_ABORT requested=1")
        recover_topaz_prompt(port, transcript)
        raise

    try:
        port.reset_input_buffer()
        write_serial(port, uboot_command("iminfo", manifest.load_address))
        image_info = read_until(port, TOPAZ_PROMPT, 30, transcript)
        validate_iminfo(image_info)
        transcript.event("OMYMODEM_STAGE_PASS=iminfo_crc")
    except BaseException:
        transcript.event("OMYMODEM_IMINFO_ABORT requested=1")
        recover_topaz_prompt(port, transcript)
        raise

    if not boot:
        transcript.event("OMYMODEM_RAM_LOAD_PASS bootm=0 flash=0 env=0")
        return

    write_serial(port, uboot_command("bootm", manifest.load_address))
    transcript.event("OMYMODEM_BOOTM_SENT flash=0 env=0")
    read_until(port, ready_marker, boot_timeout, transcript)
    transcript.event(
        f"OMYMODEM_RAM_BOOT_PASS ready_marker={ready_marker.decode('ascii')}"
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validated RAM-only YMODEM loader for HGW-500BNA-QCv2"
    )
    parser.add_argument("image", type=Path)
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument(
        "--load-address", type=parse_load_address, default=SAFE_LOAD_ADDRESS
    )
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-size", type=parse_positive_size, required=True)
    parser.add_argument("--log", type=Path)
    parser.add_argument("--boot", action="store_true")
    parser.add_argument("--boot-timeout", type=float, default=180.0)
    parser.add_argument("--ready-marker", default=DEFAULT_READY_MARKER.decode("ascii"))
    parser.add_argument(
        "--preflight-only",
        action="store_true",
        help="validate artifact and create a log without opening the serial port",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    log_path = (args.log or default_log_path()).resolve()
    ready_marker = args.ready_marker.encode("ascii", "strict")
    if not ready_marker or len(ready_marker) > 128:
        raise SystemExit("ready marker must contain 1..128 ASCII bytes")
    if args.boot_timeout <= 0:
        raise SystemExit("boot timeout must be positive")

    with Transcript(log_path) as transcript:
        try:
            transcript.event(f"OMYMODEM_LOG artifact={log_path} flash=0 env=0")
            if ymodem.__version__ != EXPECTED_YMODEM_VERSION:
                raise SafetyError(
                    "unexpected YMODEM dependency "
                    f"expected={EXPECTED_YMODEM_VERSION} actual={ymodem.__version__}"
                )
            transcript.event(f"OMYMODEM_DEPENDENCY ymodem={ymodem.__version__}")
            manifest = preflight_image(
                args.image,
                args.expected_sha256,
                args.expected_size,
                args.load_address,
            )
            transcript.event(
                "OMYMODEM_PREFLIGHT_PASS "
                f"image={manifest.path.name} bytes={manifest.size} "
                f"sha256={manifest.sha256} load=0x{manifest.load_address:08x} "
                f"uimage_payload={manifest.uimage_payload_size} "
                f"uimage_name={manifest.uimage_name!r} flash=0 env=0"
            )
            if args.preflight_only:
                transcript.event("OMYMODEM_PREFLIGHT_ONLY_PASS serial_opened=0")
                return 0

            port = serial.Serial(
                args.port,
                args.baud,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=0.1,
                write_timeout=3,
                rtscts=False,
                dsrdtr=False,
            )
            try:
                port.dtr = False
                port.rts = False
                transcript.event(
                    f"OMYMODEM_SERIAL_OPEN port={args.port} baud={args.baud}"
                )
                run_serial_boot(
                    port,
                    manifest,
                    transcript,
                    args.boot,
                    ready_marker,
                    args.boot_timeout,
                )
            finally:
                port.close()
                transcript.event("OMYMODEM_SERIAL_CLOSED")
            return 0
        except BaseException as exc:
            transcript.event(
                f"OMYMODEM_FAIL type={type(exc).__name__} reason={exc}"
            )
            raise


if __name__ == "__main__":
    raise SystemExit(main())
