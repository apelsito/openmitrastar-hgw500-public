#!/usr/bin/env python3
"""Reboot to a pre-verified LIVE slot only when both Bootbase env copies agree."""
from __future__ import annotations

import argparse
import os
import re

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", default="192.168.1.90")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

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

    state = command(
        proc,
        "echo BOOTCMD=$(/sbin/call_qcsapi get_bootcfg_param bootcmd); "
        "echo BOOTSELECT=$(/sbin/call_qcsapi get_bootcfg_param bootselect); "
        "md5sum /dev/mtdblock1 /dev/mtdblock2 /dev/mtdblock4",
        "__REBOOT_LIVE_PREFLIGHT__",
        90,
    )
    values = re.findall(r"\b[0-9a-fA-F]{32}\b", state)
    if "BOOTCMD=bootselect" not in state or "BOOTSELECT=0" not in state:
        raise RuntimeError(f"LIVE selector preflight failed\n{state}")
    if len(values) != 3 or values[0].lower() != values[1].lower():
        raise RuntimeError(f"Bootbase environment copies differ\n{state}")
    if values[2].lower() != "9a40fccfce956fa06d5fd0f3917319e1":
        raise RuntimeError(f"LIVE slot hash changed\n{state}")
    print(
        f"PREFLIGHT_OK=1 env_md5={values[0].lower()} "
        f"live_md5={values[2].lower()}"
    )
    if not args.commit:
        print("DRY_RUN=1 REBOOT=0")
        proc.write("exit\r\n")
        return 0
    proc.write("sync; reboot -d 6 >/dev/null 2>&1 &\r\n")
    print("REBOOT_REQUESTED=1 target=live delay_seconds=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
