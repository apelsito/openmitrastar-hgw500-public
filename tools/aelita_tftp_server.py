#!/usr/bin/env python3
"""Stage and control a temporary, hash-pinned TFTP server on APELSlTO."""
from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/pydeps"))
ORACLE_TOOL = ROOT / "tools/run_qtn_5g_aelita_one_shot.py"
TFTP_SERVER = ROOT / "tools/tiny_tftp_server.py"


def load_oracle():
    spec = importlib.util.spec_from_file_location("qtn_oracle", ORACLE_TOOL)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ps_encoded(command: str) -> str:
    return "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand " + base64.b64encode(command.encode("utf-16le")).decode("ascii")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("start", "stop", "status"))
    parser.add_argument("--host", default="192.168.1.63")
    parser.add_argument("--user", default="AELITA")
    parser.add_argument("--router-ip", default="192.168.1.90")
    parser.add_argument("--candidate", type=Path)
    parser.add_argument("--expected-sha256", default="")
    parser.add_argument("--timeout", type=int, default=1800)
    args = parser.parse_args()
    oracle = load_oracle()
    remote_dir = ".openmitrastar-tftp"
    rule = "OpenMitraStar Bootbase TFTP"

    if args.action == "start":
        if not args.candidate or not args.candidate.is_file():
            raise SystemExit("--candidate is required for start")
        expected = args.expected_sha256.lower()
        if sha256(args.candidate) != expected:
            raise SystemExit("candidate SHA-256 mismatch")
        client = oracle.oracle_connect(args.host, args.user)
        try:
            sftp = client.open_sftp()
            try:
                try: sftp.mkdir(remote_dir)
                except OSError: pass
                sftp.put(str(TFTP_SERVER), f"{remote_dir}/{TFTP_SERVER.name}")
                sftp.put(str(args.candidate), f"{remote_dir}/{args.candidate.name}")
            finally:
                sftp.close()
        finally:
            client.close()
        command = rf'''
$ErrorActionPreference='Stop'
$dir=Join-Path $env:USERPROFILE '.openmitrastar-tftp'
$python=(Get-Command python.exe -ErrorAction Stop).Source
$candidate=Join-Path $dir '{args.candidate.name}'
$actual=(Get-FileHash -LiteralPath $candidate -Algorithm SHA256).Hash.ToLowerInvariant()
if($actual -ne '{expected}'){{throw 'candidate hash mismatch on APELSITO'}}
$pidFile=Join-Path $dir 'server.pid'
if(Test-Path $pidFile){{ $old=[int](Get-Content $pidFile -Raw); Stop-Process -Id $old -Force -ErrorAction SilentlyContinue }}
Get-NetFirewallRule -DisplayName '{rule}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName '{rule}' -Direction Inbound -Action Allow -Protocol UDP -Program $python -RemoteAddress '{args.router_ip}' | Out-Null
$proc=Start-Process -FilePath $python -ArgumentList @((Join-Path $dir 'tiny_tftp_server.py'),'--root',$dir,'--host','0.0.0.0','--port','69') -WindowStyle Hidden -RedirectStandardOutput (Join-Path $dir 'server.stdout.log') -RedirectStandardError (Join-Path $dir 'server.stderr.log') -PassThru
Set-Content -LiteralPath $pidFile -Value $proc.Id -Encoding ascii
Start-Sleep -Seconds 1
[ordered]@{{status='READY';pid=$proc.Id;candidate='{args.candidate.name}';sha256=$actual;udp69=[bool](Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue)}} | ConvertTo-Json -Compress
'''
        print(oracle.oracle_ps(args.host, args.user, command, timeout=90))
        return 0

    if args.action == "stop":
        command = rf'''
$ErrorActionPreference='Continue'
$dir=Join-Path $env:USERPROFILE '.openmitrastar-tftp'
$pidFile=Join-Path $dir 'server.pid'
if(Test-Path $pidFile){{ $pid=[int](Get-Content $pidFile -Raw); Stop-Process -Id $pid -Force -ErrorAction SilentlyContinue; Remove-Item $pidFile -Force -ErrorAction SilentlyContinue }}
Get-NetFirewallRule -DisplayName '{rule}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule
[ordered]@{{status='STOPPED';udp69=[bool](Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue)}} | ConvertTo-Json -Compress
'''
        print(oracle.oracle_ps(args.host, args.user, command, timeout=60))
        return 0

    command = r'''
$dir=Join-Path $env:USERPROFILE '.openmitrastar-tftp'
$pidFile=Join-Path $dir 'server.pid'
$pidValue=if(Test-Path $pidFile){[int](Get-Content $pidFile -Raw)}else{0}
[ordered]@{status=if($pidValue -and (Get-Process -Id $pidValue -ErrorAction SilentlyContinue)){'READY'}else{'STOPPED'};pid=$pidValue;udp69=[bool](Get-NetUDPEndpoint -LocalPort 69 -ErrorAction SilentlyContinue)} | ConvertTo-Json -Compress
'''
    print(oracle.oracle_ps(args.host, args.user, command, timeout=60))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
