#!/usr/bin/env python3
"""Read-only reboot-path inventory over the legacy Dropbear PTY."""
from __future__ import annotations

import os

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    user, password = credentials()
    ssh = os.path.join(os.environ["WINDIR"], "System32", "OpenSSH", "ssh.exe")
    argv = [
        ssh, "-tt", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@192.168.1.90",
    ]
    proc = PtyProcess.spawn(argv, cwd=str(ROOT))
    read_until(proc, "password:", 20)
    proc.write(password + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)
    probe = (
        "echo PATH=$PATH; uname -a; cat /etc/openmitrastar-release 2>/dev/null; "
        "ls -l /sbin/reboot /bin/reboot /sbin/qevt_send_event /scripts/do_system_action "
        "/etc/default/FWupgrade.sh 2>&1; "
        "command -v reboot; command -v qevt_send_event; "
        "busybox 2>&1 | head -n 2; "
        r"grep -n 'qevt\|reboot\|flash_image' /etc/default/FWupgrade.sh /scripts/do_system_action 2>/dev/null"
    )
    output = command(proc, probe, "__REBOOT_PROBE__", 30)
    print(output.strip())
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
