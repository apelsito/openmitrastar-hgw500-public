#!/usr/bin/env python3
"""Run one bounded command through the router's legacy interactive Dropbear."""
from __future__ import annotations

import argparse
import os

from deploy_openmitrastar_07_pty import ROOT, command, credentials, read_until
from winpty import PtyProcess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("shell_command")
    parser.add_argument("--router", default="192.168.1.97")
    parser.add_argument("--timeout", type=int, default=30)
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
    out = command(proc, args.shell_command, "__ROUTER_COMMAND_DONE__", args.timeout)
    print(out)
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
