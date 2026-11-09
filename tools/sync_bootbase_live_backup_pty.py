#!/usr/bin/env python3
"""Mirror a verified LIVE-default primary Bootbase environment to its backup."""
from __future__ import annotations

import argparse
import hashlib
import os
import re

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


OEM_SCRIPT = ROOT / "work" / "revival" / "rootfs" / "scripts" / "do_backup_env.sh"


def exact_scalar(output: str, allowed: set[str]) -> str:
    for line in output.replace("\r", "").splitlines():
        value = line.strip().lstrip("# ").strip()
        if value in allowed:
            return value
    raise RuntimeError(f"expected one of {sorted(allowed)}, got {output!r}")


def hashes(output: str) -> list[str]:
    values = re.findall(r"\b[0-9a-fA-F]{32}\b", output)
    if len(values) != 2:
        raise RuntimeError(f"expected two MTD hashes, got {output!r}")
    return [value.lower() for value in values]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", default="192.168.1.90")
    parser.add_argument("--commit", action="store_true")
    args = parser.parse_args()

    expected_script_md5 = hashlib.md5(OEM_SCRIPT.read_bytes()).hexdigest()
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

    layout = command(
        proc,
        "grep -E '^mtd[12]:' /proc/mtd; md5sum /scripts/do_backup_env.sh",
        "__ENV_BACKUP_LAYOUT__", 20,
    )
    required_layout = [
        'mtd1: 00010000 00010000 "uboot_env"',
        'mtd2: 00010000 00010000 "uboot_env_bak"',
        expected_script_md5,
    ]
    if any(item.lower() not in layout.lower() for item in required_layout):
        raise RuntimeError(f"unexpected MTD layout or OEM script\n{layout}")

    bootcmd = exact_scalar(command(
        proc, "/sbin/call_qcsapi get_bootcfg_param bootcmd",
        "__ENV_BACKUP_BOOTCMD__", 20,
    ), {"bootselect", "run trial_once", "qtnboot"})
    bootselect = exact_scalar(command(
        proc, "/sbin/call_qcsapi get_bootcfg_param bootselect",
        "__ENV_BACKUP_BOOTSELECT__", 20,
    ), {"0", "1"})
    before = hashes(command(
        proc, "md5sum /dev/mtdblock1 /dev/mtdblock2",
        "__ENV_BACKUP_HASHES__", 30,
    ))
    print(
        f"primary_bootcmd={bootcmd} primary_bootselect={bootselect} "
        f"primary_md5={before[0]} backup_md5={before[1]}"
    )
    if bootcmd != "bootselect" or bootselect != "0":
        raise RuntimeError("refusing: primary environment is not the LIVE default")

    if not args.commit:
        if before[0] == before[1]:
            print(
                f"BACKUP_ALREADY_SYNCED=1 md5={before[0]} "
                "bootcmd=bootselect bootselect=0 ENV_BACKUP_WRITES=0 REBOOT=0"
            )
        else:
            print("DRY_RUN=1 ENV_BACKUP_WRITES=0 REBOOT=0")
        proc.write("exit\r\n")
        return 0

    copied = command(
        proc, "/scripts/do_backup_env.sh",
        "__ENV_BACKUP_COPIED__", 120,
    )
    if not re.search(r"(?m)^Done\s*$", copied.replace("\r", "")):
        raise RuntimeError(f"OEM backup script did not report success\n{copied}")

    verified = command(
        proc,
        "md5sum /dev/mtdblock1 /dev/mtdblock2",
        "__ENV_BACKUP_VERIFIED__", 60,
    )
    after = hashes(verified)
    if after[0] != after[1] or after[0] != before[0]:
        raise RuntimeError(f"backup hash mismatch after OEM copy\n{verified}")
    print(f"BACKUP_SYNCED=1 md5={after[0]} bootcmd=bootselect bootselect=0 REBOOT=0")
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
