#!/usr/bin/env python3
"""Read-only snapshot of interfaces, modules, processes and IRQs before RAM handoff."""
from __future__ import annotations

import argparse
import os

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router", default="192.168.1.97")
    parser.add_argument("--quick", action="store_true")
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
    if args.quick:
        out = command(proc,
            "echo MODULES_BEGIN; cat /proc/modules; echo MODULES_END; "
            "echo PROCESSES_BEGIN; ps; echo PROCESSES_END; "
            "echo IRQS_BEGIN; cat /proc/interrupts; echo IRQS_END; dmesg | tail -30",
            "__OMVL_DMA_SNAPSHOT__", 30)
    else:
        out = command(proc,
        "echo INTERFACES_BEGIN; ifconfig -a; echo INTERFACES_END; "
        "echo BRIDGE_BEGIN; brctl show 2>&1; echo BRIDGE_END; "
        "echo MODULES_BEGIN; cat /proc/modules; echo MODULES_END; "
        "echo PROCESSES_BEGIN; ps; echo PROCESSES_END; "
        "echo IRQS_BEGIN; cat /proc/interrupts; echo IRQS_END; "
        "echo NETDEV_BEGIN; cat /proc/net/dev; echo NETDEV_END; "
        "echo QDRV_CONTROL_BEGIN; ls -l /sys/devices/qdrv/control /sys/class/net 2>&1; "
        "echo QDRV_CONTROL_END",
            "__OMVL_DMA_SNAPSHOT__", 60)
    print(out)
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
