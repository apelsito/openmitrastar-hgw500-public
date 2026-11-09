#!/usr/bin/env python3
"""Execute a side-effect-free invalid WiFi CGI request on the live router."""
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
    body = "bcnint.wlan1=19"
    probe = (
        f"printf '%s' '{body}' | REQUEST_METHOD=POST CONTENT_LENGTH={len(body)} "
        "/var/www/api/wifi 2>&1; echo CGI_RC=$?"
    )
    print(command(proc, probe, "__CGI_PROBE__", 40).strip())
    proc.write("exit\r\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
