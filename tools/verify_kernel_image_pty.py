#!/usr/bin/env python3
"""Upload an image over TFTP and validate it on the router without flashing."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--tftp-host", default="192.168.1.43")
    parser.add_argument("--router", default="192.168.1.90")
    args = parser.parse_args()
    image = args.image.resolve()
    expected_size = image.stat().st_size
    expected_md5 = hashlib.md5(image.read_bytes()).hexdigest()
    remote = "/tmp/openmitrastar-kernel-candidate.uImage"
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
    transfer = command(
        proc,
        f"rm -f {remote}; tftp -g -r {image.name} -l {remote} {args.tftp_host}; "
        f"rc=$?; echo TFTP_RC=$rc; wc -c < {remote}; md5sum {remote}",
        "__KERNEL_TFTP_VERIFY__",
        120,
    )
    if ("TFTP_RC=0" not in transfer or str(expected_size) not in transfer or
            expected_md5 not in transfer.lower()):
        raise RuntimeError(f"TFTP verification failed\n{transfer}")
    checked = command(
        proc,
        f"chkimage -A arc -O linux -T kernel -v {remote}; echo CHECK_RC=$?",
        "__KERNEL_CHKIMAGE__",
        40,
    )
    if "CHECK_RC=0" not in checked:
        raise RuntimeError(f"chkimage rejected candidate\n{checked}")
    print(f"verified size={expected_size} md5={expected_md5}")
    print(checked.strip())
    print("FLASH_WRITES=0 REBOOT=0")
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
