#!/usr/bin/env python3
"""Stage and launch the AELITA 5 GHz association-only oracle.

Dry-run is the default. Execution only talks to AELITA over the pinned SSH key,
stages the Windows scripts, registers a SYSTEM scheduled task with an
independent restore watchdog, and waits for the local Windows JSON result after
the Wi-Fi client has restored its primary network.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
import re
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/pydeps"))

import paramiko  # noqa: E402


ACK = "OPENMITRASTAR_QTN_5G_AELITA_ASSOC_ONLY"
ORACLE_HOST = "192.168.1.63"
ORACLE_USER = "AELITA"
ORACLE_KEY = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/oracle_rsa_unencrypted"
KNOWN_HOSTS = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/known_hosts"
RUNNER = ROOT / "tools/run_qtn_5g_assoc_only_oracle.ps1"
STARTER = ROOT / "tools/start_qtn_5g_assoc_only_oracle_task.ps1"
WATCHDOG = ROOT / "tools/restore_wifi_oracle_watchdog.ps1"
REMOTE_DIR = ".openmitrastar-qtn5g-assoc-only"
REMOTE_RESULT = r"C:\ProgramData\OpenMitraStar\oracle\qtn-5g-assoc-only-result.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_local() -> dict[str, object]:
    required = (RUNNER, STARTER, WATCHDOG, ORACLE_KEY, KNOWN_HOSTS)
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("missing local inputs: " + ", ".join(missing))
    key = paramiko.RSAKey.from_private_key_file(str(ORACLE_KEY))
    hosts = paramiko.HostKeys()
    hosts.load(str(KNOWN_HOSTS))
    if ORACLE_HOST not in hosts:
        raise SystemExit("oracle host key is not pinned")
    return {
        "oracle_key_type": key.get_name(),
        "oracle_host_key_pinned": True,
        "files": {
            str(path.relative_to(ROOT)).replace("\\", "/"): sha256(path)
            for path in (RUNNER, STARTER, WATCHDOG)
        },
    }


def oracle_connect(host: str, user: str) -> paramiko.SSHClient:
    client = paramiko.SSHClient()
    client.load_host_keys(str(KNOWN_HOSTS))
    client.set_missing_host_key_policy(paramiko.RejectPolicy())
    key = paramiko.RSAKey.from_private_key_file(str(ORACLE_KEY))
    client.connect(
        host,
        username=user,
        pkey=key,
        look_for_keys=False,
        allow_agent=False,
        timeout=8,
        banner_timeout=10,
        auth_timeout=10,
    )
    return client


def powershell_encoded(command: str) -> str:
    encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
    return (
        "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass "
        f"-EncodedCommand {encoded}"
    )


def oracle_ps(host: str, user: str, command: str, timeout: int = 60) -> str:
    client = oracle_connect(host, user)
    try:
        _, stdout, stderr = client.exec_command(powershell_encoded(command), timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if rc:
            raise RuntimeError(f"oracle PowerShell rc={rc}: {err[:500]}")
        return out
    finally:
        client.close()


def parse_oracle_json(raw: str) -> dict:
    """Parse a Windows oracle JSON file even if console transport adds noise."""
    decoder = json.JSONDecoder(strict=False)
    cleaned = raw.lstrip("\ufeff")
    cleaned = re.sub(r"\x1b\[[0-9;?]*[ -/]*[@-~]", "", cleaned)
    cleaned = cleaned.replace("\x00", "")
    starts = [idx for idx, char in enumerate(cleaned) if char == "{"]
    if not starts:
        raise ValueError("oracle output did not contain a JSON object")
    last_error: Exception | None = None
    for start in starts:
        try:
            parsed, _end = decoder.raw_decode(cleaned[start:])
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(parsed, dict):
            return parsed
    if last_error is not None:
        raise last_error
    raise ValueError("oracle output did not decode to a JSON object")


def stage_oracle(host: str, user: str) -> dict[str, str]:
    files = (RUNNER, STARTER, WATCHDOG)
    client = oracle_connect(host, user)
    try:
        sftp = client.open_sftp()
        try:
            try:
                sftp.mkdir(REMOTE_DIR)
            except OSError:
                pass
            for source in files:
                sftp.put(str(source), f"{REMOTE_DIR}/{source.name}")
        finally:
            sftp.close()
    finally:
        client.close()

    expected = {path.name: sha256(path) for path in files}
    expected_json = json.dumps(expected, separators=(",", ":"))
    command = rf'''
$ErrorActionPreference = 'Stop'
$dir = Join-Path $env:USERPROFILE '{REMOTE_DIR}'
$expected = ConvertFrom-Json @'
{expected_json}
'@
$actual = [ordered]@{{}}
foreach ($name in $expected.PSObject.Properties.Name) {{
  $path = Join-Path $dir $name
  $item = Get-Item -LiteralPath $path -ErrorAction Stop
  if ($item.PSIsContainer -or ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {{ throw "unsafe staged file: $name" }}
  $hash = (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant()
  if ($hash -ne $expected.$name) {{ throw "hash mismatch: $name" }}
  $actual[$name] = $hash
}}
[ordered]@{{schema='openmitrastar.qtn-5g-aelita-assoc-stage/v1';user=$env:USERNAME;files=$actual}} | ConvertTo-Json -Depth 5
'''
    oracle_ps(host, user, command, 60)
    return expected


def start_oracle_task(host: str, user: str, *, test_ssid: str, restore_ssid: str,
                      expected_bssid: str) -> str:
    expected_bssid_ps = expected_bssid.replace("'", "''")
    test_ssid_ps = test_ssid.replace("'", "''")
    restore_ssid_ps = restore_ssid.replace("'", "''")
    bssid_arg = (
        f" -ExpectedBssid '{expected_bssid_ps}'"
        if expected_bssid else ""
    )
    command = rf'''
$ErrorActionPreference = 'Stop'
$dir = Join-Path $env:USERPROFILE '{REMOTE_DIR}'
& (Join-Path $dir 'start_qtn_5g_assoc_only_oracle_task.ps1') `
  -Execute -Ack OPENMITRASTAR_QTN_5G_ASSOC_ONLY_TASK `
  -SourceScript (Join-Path $dir 'run_qtn_5g_assoc_only_oracle.ps1') `
  -WatchdogSourceScript (Join-Path $dir 'restore_wifi_oracle_watchdog.ps1') `
  -TestSsid '{test_ssid_ps}' -RestoreSsid '{restore_ssid_ps}' `
  -WifiInterface 'Wi-Fi'{bssid_arg} -RestoreWatchdogMinutes 8
'''
    return oracle_ps(host, user, command, 90)


def wait_oracle_result(host: str, user: str, timeout: int) -> dict:
    deadline = time.monotonic() + timeout
    command = rf'''
$path = '{REMOTE_RESULT}'
if (Test-Path -LiteralPath $path) {{ Get-Content -LiteralPath $path -Raw }} else {{ exit 44 }}
'''
    last_error = "result-not-seen"
    while time.monotonic() < deadline:
        try:
            raw = oracle_ps(host, user, command, 30)
            return parse_oracle_json(raw)
        except Exception as exc:
            last_error = str(exc)
            time.sleep(5)
    raise RuntimeError(f"oracle result timeout: {last_error[:300]}")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--oracle-host", default=ORACLE_HOST)
    parser.add_argument("--oracle-user", default=ORACLE_USER)
    parser.add_argument("--test-ssid", default="OpenMitraStar-5G-DIAG")
    parser.add_argument("--restore-ssid", default="MOVISTAR-WIFI6-A348")
    parser.add_argument("--expected-bssid", default="")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "outputs/f3-certification/qtn-5g-aelita-assoc-only/latest.json")
    args = parser.parse_args()
    if args.oracle_host != ORACLE_HOST or args.oracle_user != ORACLE_USER:
        raise SystemExit("this gate is pinned to AELITA@192.168.1.63")
    for ssid in (args.test_ssid, args.restore_ssid):
        if not 1 <= len(ssid) <= 32:
            raise SystemExit("SSID length must be 1..32")
    if args.test_ssid == args.restore_ssid:
        raise SystemExit("--test-ssid and --restore-ssid must differ")
    if args.expected_bssid and not re.fullmatch(r"[0-9A-Fa-f]{2}(:[0-9A-Fa-f]{2}){5}", args.expected_bssid):
        raise SystemExit("--expected-bssid must be empty or a colon-separated MAC")

    local = verify_local()
    command = (
        "python tools/run_qtn_5g_aelita_assoc_only.py --execute "
        f"--ack {ACK} --oracle-host 192.168.1.63 --oracle-user AELITA "
        f"--test-ssid {args.test_ssid} --restore-ssid {args.restore_ssid}"
    )
    if not args.execute:
        print(json.dumps({
            "schema": "openmitrastar.qtn-5g-aelita-assoc-only-plan/v1",
            "mode": "dry-run",
            "oracle": f"{ORACLE_USER}@{ORACLE_HOST}",
            "runtime_snapshot": local,
            "policy": {
                "association_only": True,
                "router_mutations": False,
                "serial_uart": False,
                "flash": False,
                "static_ip": False,
                "ping": False,
                "traffic": False,
            },
            "watchdog": "restore_wifi_oracle_watchdog.ps1 preflight-first under SYSTEM",
            "exact_command": command,
            "network_changed_now": False,
        }, indent=2, sort_keys=True))
        print("OMQTN5G_AELITA_ASSOC_ONLY_DRY_RUN_PASS=1 execute=0")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    stage_oracle(args.oracle_host, args.oracle_user)
    start_oracle_task(
        args.oracle_host,
        args.oracle_user,
        test_ssid=args.test_ssid,
        restore_ssid=args.restore_ssid,
        expected_bssid=args.expected_bssid,
    )
    result = wait_oracle_result(args.oracle_host, args.oracle_user, args.timeout)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if result.get("status") != "PASS_ASSOC_ONLY":
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2
    print(f"OMQTN5G_AELITA_ASSOC_ONLY_PASS=1 result={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
