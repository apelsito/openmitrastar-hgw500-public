"""One immutable, explicitly scoped TFTP/octet read; default is a file-only plan.

--execute starts only this server. It does not authorize LAN/device operations,
change firewall rules, write firmware, reboot, or establish boot acceptance.
No incoming filename, error message or payload is copied into JSON evidence.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import socket
import stat
import struct
import time
from typing import Callable


BLOCK_SIZE = 512
MAX_REQUEST_BYTES = 512
MAX_FILE_BYTES = 0x5E0000
MAX_BLOCKS = 65535
MAX_DATAGRAM = 65535
OP_RRQ, OP_WRQ, OP_DATA, OP_ACK, OP_ERROR = 1, 2, 3, 4, 5
ERR_ACCESS, ERR_ILLEGAL = 2, 4
EVENT_SCHEMA = "openmitrastar.f325-scoped-tftp-event/v1"
RESULT_SCHEMA = "openmitrastar.f325-scoped-tftp/v1"


class TftpFailure(Exception):
    """Only program-defined codes are reported; never packet/OS exception text."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def block_count(byte_count: int) -> int:
    if type(byte_count) is not int or byte_count < 0:
        raise ValueError("invalid byte count")
    count = byte_count // BLOCK_SIZE + 1
    if count > MAX_BLOCKS:
        raise ValueError("transfer would require a block-number wrap")
    return count


@dataclass(frozen=True, slots=True)
class VerifiedPayload:
    source_path: Path
    expected_sha256: str
    expected_bytes: int
    data: bytes = field(repr=False)

    def __post_init__(self) -> None:
        if type(self.data) is not bytes:
            raise ValueError("payload must be immutable bytes")
        if (type(self.expected_bytes) is not int or not 0 <= self.expected_bytes <= MAX_FILE_BYTES
                or len(self.data) != self.expected_bytes):
            raise ValueError("payload byte-count contract failed")
        block_count(self.expected_bytes)
        if (not isinstance(self.expected_sha256, str)
                or not re.fullmatch(r"[0-9a-f]{64}", self.expected_sha256)
                or hashlib.sha256(self.data).hexdigest() != self.expected_sha256):
            raise ValueError("payload SHA-256 contract failed")

    def metadata(self) -> dict:
        return {"path": str(self.source_path), "sha256": self.expected_sha256,
                "bytes": self.expected_bytes, "blocks_including_terminal": block_count(self.expected_bytes)}


def load_verified_file(path: Path, expected_sha256: str, expected_bytes: int) -> VerifiedPayload:
    """Read at most the declared size plus one, then seal immutable bytes once."""
    if type(expected_bytes) is not int or not 0 <= expected_bytes <= MAX_FILE_BYTES:
        raise ValueError("file exceeds the allowed image window")
    if not isinstance(expected_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("invalid expected SHA-256")
    source = Path(path).resolve(strict=True)
    with source.open("rb") as stream:
        descriptor = os.fstat(stream.fileno())
        if not stat.S_ISREG(descriptor.st_mode) or descriptor.st_size != expected_bytes:
            raise ValueError("source is not a regular file of the declared size")
        data = stream.read(expected_bytes + 1)
    return VerifiedPayload(source, expected_sha256, expected_bytes, data)


def exact_ipv4(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("an explicit IPv4 string is required")
    try:
        address = ipaddress.IPv4Address(value)
    except (ValueError, TypeError):
        raise ValueError("an explicit IPv4 address is required") from None
    if address.is_unspecified or address.is_multicast or int(address) == 0xFFFFFFFF:
        raise ValueError("unspecified, multicast and broadcast addresses are forbidden")
    return str(address)


def exact_filename(value: str) -> bytes:
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value):
        raise ValueError("allow-file must be one ASCII basename without path aliases")
    return value.encode("ascii")


def validate_scope(bind: str, allow_client: str, allow_file: str, port: int,
                   timeout: float, ack_timeout: float, max_retries: int) -> tuple[str, str, bytes]:
    bind, allow_client = exact_ipv4(bind), exact_ipv4(allow_client)
    name = exact_filename(allow_file)
    if type(port) is not int or not 0 <= port <= 65535:
        raise ValueError("invalid UDP port")
    if port == 0 and not ipaddress.IPv4Address(bind).is_loopback:
        raise ValueError("an ephemeral listener is restricted to loopback tests")
    if (isinstance(timeout, bool) or not isinstance(timeout, (int, float))
            or not math.isfinite(timeout) or not 0 < timeout <= 3600):
        raise ValueError("timeout must be finite and between zero and 3600 seconds")
    if (isinstance(ack_timeout, bool) or not isinstance(ack_timeout, (int, float))
            or not math.isfinite(ack_timeout) or not 0 < ack_timeout <= 30):
        raise ValueError("invalid ACK timeout")
    if type(max_retries) is not int or not 0 <= max_retries <= 20:
        raise ValueError("retries must be bounded between zero and twenty")
    return bind, allow_client, name


def request_error(packet: bytes, allowed_name: bytes) -> int | None:
    """Accept RRQ/octet and ignore well-formed RFC 2347 option/value pairs.

    No option is negotiated: the response is DATA1 with ordinary 512-byte
    blocks. Unknown ASCII options are safe to ignore after framing validation.
    """
    if not 2 <= len(packet) <= MAX_REQUEST_BYTES:
        return ERR_ILLEGAL
    opcode = struct.unpack("!H", packet[:2])[0]
    if opcode == OP_WRQ:
        return ERR_ACCESS
    if opcode != OP_RRQ:
        return ERR_ILLEGAL
    fields = packet[2:].split(b"\0")
    if len(fields) < 3 or fields[-1] != b"" or (len(fields) - 3) % 2:
        return ERR_ILLEGAL
    name, mode = fields[:2]
    if name != allowed_name:
        return ERR_ACCESS
    if mode.lower() != b"octet":
        return ERR_ILLEGAL
    seen = set()
    for index in range(2, len(fields) - 1, 2):
        option, value = fields[index:index + 2]
        if (not option or not value or not option.isascii() or not value.isascii()
                or option.lower() in seen):
            return ERR_ILLEGAL
        seen.add(option.lower())
    return None


def error_packet(code: int) -> bytes:
    # The message is fixed and cannot reflect any incoming filename/content.
    return struct.pack("!HH", OP_ERROR, code) + b"request denied\0"


def ack_kind(packet: bytes, sender: tuple[str, int], client: tuple[str, int], block: int) -> str:
    if sender != client:
        return "foreign_peer"
    if len(packet) >= 2 and struct.unpack("!H", packet[:2])[0] == OP_ERROR:
        return "client_error"
    if len(packet) != 4:
        return "malformed_ack"
    opcode, received_block = struct.unpack("!HH", packet)
    if opcode != OP_ACK:
        return "malformed_ack"
    return "ack" if received_block == block else "unexpected_ack"


def remaining(deadline: float, clock: Callable[[], float]) -> float:
    value = deadline - clock()
    if value <= 0:
        raise TftpFailure("global_timeout")
    return value


def _udp_socket() -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        # Windows otherwise turns an ICMP response to a rejected request into
        # WSAECONNRESET on a later recvfrom belonging to another request.
        if hasattr(socket, "SIO_UDP_CONNRESET"):
            sock.ioctl(socket.SIO_UDP_CONNRESET, False)
        return sock
    except Exception:
        sock.close()
        raise


def _send_payload(sock: socket.socket, payload: VerifiedPayload, client: tuple[str, int], *,
                  deadline: float, ack_timeout: float, max_retries: int,
                  counts: dict, clock: Callable[[], float]) -> None:
    for block in range(1, block_count(payload.expected_bytes) + 1):
        chunk = payload.data[(block - 1) * BLOCK_SIZE:block * BLOCK_SIZE]
        packet = struct.pack("!HH", OP_DATA, block) + chunk
        acknowledged = False
        for attempt in range(max_retries + 1):
            sock.settimeout(remaining(deadline, clock))
            if sock.sendto(packet, client) != len(packet):
                raise TftpFailure("short_datagram_send")
            counts["data_packets_sent"] += 1
            counts["data_bytes_sent_including_retries"] += len(chunk)
            if attempt:
                counts["retransmissions"] += 1
            ack_deadline = min(deadline, clock() + ack_timeout)
            while True:
                wait = min(remaining(deadline, clock), ack_deadline - clock())
                if wait <= 0:
                    break
                sock.settimeout(wait)
                try:
                    received, sender = sock.recvfrom(MAX_DATAGRAM)
                except socket.timeout:
                    break
                counts["transfer_datagrams_received"] += 1
                received_at = clock()
                if received_at >= deadline:
                    raise TftpFailure("global_timeout")
                kind = ack_kind(received, sender, client, block)
                if kind == "client_error":
                    raise TftpFailure("client_error")
                if received_at >= ack_deadline:
                    counts["late_ack" if kind == "ack" else kind] += 1
                    break
                if kind != "ack":
                    counts[kind] += 1
                    continue
                acknowledged = True
                counts["blocks_acked"] += 1
                counts["payload_bytes_acked"] += len(chunk)
                break
            if acknowledged:
                break
            remaining(deadline, clock)
        if not acknowledged:
            raise TftpFailure("ack_retries_exhausted")


def serve_once(payload: VerifiedPayload, *, bind: str, allow_client: str, allow_file: str,
               port: int = 69, timeout: float = 300, ack_timeout: float = 0.5,
               max_retries: int = 5, on_event: Callable[[dict], None] | None = None,
               clock: Callable[[], float] = time.monotonic) -> dict:
    """Listen once and terminate after the first accepted RRQ, even on failure.

    `payload` is already verified immutable memory: this function never opens a
    source file. The same monotonic deadline bounds listening and every block.
    """
    if type(payload) is not VerifiedPayload:
        raise ValueError("a verified immutable payload is required")
    bind, allow_client, allowed_name = validate_scope(bind, allow_client, allow_file, port,
                                                     timeout, ack_timeout, max_retries)
    counts = dict.fromkeys(("listener_datagrams_received", "foreign_client", "rejected_requests",
                           "transfer_datagrams_received", "foreign_peer", "malformed_ack", "unexpected_ack",
                           "late_ack",
                           "data_packets_sent", "data_bytes_sent_including_retries", "retransmissions",
                           "blocks_acked", "payload_bytes_acked"), 0)
    started = clock()
    deadline = started + timeout
    listener, transfer = None, None
    result = {"schema": RESULT_SCHEMA, "status": "FAIL_TFTP_SINGLE_TRANSFER", "reason": None,
              "bind": bind, "port": port, "allow_client": allow_client, "allow_file": allow_file,
              "file": payload.metadata(), "timeout_seconds": timeout, "ack_timeout_seconds": ack_timeout,
              "max_retries": max_retries, "transfer_started": False, "transfer_complete": False,
              "counts": counts, "raw_content_logged": False, "rejected_filenames_logged": False,
              "flash": False, "boot_verified": False, "sockets_closed": False}

    def emit(event: str, **fields) -> None:
        if on_event is not None:
            on_event({"schema": EVENT_SCHEMA, "event": event, **fields})

    try:
        listener = _udp_socket()
        listener.bind((bind, port))
        result["port"] = listener.getsockname()[1]
        emit("ready", bind=bind, port=result["port"], allow_client=allow_client,
             allow_file=allow_file, file=payload.metadata(), timeout_seconds=timeout)
        while True:
            listener.settimeout(remaining(deadline, clock))
            try:
                packet, client = listener.recvfrom(MAX_DATAGRAM)
            except socket.timeout:
                raise TftpFailure("global_timeout") from None
            counts["listener_datagrams_received"] += 1
            if client[0] != allow_client:
                counts["foreign_client"] += 1
                continue
            denied = request_error(packet, allowed_name)
            if denied is not None:
                counts["rejected_requests"] += 1
                listener.settimeout(remaining(deadline, clock))
                listener.sendto(error_packet(denied), client)
                continue
            # From this point an error is terminal. Bind a distinct transfer
            # TID while the listening port is reserved, then close the listener
            # before DATA so another RRQ cannot start a new session.
            result["transfer_started"] = True
            result["client_tid"] = client[1]
            transfer = _udp_socket()
            transfer.bind((bind, 0))
            result["transfer_tid"] = transfer.getsockname()[1]
            listener.close()
            listener = None
            emit("transfer_started", client=allow_client, client_tid=client[1],
                 transfer_tid=result["transfer_tid"], file=payload.metadata())
            _send_payload(transfer, payload, client, deadline=deadline, ack_timeout=ack_timeout,
                          max_retries=max_retries, counts=counts, clock=clock)
            result.update(status="PASS_TFTP_SINGLE_TRANSFER", transfer_complete=True)
            break
    except TftpFailure as error:
        result["reason"] = error.code
    except Exception as error:
        result["reason"] = "server_error"
        result["error_type"] = type(error).__name__
    finally:
        closed = True
        for sock in (transfer, listener):
            if sock is not None:
                try:
                    sock.close()
                except OSError:
                    closed = False
        result["sockets_closed"] = closed
        if not closed:
            result.update(status="FAIL_TFTP_SINGLE_TRANSFER", reason="socket_close_unproved")
        result["elapsed_seconds"] = round(clock() - started, 6)
    emit("complete" if result["status"] == "PASS_TFTP_SINGLE_TRANSFER" else "failed", result=result)
    return result


def new_output_directory(path: Path) -> Path:
    output = Path(path).absolute()
    for parent in (output, *output.parents):
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise ValueError("output path may not contain a symlink or junction")
    output.mkdir(parents=True, exist_ok=False)
    return output.resolve()


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-bytes", required=True, type=int)
    parser.add_argument("--bind", required=True)
    parser.add_argument("--allow-client", required=True)
    parser.add_argument("--allow-file", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--timeout", default=300, type=float)
    parser.add_argument("--port", default=69, type=int)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args(argv)
    try:
        bind, client, _ = validate_scope(args.bind, args.allow_client, args.allow_file,
                                         args.port, args.timeout, 0.5, 5)
        payload = load_verified_file(args.file, args.expected_sha256, args.expected_bytes)
        if not args.execute:
            print(json.dumps({"schema": RESULT_SCHEMA, "status": "PASS_OFFLINE_TFTP_PLAN", "mode": "dry-run",
                              "bind": bind, "port": args.port, "allow_client": client, "allow_file": args.allow_file,
                              "file": payload.metadata(), "timeout_seconds": args.timeout,
                              "output_dir": str(args.output_dir.absolute()), "network_access": False,
                              "flash": False, "hardware_actions_performed": False}), flush=True)
            return 0
        output = new_output_directory(args.output_dir)
    except Exception as error:
        print(json.dumps({"schema": RESULT_SCHEMA, "status": "FAIL_PREFLIGHT", "error_type": type(error).__name__,
                          "network_access": False, "flash": False}), flush=True)
        return 2

    def record(event: dict) -> None:
        row = {"generated_at_utc": datetime.now(timezone.utc).isoformat(), **event}
        with (output / "events.jsonl").open("a", encoding="ascii", newline="\n") as stream:
            stream.write(json.dumps(row, ensure_ascii=True) + "\n")
        print(json.dumps(row, ensure_ascii=True), flush=True)

    result = serve_once(payload, bind=bind, allow_client=client, allow_file=args.allow_file,
                        port=args.port, timeout=args.timeout, on_event=record)
    result.update(mode="execute", network_access=True, script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    with (output / "result.json").open("x", encoding="ascii", newline="\n") as stream:
        stream.write(json.dumps(result, indent=2, ensure_ascii=True) + "\n")
    return 0 if result["status"] == "PASS_TFTP_SINGLE_TRANSFER" else 1


if __name__ == "__main__":
    raise SystemExit(main())
