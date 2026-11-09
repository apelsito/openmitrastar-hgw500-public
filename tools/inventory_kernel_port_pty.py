#!/usr/bin/env python3
"""Read-only platform inventory for a future Linux kernel port."""
from __future__ import annotations

import os

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


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
    probe = r'''
echo '=== UNAME ==='; uname -a
echo '=== CPUINFO ==='; cat /proc/cpuinfo
echo '=== CMDLINE ==='; cat /proc/cmdline
echo '=== MTD ==='; cat /proc/mtd
echo '=== MOUNTS ==='; cat /proc/mounts
echo '=== DEVICE_TREE ==='; if [ -d /proc/device-tree ]; then find /proc/device-tree -maxdepth 2 -type f 2>/dev/null; else echo absent; fi
echo '=== CONFIG ==='; if [ -r /proc/config.gz ]; then busybox zcat /proc/config.gz | md5sum; busybox zcat /proc/config.gz | grep -E '^(CONFIG_(ARC|PLAT|TOPAZ|RUBY|SPI|MTD|NET|QTN|PCI|SERIAL|HZ|PREEMPT|SQUASHFS|IKCONFIG))'; else echo absent; fi
echo '=== INTERRUPTS ==='; cat /proc/interrupts
echo '=== IOMEM ==='; cat /proc/iomem 2>/dev/null
echo '=== BOOT_DMESG ==='; dmesg | grep -Ei 'arc|topaz|ruby|qtn|spi|nand|nor|ether|emac|uart|clock|timer' | head -120
'''.strip()
    print(command(proc, probe, "__KERNEL_PORT_INVENTORY__", 90).strip())
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
