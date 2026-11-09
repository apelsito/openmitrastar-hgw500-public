#!/usr/bin/env python3
"""Load the volatile loader with execution disabled and run hardware preflight."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


ARTIFACTS = ROOT / "work/tftp/omvl"
MODULE = ARTIFACTS / "openmitrastar_volatile_loader.ko"
IMAGE = ARTIFACTS / "linux-5.10.260-topaz-ramssh-RAM-ONLY-NO-GO.uImage"


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", default="192.168.1.97")
    parser.add_argument("--tftp-host", default="192.168.1.43")
    parser.add_argument("--probe-address", type=lambda value: int(value, 0),
                        default=0)
    parser.add_argument("--probe-only", action="store_true")
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

    transfer = command(proc,
        "rm -f /tmp/openmitrastar_volatile_loader.ko; "
        f"tftp -g -r {MODULE.name} -l /tmp/{MODULE.name} {args.tftp_host}; "
        "echo MODULE_TFTP_RC=$?; "
        "wc -c /tmp/openmitrastar_volatile_loader.ko; "
        "md5sum /tmp/openmitrastar_volatile_loader.ko",
        "__OMVL_TOOLS_TRANSFER__", 120)
    print(transfer)
    required = ["MODULE_TFTP_RC=0", str(MODULE.stat().st_size), md5(MODULE)]
    if any(value.lower() not in transfer.lower() for value in required):
        raise RuntimeError("tool transfer verification failed")

    loaded = command(proc,
        "rmmod openmitrastar_volatile_loader 2>/dev/null || true; "
        f"insmod /tmp/openmitrastar_volatile_loader.ko "
        f"probe_address=0x{args.probe_address:08x}; echo INSMOD_RC=$?; "
        "minor=$(awk '$2==\"openmitrastar-volatile-loader\" {print $1}' /proc/misc); "
        "echo MISC_MINOR=$minor; test -n \"$minor\" && "
        "rm -f /dev/openmitrastar-volatile-loader && "
        "mknod /dev/openmitrastar-volatile-loader c 10 $minor; "
        "ls -l /dev/openmitrastar-volatile-loader; "
        "grep '^openmitrastar_volatile_loader ' /proc/modules; "
        "echo 'OMVL:RESET' > /dev/openmitrastar-volatile-loader; echo RESET_RC=$?; "
        "dmesg | tail -12",
        "__OMVL_MODULE_LOADED__", 60)
    print(loaded)
    if "INSMOD_RC=0" not in loaded or "OMVL_RESET_PASS" not in loaded or "RESET_RC=0" not in loaded:
        raise RuntimeError("module load/reset failed")
    if args.probe_only:
        print("OMVL_READ_ONLY_PROBE_PASS FLASH_WRITES=0")
        proc.write("exit\r\n")
        return 0

    staged = command(proc,
        f"tftp -g -r {IMAGE.name} -l /dev/openmitrastar-volatile-loader {args.tftp_host}; "
        "echo IMAGE_TFTP_RC=$?; "
        "echo 'OMVL:PREFLIGHT' > /dev/openmitrastar-volatile-loader; echo PREFLIGHT_RC=$?; "
        "cat /proc/meminfo | head -18; dmesg | tail -16",
        "__OMVL_HW_PREFLIGHT__", 300)
    print(staged)
    required = ["IMAGE_TFTP_RC=0", "OMVL_PREFLIGHT_PASS", "PREFLIGHT_RC=0",
                "image=4053888", "payload=4053824", "load=8493a000",
                "entry=84ab0000", "overlap=1", "execute=0"]
    if any(value not in staged for value in required):
        raise RuntimeError("hardware preflight failed")
    print("OMVL_HARDWARE_PREFLIGHT_PASS EXECUTION_DISABLED=1 FLASH_WRITES=0")
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
