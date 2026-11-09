#!/usr/bin/env python3
"""Read a firmware MTD slot to /tmp, download it with legacy SCP, and verify MD5."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import time

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def ssh_argv(executable: str, user: str, router: str) -> list[str]:
    return [
        executable, "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@{router}",
    ]


def read_to_eof(proc: PtyProcess, timeout: int) -> str:
    deadline = time.monotonic() + timeout
    chunks: list[str] = []
    while time.monotonic() < deadline:
        try:
            chunk = proc.read(4096)
        except EOFError:
            break
        if chunk:
            chunks.append(chunk)
    return "".join(chunks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--slot", choices=["mtd3", "mtd4"], default="mtd4")
    parser.add_argument("--router", default="192.168.1.90")
    parser.add_argument(
        "--output", type=Path,
        default=ROOT / "outputs" / "kernel-port" / "router-current-mtd4.bin",
    )
    args = parser.parse_args()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    expected_size = 0x7A0000
    remote = f"/tmp/{args.slot}-slot-export.bin"

    user, password = credentials()
    system32 = Path(os.environ["WINDIR"]) / "System32" / "OpenSSH"
    ssh = str(system32 / "ssh.exe")
    proc = PtyProcess.spawn(ssh_argv(ssh, user, args.router), cwd=str(ROOT))
    read_until(proc, "password:", 20)
    proc.write(password + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)

    exported = command(
        proc,
        f"rm -f {remote}; dd if=/dev/mtdblock{args.slot[-1]} of={remote} "
        "bs=64k count=122 2>/dev/null; rc=$?; sync; echo DD_RC=$rc; "
        f"wc -c {remote}; md5sum {remote}",
        "__MTD_EXPORT_READY__",
        120,
    )
    match = re.search(r"\b([0-9a-fA-F]{32})\b", exported)
    if "DD_RC=0" not in exported or str(expected_size) not in exported or not match:
        raise RuntimeError(f"MTD export failed\n{exported}")
    remote_md5 = match.group(1).lower()

    begin = "__MTD_HEX_BEGIN__"
    end = "__MTD_HEX_END__"
    encoded = command(
        proc,
        f"echo {begin}; hexdump -v -e '1/1 \"%02x\"' {remote}; "
        f"echo; echo {end}",
        "__MTD_HEX_DONE__",
        600,
    )
    payload = encoded.split(begin, 1)[1].split(end, 1)[0]
    hex_lines = []
    for raw in payload.replace("\r", "").splitlines():
        line = raw.strip()
        if line and len(line) % 2 == 0 and re.fullmatch(r"[0-9a-fA-F]+", line):
            hex_lines.append(line)
    data = bytes.fromhex("".join(hex_lines))
    args.output.write_bytes(data)
    local_md5 = hashlib.md5(data).hexdigest()
    cleanup = command(proc, f"rm -f {remote}; echo CLEANED=1", "__MTD_EXPORT_CLEANUP__", 20)
    proc.write("exit\r\n")
    if len(data) != expected_size or local_md5 != remote_md5:
        raise RuntimeError(
            f"download mismatch size={len(data)} md5={local_md5} remote_md5={remote_md5}"
        )
    if "CLEANED=1" not in cleanup:
        raise RuntimeError("remote temporary file cleanup not confirmed")
    print(f"DOWNLOADED=1 slot={args.slot} bytes={len(data)} md5={local_md5} path={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
