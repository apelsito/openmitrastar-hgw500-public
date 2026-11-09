#!/usr/bin/env python3
"""Tiny read-only TFTP server for the MitraStar lab."""

from __future__ import annotations

import argparse
import pathlib
import socket
import struct


BLKSIZE = 512


def serve_file(sock: socket.socket, root: pathlib.Path, addr: tuple[str, int], filename: str) -> None:
    safe = filename.replace("\\", "/").lstrip("/")
    if ".." in safe.split("/"):
        return
    path = root / safe
    if not path.is_file():
        sock.sendto(struct.pack("!HH", 5, 1) + b"not found\x00", addr)
        return
    with path.open("rb") as f:
        block = 1
        while True:
            data = f.read(BLKSIZE)
            packet = struct.pack("!HH", 3, block) + data
            for _ in range(8):
                sock.sendto(packet, addr)
                sock.settimeout(3)
                try:
                    ack, ack_addr = sock.recvfrom(2048)
                except socket.timeout:
                    continue
                if ack_addr == addr and len(ack) >= 4 and ack[:2] == b"\x00\x04":
                    ack_block = struct.unpack("!H", ack[2:4])[0]
                    if ack_block == block:
                        break
            else:
                return
            if len(data) < BLKSIZE:
                return
            block = (block + 1) & 0xFFFF


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default="work/tftp")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=69)
    args = parser.parse_args()
    root = pathlib.Path(args.root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((args.host, args.port))
    print(f"TFTP serving {root} on {args.host}:{args.port}", flush=True)
    while True:
        data, addr = sock.recvfrom(2048)
        if len(data) < 4:
            continue
        op = struct.unpack("!H", data[:2])[0]
        if op != 1:
            continue
        parts = data[2:].split(b"\x00")
        if not parts:
            continue
        filename = parts[0].decode("utf-8", "ignore")
        print(f"RRQ {filename} from {addr[0]}:{addr[1]}", flush=True)
        child = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        child.bind((args.host, 0))
        serve_file(child, root, addr, filename)
        child.close()


if __name__ == "__main__":
    raise SystemExit(main())
