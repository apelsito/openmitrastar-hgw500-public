#!/usr/bin/env python3
"""Read-only live/safety and recovery preflight over legacy Dropbear."""
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
echo '=== IDENTITY ==='
uname -a
cat /etc/openmitrastar-release 2>/dev/null || true
echo '=== BOOT ==='
cat /proc/cmdline
cat /proc/mounts | grep -E ' / |rootfs|squashfs'
echo '=== MTD ==='
cat /proc/mtd
echo '=== ENV SELECTOR ==='
/sbin/call_qcsapi get_bootcfg_param bootcmd 2>&1
/sbin/call_qcsapi get_bootcfg_param bootselect 2>&1
for d in /dev/mtdblock1 /dev/mtdblock2; do
  [ -r "$d" ] || continue
  echo "$d"
  strings "$d" 2>/dev/null | grep -E '^(bootcmd|bootselect)=' | head -4
done
echo '=== SLOT HASHES ==='
for d in /dev/mtdblock3 /dev/mtdblock4; do
  [ -r "$d" ] && md5sum "$d"
done
echo '=== RECOVERY DEVICES ==='
ls -l /dev/watchdog* /sys/class/watchdog /sys/class/gpio 2>/dev/null || true
dmesg | grep -Ei 'watchdog|reset button|wps|gpio|bootselect' | tail -40
echo '=== FLASH TOOLS ==='
which chkimage 2>/dev/null || ls -l /sbin/chkimage /usr/sbin/chkimage 2>/dev/null
which call_qcsapi 2>/dev/null || ls -l /sbin/call_qcsapi 2>/dev/null
ls -l /etc/default/FWupgrade.sh
'''.strip()
    print(command(proc, probe, "__KERNEL_FLASH_PREFLIGHT__", 120).strip())
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
