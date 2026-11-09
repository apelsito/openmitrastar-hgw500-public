#!/usr/bin/env python3
"""Offline verifier for the redundant Topaz U-Boot recovery contract."""
from __future__ import annotations

import argparse
import pathlib
import struct
import zlib

ENV_DATA_SIZE = 0x6000


def parse_env(blob: bytes) -> dict[str, str]:
    if len(blob) < ENV_DATA_SIZE:
        raise ValueError(f"environment is shorter than {ENV_DATA_SIZE:#x}")
    region = blob[:ENV_DATA_SIZE]
    expected = struct.unpack_from("<I", region)[0]
    actual = zlib.crc32(region[4:]) & 0xFFFFFFFF
    if actual != expected:
        raise ValueError(f"CRC mismatch: stored={expected:08x} calculated={actual:08x}")
    result: dict[str, str] = {}
    for raw in region[4:].split(b"\0"):
        if not raw:
            break
        if b"=" not in raw:
            raise ValueError("malformed environment entry")
        key, value = raw.split(b"=", 1)
        result[key.decode("ascii")] = value.decode("ascii")
    return result


def verify_contract(primary: bytes, backup: bytes) -> dict[str, str]:
    env = parse_env(primary[:ENV_DATA_SIZE])
    backup_env = parse_env(backup[:ENV_DATA_SIZE])
    for name, candidate in (("primary", env), ("backup", backup_env)):
        if candidate.get("bootcmd") != "bootselect":
            raise ValueError(f"{name} bootcmd is not bootselect")
        if candidate.get("bootselect") != "0":
            raise ValueError(f"{name} bootselect is not the live slot (0)")
    return env


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("primary", type=pathlib.Path)
    parser.add_argument("backup", type=pathlib.Path)
    args = parser.parse_args()
    env = verify_contract(args.primary.read_bytes(), args.backup.read_bytes())
    print("RECOVERY_ENV_OK=1")
    print(f"bootcmd={env['bootcmd']}")
    print(f"bootselect={env['bootselect']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
