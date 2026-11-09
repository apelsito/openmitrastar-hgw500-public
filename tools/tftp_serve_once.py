#!/usr/bin/env python3
"""Minimal read-only TFTP server for one-off firmware validation transfers.

This intentionally implements only RRQ/octet reads. It rejects writes and paths
outside the configured root so it can be used as a narrow transfer helper.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
from pathlib import Path
import socket
import struct
import sys
import time


OP_RRQ = 1
OP_WRQ = 2
OP_DATA = 3
OP_ACK = 4
OP_ERROR = 5

ERR_NOT_FOUND = 1
ERR_ACCESS = 2
ERR_ILLEGAL = 4

BLOCK_SIZE = 512


def packet_error(code: int, message: str) -> bytes:
    return struct.pack("!HH", OP_ERROR, code) + message.encode("ascii", "replace") + b"\0"


def parse_request(packet: bytes) -> tuple[int, str, str]:
    if len(packet) < 4:
        raise ValueError("short packet")
    opcode = struct.unpack("!H", packet[:2])[0]
    parts = packet[2:].split(b"\0")
    if len(parts) < 2:
        raise ValueError("missing filename or mode")
    filename = parts[0].decode("utf-8", "replace")
    mode = parts[1].decode("ascii", "replace").lower()
    return opcode, filename, mode


def resolve_under_root(root: Path, requested: str) -> Path:
    clean = requested.replace("\\", "/").lstrip("/")
    candidate = (root / clean).resolve()
    root_resolved = root.resolve()
    if os.path.commonpath([str(root_resolved), str(candidate)]) != str(root_resolved):
        raise PermissionError(requested)
    return candidate


def serve_file(
    path: Path,
    client: tuple[str, int],
    timeout: float,
    retries: int,
    bind: str = "0.0.0.0",
) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(timeout)
    try:
        sock.bind((bind, 0))
        with path.open("rb") as fh:
            block = 1
            while True:
                payload = fh.read(BLOCK_SIZE)
                data = struct.pack("!HH", OP_DATA, block) + payload
                for attempt in range(retries):
                    sock.sendto(data, client)
                    try:
                        ack, sender = sock.recvfrom(516)
                    except socket.timeout:
                        continue
                    if sender != client or len(ack) < 4:
                        continue
                    op, ack_block = struct.unpack("!HH", ack[:4])
                    if op == OP_ACK and ack_block == block:
                        break
                    if op == OP_ERROR:
                        raise RuntimeError("client rejected transfer")
                else:
                    raise TimeoutError(f"no ACK for block {block}")
                if len(payload) < BLOCK_SIZE:
                    return
                block = (block + 1) & 0xFFFF
                if block == 0:
                    block = 1
    finally:
        sock.close()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--bind", default="0.0.0.0")
    parser.add_argument("--port", default=69, type=int)
    parser.add_argument("--timeout", default=120.0, type=float)
    parser.add_argument("--ack-timeout", default=0.5, type=float)
    parser.add_argument("--retries", default=20, type=int)
    parser.add_argument("--once", action="store_true", help="exit after one request")
    parser.add_argument("--allow-client", type=ipaddress.IPv4Address)
    parser.add_argument("--allow-file", help="Exact RRQ filename allowed, without path aliases")
    args = parser.parse_args()

    root = args.root.resolve()
    if not root.is_dir():
        print(f"root does not exist: {root}", file=sys.stderr)
        return 2

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(1.0)
    try:
        sock.bind((args.bind, args.port))
    except OSError as exc:
        print(f"bind failed on {args.bind}:{args.port}: {exc}", file=sys.stderr)
        return 3

    print(f"TFTP read-only server on {args.bind}:{args.port}, root={root}", flush=True)
    deadline = time.time() + args.timeout
    try:
        while time.time() < deadline:
            try:
                packet, client = sock.recvfrom(2048)
            except socket.timeout:
                continue
            # Reject other hosts before parsing/logging requests or opening files.
            if args.allow_client is not None and client[0] != str(args.allow_client):
                continue
            try:
                opcode, filename, mode = parse_request(packet)
                print(f"request opcode={opcode} filename={filename!r} mode={mode!r} client={client}", flush=True)
                if opcode == OP_WRQ:
                    sock.sendto(packet_error(ERR_ACCESS, "write disabled"), client)
                    continue
                if opcode != OP_RRQ:
                    sock.sendto(packet_error(ERR_ILLEGAL, "only RRQ supported"), client)
                    continue
                if args.allow_file is not None and filename != args.allow_file:
                    sock.sendto(packet_error(ERR_ACCESS, "file disabled"), client)
                    continue
                if mode not in {"octet", "netascii"}:
                    sock.sendto(packet_error(ERR_ILLEGAL, "unsupported mode"), client)
                    continue
                path = resolve_under_root(root, filename)
                if not path.is_file():
                    sock.sendto(packet_error(ERR_NOT_FOUND, "not found"), client)
                    continue
                serve_file(
                    path,
                    client,
                    timeout=args.ack_timeout,
                    retries=args.retries,
                    bind=args.bind,
                )
                print(f"served {path.name} to {client}", flush=True)
                if args.once:
                    return 0
            except Exception as exc:  # keep the listener alive for bad packets
                print(f"request failed: {exc}", file=sys.stderr, flush=True)
                try:
                    sock.sendto(packet_error(ERR_ILLEGAL, "request failed"), client)
                except Exception:
                    pass
    finally:
        sock.close()
    print("timeout waiting for request", file=sys.stderr)
    return 4


if __name__ == "__main__":
    raise SystemExit(main())
