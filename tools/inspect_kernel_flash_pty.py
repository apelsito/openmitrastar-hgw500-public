#!/usr/bin/env python3
"""Read-only inspection of the OEM inactive-slot flash state."""
from __future__ import annotations

import argparse
import os

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", default="192.168.1.90")
    parser.add_argument("--bytes", type=int, default=1_924_128)
    parser.add_argument("--probe-invalid-backend", action="store_true")
    parser.add_argument("--probe-detached-wrapper", action="store_true")
    parser.add_argument("--tftp-host", default="192.168.1.43")
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

    status = command(
        proc,
        "echo RESULT_BEGIN; cat /tmp/result_upgrade 2>/dev/null; echo RESULT_END; "
        "echo BOOTCMD=$(/sbin/call_qcsapi get_bootcfg_param bootcmd); "
        "echo BOOTSELECT=$(/sbin/call_qcsapi get_bootcfg_param bootselect); "
        "echo SLOT3_HEADER_BEGIN; dd if=/dev/mtdblock3 bs=128 count=1 2>/dev/null | hexdump -C; "
        "echo SLOT3_HEADER_END; echo SLOT3_CHKIMAGE_BEGIN; "
        "chkimage -A arc -O linux -T kernel -v /dev/mtdblock3 2>&1; "
        "echo SLOT3_CHKIMAGE_RC=$?; echo SLOT3_CHKIMAGE_END; "
        "echo SLOT3_MD5_BEGIN; md5sum /dev/mtdblock3; echo SLOT3_MD5_END; "
        "echo UPDATE_PROCESSES_BEGIN; ps | grep -E '[f]lash_image_update|[F]Wupgrade'; "
        "echo UPDATE_PROCESSES_END",
        "__FLASH_INSPECT_STATUS__",
        30,
    )
    print(status)
    details = command(
        proc,
        "echo FWUPGRADE_SCRIPT_BEGIN; sed -n '1,140p' /etc/default/FWupgrade.sh; "
        "echo FWUPGRADE_SCRIPT_END; echo LOG_BEGIN; "
        "cat /tmp/openmitrastar-fwupgrade.log /tmp/openmitrastar-flash-run.log 2>/dev/null; "
        "echo LOG_END; ls -l /tmp/topaz-linux.lzma.img /tmp/result_upgrade 2>/dev/null; "
        "ls -l /bin/nohup /usr/bin/nohup /sbin/setsid /usr/bin/setsid 2>/dev/null; "
        "ls -l /sbin/start-stop-daemon /bin/start-stop-daemon 2>/dev/null; "
        "start-stop-daemon --help 2>&1 | sed -n '1,80p'",
        "__FLASH_INSPECT_DETAILS__",
        30,
    )
    print(details)
    if args.probe_invalid_backend:
        probe = command(
            proc,
            "date; call_qcsapi flash_image_update /tmp/definitely-not-present safety; "
            "echo INVALID_PROBE_RC=$?; date",
            "__FLASH_INVALID_BACKEND_PROBE__",
            90,
        )
        print(probe)
    if args.probe_detached_wrapper:
        detached = command(
            proc,
            "tftp -g -r remote_oem_flash_job.sh "
            f"-l /tmp/remote_oem_flash_job.sh {args.tftp_host}; "
            "chmod 700 /tmp/remote_oem_flash_job.sh; "
            "rm -f /tmp/oem-flash-test.status /tmp/oem-flash-test.pid "
            "/tmp/result_upgrade /tmp/openmitrastar-fwupgrade.log; "
            "start-stop-daemon -S -b -m -p /tmp/oem-flash-test.pid -x /bin/sh -- "
            "/tmp/remote_oem_flash_job.sh /tmp/definitely-not-present safety "
            "/tmp/oem-flash-test.status; echo DETACH_START_RC=$?; sleep 2; "
            "cat /tmp/oem-flash-test.status /tmp/result_upgrade "
            "/tmp/openmitrastar-fwupgrade.log 2>/dev/null; "
            "echo PID=$(cat /tmp/oem-flash-test.pid 2>/dev/null)",
            "__FLASH_DETACHED_WRAPPER_PROBE__",
            30,
        )
        print(detached)
    full_blocks, remainder = divmod(args.bytes, 4096)
    if remainder:
        read_command = (
            "{ "
            f"dd if=/dev/mtdblock3 bs=4096 count={full_blocks}; "
            f"dd if=/dev/mtdblock3 bs=4096 skip={full_blocks} count=1 | "
            f"dd bs=1 count={remainder}; "
            "} 2>/dev/null | md5sum"
        )
    else:
        read_command = (
            f"dd if=/dev/mtdblock3 bs=4096 count={full_blocks} 2>/dev/null | md5sum"
        )
    readback = command(
        proc,
        read_command,
        "__FLASH_INSPECT_READBACK__",
        120,
    )
    print(readback)
    extracted = command(
        proc,
        "{ "
        f"dd if=/dev/mtdblock3 bs=4096 count={full_blocks}; "
        f"dd if=/dev/mtdblock3 bs=4096 skip={full_blocks} count=1 | "
        f"dd bs=1 count={remainder}; "
        "} 2>/dev/null > /tmp/safety-readback.img; "
        "wc -c /tmp/safety-readback.img; md5sum /tmp/safety-readback.img; "
        "chkimage -A arc -O linux -T kernel -v /tmp/safety-readback.img; "
        "echo EXTRACTED_CHKIMAGE_RC=$?",
        "__FLASH_INSPECT_EXTRACTED__",
        120,
    )
    print(extracted)
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
