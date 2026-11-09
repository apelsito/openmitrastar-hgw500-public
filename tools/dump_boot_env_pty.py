#!/usr/bin/env python3
"""Dump both 64 KiB Bootbase environment copies and verify their CRC32."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import struct
import zlib

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


# Quantenna reserves a 64 KiB erase block for each copy, but the U-Boot
# environment is only 24 KiB.  The little-endian CRC at offset zero covers
# exactly the remaining 0x5ffc bytes of that logical environment.  Bytes from
# 0x6000 through 0xffff are outside the CRC and normally remain erased.
ENV_LOGICAL_SIZE = 0x6000


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", default="192.168.1.90")
    parser.add_argument(
        "--output", type=Path, default=ROOT / "outputs" / "kernel-port" / "bootcfg-current"
    )
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)

    user, password = credentials()
    ssh = os.path.join(os.environ["WINDIR"], "System32", "OpenSSH", "ssh.exe")
    proc = PtyProcess.spawn([
        ssh, "-tt", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@{args.router}",
    ], cwd=str(ROOT))
    read_until(proc, "password:", 20)
    proc.write(password + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)

    for index in (1, 2):
        begin = f"__ENV{index}_HEX_BEGIN__"
        end = f"__ENV{index}_HEX_END__"
        output = command(
            proc,
            f"echo {begin}; hexdump -v -e '1/1 \"%02x\"' /dev/mtdblock{index}; "
            f"echo; echo {end}",
            f"__ENV{index}_DUMP_DONE__",
            120,
        )
        payload = output.split(begin, 1)[1].split(end, 1)[0]
        hex_text = re.sub(r"[^0-9a-fA-F]", "", payload)
        data = bytes.fromhex(hex_text)
        if len(data) != 0x10000:
            raise RuntimeError(f"mtd{index}: expected 65536 bytes, got {len(data)}")
        path = args.output / f"mtd{index}.bin"
        path.write_bytes(data)
        stored_le = struct.unpack("<I", data[:4])[0]
        calculated = zlib.crc32(data[4:ENV_LOGICAL_SIZE]) & 0xFFFFFFFF
        print(
            f"mtd{index} path={path} stored_crc=0x{stored_le:08x} "
            f"calculated_crc=0x{calculated:08x} valid={stored_le == calculated}"
        )

    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
