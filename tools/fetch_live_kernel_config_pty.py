#!/usr/bin/env python3
"""Fetch /proc/config.gz from the repeater without modifying the device."""
from __future__ import annotations

import gzip
import hashlib
import os
import re
from pathlib import Path

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


OUT = ROOT / "outputs" / "kernel-port"


def main() -> int:
    user, password = credentials()
    ssh = os.path.join(os.environ["WINDIR"], "System32", "OpenSSH", "ssh.exe")
    proc = PtyProcess.spawn([
        ssh, "-tt", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@192.168.1.90",
    ], cwd=str(ROOT))
    read_until(proc, "password:", 20)
    proc.write(password + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)

    raw = command(
        proc,
        "echo __CFG_HEX_BEGIN__; hexdump -v -e '1/1 \"%02x\"' /proc/config.gz; "
        "echo; echo __CFG_HEX_END__",
        "__CFG_DONE__",
        90,
    )
    proc.write("exit\r\n")

    match = re.search(r"__CFG_HEX_BEGIN__\s*([0-9a-fA-F\s]+?)\s*__CFG_HEX_END__", raw)
    if not match:
        raise RuntimeError("Could not delimit the remote kernel config")
    payload = bytes.fromhex("".join(match.group(1).split()))
    config = gzip.decompress(payload)

    OUT.mkdir(parents=True, exist_ok=True)
    gz_path = OUT / "live-proc-config.gz"
    config_path = OUT / "live-kernel-2.6.35.12.config"
    gz_path.write_bytes(payload)
    config_path.write_bytes(config)
    print(f"wrote {gz_path} ({len(payload)} bytes, sha256={hashlib.sha256(payload).hexdigest()})")
    print(f"wrote {config_path} ({len(config)} bytes, sha256={hashlib.sha256(config).hexdigest()})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
