#!/usr/bin/env python3
"""Clone the OEM firmware.cgi inactive-slot upgrade flow over SSH/TFTP."""
from __future__ import annotations

import argparse
import hashlib
import os
from pathlib import Path
import re
import time

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


REMOTE = "/tmp/topaz-linux.lzma.img"


def scalar(output: str, allowed: set[str]) -> str:
    for line in output.replace("\r", "").splitlines():
        value = line.strip().lstrip("# ").strip()
        if value in allowed:
            return value
    raise RuntimeError(f"expected one of {sorted(allowed)}, got: {output!r}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("image", type=Path)
    parser.add_argument("--tftp-host", default="192.168.1.43")
    parser.add_argument("--router", default="192.168.1.90")
    parser.add_argument("--flash", action="store_true")
    parser.add_argument("--no-reboot", action="store_true")
    parser.add_argument(
        "--keep-current-slot",
        action="store_true",
        help="after a verified inactive-slot write, restore the original bootselect",
    )
    parser.add_argument(
        "--accept-no-uart-recovery",
        action="store_true",
        help="acknowledge that a post-handoff kernel hang cannot switch slots",
    )
    args = parser.parse_args()
    if args.flash and not args.accept_no_uart_recovery:
        parser.error("--flash requires --accept-no-uart-recovery")
    if args.keep_current_slot and not (args.flash and args.no_reboot):
        parser.error("--keep-current-slot requires --flash --no-reboot")

    image = args.image.resolve()
    expected_size = image.stat().st_size
    image_bytes = image.read_bytes()
    expected_md5 = hashlib.md5(image_bytes).hexdigest()
    # qcsapi canonicalizes the RAS metadata architecture byte while writing.
    # This byte is outside the uImage header and kernel payload CRC regions.
    flashed_bytes = bytearray(image_bytes)
    if len(flashed_bytes) > 0x6B:
        flashed_bytes[0x6B] = 0x13
    expected_flash_md5 = hashlib.md5(flashed_bytes).hexdigest()
    if expected_size <= 0 or expected_size > 0x7A0000:
        raise ValueError(f"candidate size outside slot: {expected_size}")

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
        f"rm -f {REMOTE}; tftp -g -r {image.name} -l {REMOTE} {args.tftp_host}; "
        f"rc=$?; echo TFTP_RC=$rc; wc -c < {REMOTE}; md5sum {REMOTE}",
        "__OEMCGI_TRANSFER__",
        120,
    )
    if ("TFTP_RC=0" not in transfer or str(expected_size) not in transfer or
            expected_md5 not in transfer.lower()):
        raise RuntimeError(f"transfer integrity failure\n{transfer}")

    checked = command(
        proc,
        f"chkimage -A arc -O linux -T kernel -v {REMOTE}; echo CHECK_RC=$?",
        "__OEMCGI_CHKIMAGE__",
        40,
    )
    if "CHECK_RC=0" not in checked:
        raise RuntimeError(f"chkimage rejected candidate\n{checked}")

    bootcmd = command(
        proc, "/sbin/call_qcsapi get_bootcfg_param bootcmd",
        "__OEMCGI_BOOTCMD__", 20,
    )
    if scalar(bootcmd, {"bootselect", "qtnboot"}) != "bootselect":
        raise RuntimeError("OEM clone refuses non-bootselect bootcmd")
    selected = scalar(command(
        proc, "/sbin/call_qcsapi get_bootcfg_param bootselect",
        "__OEMCGI_BOOTSELECT__", 20,
    ), {"0", "1"})
    active = "live" if selected == "0" else "safety"
    target = "safety" if active == "live" else "live"
    target_mtd = "/dev/mtdblock3" if target == "safety" else "/dev/mtdblock4"
    before = command(proc, f"md5sum {target_mtd}", "__OEMCGI_BEFORE__", 60)
    before_md5 = re.search(r"\b[0-9a-fA-F]{32}\b", before)
    if not before_md5:
        raise RuntimeError("could not hash inactive slot")

    print(
        f"candidate accepted size={expected_size} md5={expected_md5} "
        f"active={active} target={target} target_before={before_md5.group(0).lower()}"
    )
    if not args.flash:
        print("VERIFY_ONLY=1 FLASH_WRITES=0 REBOOT=0")
        proc.write("exit\r\n")
        return 0

    command(proc, "/etc/default/led.sh fwupgrade >/dev/null 2>&1 & echo LED_STARTED=1",
            "__OEMCGI_LED__", 10)
    launched = command(
        proc,
        f"tftp -g -r remote_oem_flash_job.sh -l /tmp/remote_oem_flash_job.sh {args.tftp_host}; "
        "chmod 700 /tmp/remote_oem_flash_job.sh; "
        "rm -f /tmp/oem-flash.status /tmp/oem-flash.pid /tmp/result_upgrade "
        "/tmp/openmitrastar-fwupgrade.log; "
        "start-stop-daemon -S -b -m -p /tmp/oem-flash.pid -x /bin/sh -- "
        f"/tmp/remote_oem_flash_job.sh {REMOTE} {target} /tmp/oem-flash.status; "
        "echo DETACH_START_RC=$?; sleep 1; cat /tmp/oem-flash.status 2>/dev/null; "
        "echo PID=$(cat /tmp/oem-flash.pid 2>/dev/null)",
        "__OEMCGI_FLASH_LAUNCH__",
        30,
    )
    if "DETACH_START_RC=0" not in launched or "state=running" not in launched:
        raise RuntimeError(f"could not launch detached OEM writer\n{launched}")
    print("FLASH_JOB_STARTED=1", flush=True)
    deadline = time.monotonic() + 20 * 60
    next_report = 0.0
    while True:
        polled = command(
            proc,
            "cat /tmp/oem-flash.status 2>/dev/null; "
            "pid=$(cat /tmp/oem-flash.pid 2>/dev/null); "
            "if [ -n \"$pid\" ] && kill -0 \"$pid\" 2>/dev/null; then "
            "echo JOB_ALIVE=1; else echo JOB_ALIVE=0; fi",
            "__OEMCGI_FLASH_POLL__",
            20,
        )
        finished = re.search(r"state=finished rc=(\d+)", polled)
        if finished:
            if finished.group(1) != "0":
                details = command(
                    proc,
                    "cat /tmp/result_upgrade /tmp/openmitrastar-fwupgrade.log 2>/dev/null",
                    "__OEMCGI_FLASH_FAILED__",
                    20,
                )
                raise RuntimeError(f"OEM writer failed rc={finished.group(1)}\n{details}")
            break
        if "JOB_ALIVE=1" not in polled:
            raise RuntimeError(f"OEM writer disappeared without final status\n{polled}")
        now = time.monotonic()
        if now >= next_report:
            elapsed = int(20 * 60 - (deadline - now))
            print(f"FLASH_JOB_RUNNING=1 elapsed_seconds={elapsed}", flush=True)
            next_report = now + 30
        if now >= deadline:
            raise TimeoutError("OEM writer still running after 20 minutes; job left detached")
        time.sleep(5)

    flashed = command(
        proc,
        "echo FLASH_RC=0; cat /tmp/result_upgrade 2>/dev/null; "
        "cat /tmp/openmitrastar-fwupgrade.log 2>/dev/null",
        "__OEMCGI_FLASH_DONE__",
        30,
    )
    if "complete" not in flashed.lower():
        raise RuntimeError(f"OEM writer exited zero without complete\n{flashed}")
    new_selected = scalar(command(
        proc, "/sbin/call_qcsapi get_bootcfg_param bootselect",
        "__OEMCGI_NEW_BOOTSELECT__", 20,
    ), {"0", "1"})
    if new_selected != selected:
        raise RuntimeError(
            f"OEM writer unexpectedly changed bootselect {selected} -> {new_selected}"
        )
    full_blocks, remainder = divmod(expected_size, 4096)
    if remainder:
        read_command = (
            "{ "
            f"dd if={target_mtd} bs=4096 count={full_blocks}; "
            f"dd if={target_mtd} bs=4096 skip={full_blocks} count=1 | "
            f"dd bs=1 count={remainder}; "
            "} 2>/dev/null | md5sum"
        )
    else:
        read_command = (
            f"dd if={target_mtd} bs=4096 count={full_blocks} 2>/dev/null | md5sum"
        )
    readback = command(
        proc,
        read_command,
        "__OEMCGI_READBACK__",
        180,
    )
    if expected_flash_md5 not in readback.lower():
        raise RuntimeError(f"flashed slot readback mismatch\n{readback}")
    print(
        f"FLASH_READBACK_OK=1 md5={expected_flash_md5} "
        "ras_offset_0x6b=0x13"
    )
    print(f"FLASH_COMPLETE=1 target={target} bootselect={new_selected}")
    if args.keep_current_slot:
        # Current qcsapi keeps the active selector unchanged. Retain this
        # explicit invariant because it is the safety property of no-reboot.
        print(f"BOOTSELECT_RESTORED=1 bootselect={selected}")
    if args.no_reboot:
        print("REBOOT=0")
        proc.write("exit\r\n")
        return 0

    # Same delayed reboot primitive used by firmware.cgi, with an explicit
    # sync before the session disappears.
    proc.write(f"rm -f {REMOTE}; sync; reboot -d 6 >/dev/null 2>&1 &\r\n")
    print("REBOOT_REQUESTED=1 delay_seconds=6")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
