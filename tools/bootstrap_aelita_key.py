#!/usr/bin/env python3
from __future__ import annotations

import base64
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import paramiko  # noqa: E402


def main() -> int:
    old_key = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/oracle_rsa"
    new_public = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/oracle_rsa_unencrypted.pub"
    key = paramiko.RSAKey.from_private_key_file(str(old_key), password='""')
    public_b64 = base64.b64encode(new_public.read_bytes()).decode("ascii")
    script = rf"""
$ErrorActionPreference = 'Stop'
$key = [Text.Encoding]::ASCII.GetString([Convert]::FromBase64String('{public_b64}')).Trim()
$path = Join-Path $env:ProgramData 'ssh\administrators_authorized_keys'
[IO.File]::WriteAllText($path, $key + "`r`n", [Text.Encoding]::ASCII)
Restart-Service sshd
Write-Output 'AELITA_KEY_ROTATION_PASS=1'
"""
    encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            "192.168.1.63",
            username="AELITA",
            pkey=key,
            look_for_keys=False,
            allow_agent=False,
            timeout=5,
            banner_timeout=8,
            auth_timeout=8,
        )
        _, stdout, stderr = client.exec_command(
            f"powershell.exe -NoProfile -EncodedCommand {encoded}", timeout=20
        )
        out = stdout.read().decode("utf-8", errors="replace")
        err = stderr.read().decode("utf-8", errors="replace")
        status = stdout.channel.recv_exit_status()
        print(out, end="")
        if err:
            print(err, file=sys.stderr, end="")
        return status
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
