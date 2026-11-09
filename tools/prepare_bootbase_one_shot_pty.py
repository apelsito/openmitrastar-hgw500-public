#!/usr/bin/env python3
"""Prepare a recoverable one-shot Bootbase slot trial through /proc/bootcfg."""
from __future__ import annotations

import argparse
import os
import re

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def scalar(output: str, allowed: set[str]) -> str:
    for line in output.replace("\r", "").splitlines():
        value = line.strip().lstrip("# ").strip()
        if value in allowed:
            return value
    raise RuntimeError(f"expected one of {sorted(allowed)}, got {output!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--trial-slot", choices=["live", "safety"])
    mode.add_argument(
        "--self-test-live",
        action="store_true",
        help=(
            "prove run/saveenv with the known-good live slot while also "
            "persisting live as the fallback"
        ),
    )
    mode.add_argument(
        "--restore-live-default",
        action="store_true",
        help="commit bootcmd=bootselect and bootselect=0",
    )
    parser.add_argument("--router", default="192.168.1.90")
    parser.add_argument("--commit", action="store_true")
    parser.add_argument("--reboot", action="store_true")
    args = parser.parse_args()
    if args.reboot and not args.commit:
        parser.error("--reboot requires --commit")

    if args.self_test_live:
        trial_slot = "live"
        trial_value = "0"
        fallback_value = "0"
        fallback_slot = "live"
    else:
        trial_slot = args.trial_slot
        trial_value = "0" if trial_slot == "live" else "1"
        fallback_value = "1" if trial_slot == "live" else "0"
        fallback_slot = "safety" if trial_slot == "live" else "live"
    trial_once = (
        "setenv bootcmd bootselect; "
        f"setenv bootselect {fallback_value}; saveenv; "
        f"setenv bootselect {trial_value}; bootselect"
    )

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

    bootcmd = scalar(command(
        proc, "/sbin/call_qcsapi get_bootcfg_param bootcmd",
        "__ONESHOT_BOOTCMD__", 20,
    ), {"bootselect", "qtnboot", "run trial_once"})
    selected = scalar(command(
        proc, "/sbin/call_qcsapi get_bootcfg_param bootselect",
        "__ONESHOT_BOOTSELECT__", 20,
    ), {"0", "1"})
    env_hash = command(
        proc, "md5sum /dev/mtdblock1 /dev/mtdblock2",
        "__ONESHOT_ENV_HASH__", 30,
    )
    hashes = re.findall(r"\b[0-9a-fA-F]{32}\b", env_hash)
    if len(hashes) != 2:
        raise RuntimeError("could not hash both environment copies")

    print(
        f"current_bootcmd={bootcmd} current_bootselect={selected} "
        f"trial={trial_slot} fallback={fallback_slot}"
    )
    print(f"trial_once={trial_once}")
    print(f"env_before={hashes[0].lower()},{hashes[1].lower()}")
    if args.restore_live_default:
        if not args.commit:
            print("RESTORE_DRY_RUN=1 ENV_WRITES=0 REBOOT=0")
            proc.write("exit\r\n")
            return 0
        restored = command(
            proc,
            "/scripts/set_bootval -nc bootcmd bootselect; "
            "/scripts/set_bootval -nc bootselect 0; "
            "cat /proc/bootcfg/pending; sync; "
            "grep -E '^(bootcmd|bootselect)=' /proc/bootcfg/env",
            "__ONESHOT_RESTORED__",
            60,
        )
        if "bootcmd=bootselect" not in restored or "bootselect=0" not in restored:
            raise RuntimeError(f"restored environment readback mismatch\n{restored}")
        print("LIVE_DEFAULT_RESTORED=1 bootcmd=bootselect bootselect=0")
        if args.reboot:
            proc.write("reboot -d 6 >/dev/null 2>&1 &\r\n")
            print("REBOOT_REQUESTED=1 delay_seconds=6")
        else:
            print("REBOOT=0")
            proc.write("exit\r\n")
        return 0
    if not args.commit:
        print("DRY_RUN=1 ENV_WRITES=0 REBOOT=0")
        proc.write("exit\r\n")
        return 0

    staged = command(
        proc,
        f"/scripts/set_bootval -nc trial_once '{trial_once}'; "
        "/scripts/set_bootval -nc bootcmd 'run trial_once'; "
        "grep -E '^(trial_once|bootcmd|bootselect)=' /proc/bootcfg/env",
        "__ONESHOT_STAGED__",
        30,
    )
    required = [f"trial_once={trial_once}", "bootcmd=run trial_once"]
    if any(item not in staged for item in required):
        raise RuntimeError(f"staged environment readback mismatch\n{staged}")

    committed = command(
        proc,
        "cat /proc/bootcfg/pending; sync; "
        "grep -E '^(trial_once|bootcmd|bootselect)=' /proc/bootcfg/env; "
        "md5sum /dev/mtdblock1 /dev/mtdblock2",
        "__ONESHOT_COMMITTED__",
        60,
    )
    if any(item not in committed for item in required):
        raise RuntimeError(f"committed environment readback mismatch\n{committed}")
    if len(re.findall(r"\b[0-9a-fA-F]{32}\b", committed)) != 2:
        raise RuntimeError("committed environment hashes missing")
    print("ENV_COMMITTED=1")

    if not args.reboot:
        print("REBOOT=0")
        proc.write("exit\r\n")
        return 0
    proc.write("reboot -d 6 >/dev/null 2>&1 &\r\n")
    print("REBOOT_REQUESTED=1 delay_seconds=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
