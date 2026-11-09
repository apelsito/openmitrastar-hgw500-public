#!/usr/bin/env python3
"""Read-only Bootbase environment and bootcfg inspection over legacy SSH."""
from __future__ import annotations

import argparse
import os

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", default="192.168.1.90")
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

    out = command(
        proc,
        "echo MTD_BEGIN; cat /proc/mtd; echo MTD_END; "
        "echo BOOTCFG_FILES_BEGIN; ls -la /proc/bootcfg; echo BOOTCFG_FILES_END; "
        "echo ENV_BEGIN; cat /proc/bootcfg/env; echo ENV_END; "
        "echo HASH_BEGIN; md5sum /dev/mtdblock1 /dev/mtdblock2; echo HASH_END; "
        "echo MTD1_HEAD_BEGIN; dd if=/dev/mtdblock1 bs=1024 count=1 2>/dev/null | hexdump -C; "
        "echo MTD1_HEAD_END; echo MTD2_HEAD_BEGIN; "
        "dd if=/dev/mtdblock2 bs=1024 count=1 2>/dev/null | hexdump -C; "
        "echo MTD2_HEAD_END; "
        "echo KEXEC_BEGIN; ls -l /sbin/kexec /usr/sbin/kexec /bin/kexec 2>/dev/null; "
        "if [ -r /proc/config.gz ]; then zcat /proc/config.gz | grep -E 'CONFIG_KEXEC|CONFIG_CRASH'; fi; "
        "grep -E '(^| )(_?sys_kexec_load|sys_ni_syscall|kernel_kexec|machine_kexec)( |$)' /proc/kallsyms 2>/dev/null; "
        "echo KEXEC_END",
        "__BOOTCFG_INSPECT__",
        60,
    )
    print(out)
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
