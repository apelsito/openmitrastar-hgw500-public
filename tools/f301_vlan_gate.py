#!/usr/bin/env python3
"""Guarded F301 VLAN 4090 physical gate; dry-run is strictly offline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import time
from typing import Any
import uuid

import openmitrastar_f301_hardware_lock as hardware_lock
import run_f301_multicast_igmp_physical as multicast_gate


ROOT = Path(__file__).resolve().parents[1]
DEVICE = "hgw500bna-qcv2-a2-primary"
BUILD = Path.home() / f".openmitrastar/devices/{DEVICE}/firmware/f301-device-bound"
MANIFEST = BUILD / "manifest.json"
CONFIG = BUILD / "openmitrastar-linux510-f301-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.config"
KNOWN_HOSTS = BUILD / "known_hosts.f301"
ENDPOINT_DIR = ROOT / "outputs/kernel-port/f301-vlan-gate"
ENDPOINT = ENDPOINT_DIR / "f301-vlan-endpoint.arc700"
ENDPOINT_MANIFEST = ENDPOINT_DIR / "manifest.json"
CONTROLLER_SCRIPT = ROOT / "tools/f301_vlan_controller.ps1"
UART_GUARD_SCRIPT = ROOT / "tools/f301_vlan_uart_guard.ps1"
UART_EVIDENCE = ROOT / "outputs/uart-live/f165-uart-passive-20260901/capture-status.json"
EXPECTED_VERSION = "lyoko-foundation-6.6.1-f301-f300-capability-truth-device"
EXPECTED_CANDIDATE_SHA256 = "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262"
EXPECTED_CONFIG_SHA256 = "cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e"
EXPECTED_UART_PNP = r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000"
ACK = "OPENMITRASTAR_F301_VLAN4090_PHYSICAL"
VLAN_ID = 4090
VLAN_INTERFACE = "eth0.4090"
ROUTER_VLAN_IP = "10.254.90.1"
CONTROLLER_VLAN_IP = "10.254.90.2"
VLAN_NETMASK = "255.255.255.252"
PREFIX_LENGTH = 30
UDP_PORT = 40900
PACKET_COUNT = 128
PAYLOAD_BYTES = 512
WATCHDOG_SECONDS = 300
PLAN_SCHEMA = "openmitrastar.f301-vlan4090-plan/v1"
RESULT_SCHEMA = "openmitrastar.f301-vlan4090-physical/v1"
REMOTE_ROOT = "/run/openmitrastar/vlan4090"

wpa = multicast_gate.wpa


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="ascii"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temporary.open("w", encoding="ascii", newline="\n") as stream:
            stream.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def powershell_json(args: list[str], timeout: int = 60) -> dict[str, Any]:
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip()[:600] or f"PowerShell rc={proc.returncode}")
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("PowerShell returned no JSON")
    payload = json.loads(lines[-1])
    if not isinstance(payload, dict):
        raise RuntimeError("PowerShell returned non-object JSON")
    return payload


def active_workflow_evidence() -> dict[str, Any]:
    command = r'''
$patterns = @(
  'run_f301_sequential_dual_radio_soak[.]py',
  'run_f301_multicast_igmp_physical[.]py',
  'f301_dfs.*(physical|gate)',
  'f301_vlan_gate[.]py'
)
$items = Get-CimInstance Win32_Process -ErrorAction Stop |
  Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -and
    ($patterns | Where-Object { $_.CommandLine -match $_ } | Select-Object -First 1)
  } |
  Select-Object ProcessId, Name, CommandLine
@($items | ForEach-Object {
  [ordered]@{pid=[int]$_.ProcessId;name=[string]$_.Name;kind=if($_.CommandLine -match 'soak'){'soak'}elseif($_.CommandLine -match 'multicast'){'multicast'}elseif($_.CommandLine -match 'dfs'){'dfs'}else{'vlan'}}
}) | ConvertTo-Json -Compress
'''
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip()[:300] or f"rc={proc.returncode}")
        decoded = json.loads(proc.stdout.strip() or "[]")
        if isinstance(decoded, dict):
            decoded = [decoded]
        if not isinstance(decoded, list):
            raise RuntimeError("unexpected process inventory")
        processes = [
            item for item in decoded
            if isinstance(item, dict) and int(item.get("pid") or 0) != os.getpid()
        ]
        return {
            "active": bool(processes),
            "processes": processes,
            "detection_error": "",
            "shared_lock_present": hardware_lock.LOCK_DIR.exists(),
        }
    except Exception as exc:
        return {
            "active": False,
            "processes": [],
            "detection_error": f"{type(exc).__name__}: {str(exc)[:300]}",
            "shared_lock_present": hardware_lock.LOCK_DIR.exists(),
        }


def workflow_guard_clear(evidence: dict[str, Any]) -> bool:
    return bool(
        evidence.get("active") is False
        and not evidence.get("detection_error")
        and evidence.get("shared_lock_present") is False
    )


def local_preflight() -> dict[str, Any]:
    errors: list[str] = []
    manifest: dict[str, Any] = {}
    endpoint_manifest: dict[str, Any] = {}
    uart: dict[str, Any] = {}
    try:
        manifest = read_json(MANIFEST)
    except Exception as exc:
        errors.append(f"f301-manifest:{type(exc).__name__}")
    try:
        endpoint_manifest = read_json(ENDPOINT_MANIFEST)
    except Exception as exc:
        errors.append(f"endpoint-manifest:{type(exc).__name__}")
    try:
        uart = read_json(UART_EVIDENCE)
    except Exception as exc:
        errors.append(f"uart-evidence:{type(exc).__name__}")

    artifact = manifest.get("artifacts", {}).get("webformat", {}) if manifest else {}
    candidate = BUILD / str(artifact.get("file") or "")
    checks = {
        "candidate_present": candidate.is_file(),
        "candidate_sha256": candidate.is_file() and sha256_file(candidate) == EXPECTED_CANDIDATE_SHA256,
        "manifest_sha256": artifact.get("sha256") == EXPECTED_CANDIDATE_SHA256,
        "config_present": CONFIG.is_file(),
        "config_sha256": CONFIG.is_file() and sha256_file(CONFIG) == EXPECTED_CONFIG_SHA256,
        "kernel_8021q": CONFIG.is_file() and "CONFIG_VLAN_8021Q=y\n" in CONFIG.read_text(encoding="ascii"),
        "bridge_vlan_filtering_off": CONFIG.is_file() and "# CONFIG_BRIDGE_VLAN_FILTERING is not set\n" in CONFIG.read_text(encoding="ascii"),
        "endpoint_present": ENDPOINT.is_file(),
        "endpoint_hash": ENDPOINT.is_file()
        and endpoint_manifest.get("artifact", {}).get("sha256") == sha256_file(ENDPOINT),
        "endpoint_contract": endpoint_manifest.get("contract", {}).get("vlan_id") == VLAN_ID
        and endpoint_manifest.get("contract", {}).get("bridge_mutation") is False
        and endpoint_manifest.get("contract", {}).get("mtd_writes") is False,
        "controller_script": CONTROLLER_SCRIPT.is_file(),
        "uart_guard_script": UART_GUARD_SCRIPT.is_file(),
        "known_hosts": KNOWN_HOSTS.is_file(),
        "uart_recovery_evidence": uart.get("ready") is True
        and uart.get("pinned_pnp_device_id") == EXPECTED_UART_PNP
        and uart.get("dtr") is False
        and uart.get("rts") is False,
    }
    errors.extend(name for name, passed in checks.items() if not passed)
    return {
        "ready": not errors,
        "checks": checks,
        "errors": errors,
        "candidate_file": candidate.name if candidate.name else "",
        "candidate_sha256": sha256_file(candidate) if candidate.is_file() else "",
        "endpoint_sha256": sha256_file(ENDPOINT) if ENDPOINT.is_file() else "",
        "uart_evidence": str(UART_EVIDENCE.relative_to(ROOT)),
        "hardware_actions": False,
    }


def strict_ssh_args(host: str, key: Path) -> list[str]:
    return [
        "ssh", "-i", str(key), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={KNOWN_HOSTS}", "-o", "HostKeyAlgorithms=+ssh-rsa",
        "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa", "-o", "LogLevel=ERROR", f"root@{host}",
    ]


def router_exec(host: str, command: str, timeout: int = 30, input_bytes: bytes | None = None) -> str:
    last_error = ""
    for key in wpa.router_key_candidates():
        proc = subprocess.run(
            [*strict_ssh_args(host, key), command],
            cwd=ROOT,
            input=input_bytes,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        if proc.returncode == 0:
            return out
        last_error = f"rc={proc.returncode}: {err[:300]}"
        if "Permission denied" not in err:
            break
    raise RuntimeError(f"router SSH failed: {last_error}")


def router_upload(host: str, local: Path, remote: str, mode: str = "0700") -> None:
    if not re.fullmatch(r"/run/openmitrastar/vlan4090/[A-Za-z0-9._-]+", remote):
        raise ValueError("unsafe remote path")
    command = f"set -eu; umask 077; mkdir -p {REMOTE_ROOT}; cat > {remote}; chmod {mode} {remote}"
    router_exec(host, command, timeout=45, input_bytes=local.read_bytes())


def rollback_script() -> bytes:
    text = f"""#!/bin/sh
set -u
root={REMOTE_ROOT}
reason=${{1:-unknown}}
if [ -f "$root/server.pid" ]; then kill "$(cat "$root/server.pid")" 2>/dev/null || true; fi
if [ -x "$root/f301-vlan-endpoint" ]; then "$root/f301-vlan-endpoint" delete {VLAN_INTERFACE} >/dev/null 2>&1 || true; fi
rm -f "$root/active"
printf 'OMF301_VLAN_ROLLBACK=complete reason=%s\n' "$reason" >> "$root/rollback.log"
exit 0
"""
    return text.encode("ascii")


def upload_bytes(host: str, content: bytes, remote: str, mode: str = "0700") -> None:
    temporary = ROOT / "outputs/preflight/.f301-vlan-upload.tmp"
    try:
        temporary.parent.mkdir(parents=True, exist_ok=True)
        temporary.write_bytes(content)
        router_upload(host, temporary, remote, mode)
    finally:
        temporary.unlink(missing_ok=True)


def router_snapshot(host: str) -> dict[str, Any]:
    command = r'''set -eu
printf 'VERSION='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'PORTS='; for p in /sys/class/net/br0/brif/*; do [ -e "$p" ] && printf '%s,' "${p##*/}"; done; echo
printf 'BR0_STATE='; cat /sys/class/net/br0/operstate
printf 'BR0_MTU='; cat /sys/class/net/br0/mtu
printf 'IP_FORWARD='; cat /proc/sys/net/ipv4/ip_forward
printf 'PERSIST='; awk '$2=="/persist" {print $4; found=1} END {if(!found) print "unmounted"}' /proc/mounts
printf 'MTD_TABLE='; sha256sum /proc/mtd | awk '{print $1}'
printf 'ROUTE_TABLE='; sha256sum /proc/net/route | awk '{print $1}'
printf 'VLAN_CONFIG='; if [ -r /proc/net/vlan/config ]; then sha256sum /proc/net/vlan/config | awk '{print $1}'; else echo absent; fi
printf 'VLAN_PRESENT='; if [ -d /sys/class/net/eth0.4090 ]; then echo 1; else echo 0; fi
printf 'FATAL='; dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|qdrv.*fatal|muc.*fatal|auc.*fatal' || true
for dev in br0 eth0 wlan0 wifi0 eth0.4090; do
  [ -d "/sys/class/net/$dev" ] || continue
  printf '%s_RX=' "$dev"; cat "/sys/class/net/$dev/statistics/rx_packets"
  printf '%s_TX=' "$dev"; cat "/sys/class/net/$dev/statistics/tx_packets"
done
'''
    payload: dict[str, Any] = {"ports": []}
    for line in router_exec(host, command).splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        value = value.strip()
        if key == "VERSION":
            payload["version"] = value
        elif key == "PORTS":
            payload["ports"] = sorted(item for item in value.split(",") if item)
        elif key in {"BR0_STATE", "BR0_MTU", "IP_FORWARD", "PERSIST", "MTD_TABLE", "ROUTE_TABLE", "VLAN_CONFIG"}:
            payload[key.lower()] = value
        elif key in {"VLAN_PRESENT", "FATAL"} or key.endswith(("_RX", "_TX")):
            payload[key.lower()] = int(value or 0)
    required = {"version", "ports", "br0_state", "br0_mtu", "ip_forward", "persist", "mtd_table", "route_table", "vlan_config", "vlan_present", "fatal"}
    missing = sorted(required.difference(payload))
    if missing:
        raise RuntimeError(f"router snapshot missing: {', '.join(missing)}")
    return payload


def immutable_management(snapshot: dict[str, Any]) -> dict[str, Any]:
    return {
        key: snapshot.get(key)
        for key in (
            "ports", "br0_state", "br0_mtu", "ip_forward", "persist",
            "mtd_table", "route_table", "vlan_config",
        )
    }


def wait_json(path: Path, timeout: int, expected_key: str, expected_value: Any) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    last_error = "not-created"
    while time.monotonic() < deadline:
        try:
            payload = read_json(path)
            if payload.get(expected_key) == expected_value:
                return payload
            last_error = f"{expected_key}={payload.get(expected_key)!r}"
        except Exception as exc:
            last_error = f"{type(exc).__name__}: {str(exc)[:100]}"
        time.sleep(0.2)
    raise RuntimeError(f"timeout waiting for {path.name}: {last_error}")


def start_guard(script: Path, arguments: list[str], stdout_path: Path, stderr_path: Path) -> subprocess.Popen[str]:
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script), *arguments],
        cwd=ROOT,
        text=True,
        stdout=stdout_handle,
        stderr=stderr_handle,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    stdout_handle.close()
    stderr_handle.close()
    return process


def vlan_packet(token: str, direction: str, sequence: int, size: int = PAYLOAD_BYTES) -> bytes:
    header = f"LYOKO-VLAN1|{token}|{direction}|{sequence}|".encode("ascii")
    if len(header) > size:
        raise ValueError("payload too small")
    return header + b"x" * (size - len(header))


def parse_vlan_reply(payload: bytes, token: str) -> int | None:
    prefix = f"LYOKO-VLAN1|{token}|DOWN|".encode("ascii")
    if not payload.startswith(prefix):
        return None
    try:
        return int(payload[len(prefix):].split(b"|", 1)[0])
    except (ValueError, IndexError):
        return None


def run_vlan_traffic(token: str, count: int, timeout_seconds: float = 1.0) -> dict[str, Any]:
    if not re.fullmatch(r"[0-9a-f]{32}", token):
        raise ValueError("traffic token must be 32 lowercase hex characters")
    received: set[int] = set()
    sent = 0
    retransmissions = 0
    started = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp:
        udp.bind((CONTROLLER_VLAN_IP, 0))
        udp.settimeout(timeout_seconds)
        for sequence in range(count):
            for attempt in range(3):
                udp.sendto(vlan_packet(token, "UP", sequence), (ROUTER_VLAN_IP, UDP_PORT))
                sent += 1
                if attempt:
                    retransmissions += 1
                try:
                    payload, peer = udp.recvfrom(PAYLOAD_BYTES + 64)
                except socket.timeout:
                    continue
                parsed = parse_vlan_reply(payload, token)
                if peer[0] == ROUTER_VLAN_IP and parsed == sequence:
                    received.add(sequence)
                    break
    elapsed = max(time.monotonic() - started, 0.001)
    return {
        "requested_packets": count,
        "wire_sends": sent,
        "received_packets": len(received),
        "lost_packets": count - len(received),
        "retransmissions": retransmissions,
        "payload_bytes": PAYLOAD_BYTES,
        "elapsed_seconds": round(elapsed, 3),
        "round_trip_mbps": round((len(received) * PAYLOAD_BYTES * 2 * 8) / elapsed / 1_000_000, 3),
        "pass": len(received) == count,
    }


def aelita_monitor_script(router_host: str, seconds: int, result_path: str) -> str:
    return rf'''
$ErrorActionPreference = 'Stop'
$ok = 0
$failed = 0
$deadline = [DateTime]::UtcNow.AddSeconds({seconds})
while ([DateTime]::UtcNow -lt $deadline) {{
  if (Test-NetConnection -ComputerName {router_host} -Port 22 -InformationLevel Quiet -WarningAction SilentlyContinue) {{ $ok++ }} else {{ $failed++ }}
  Start-Sleep -Milliseconds 500
}}
$payload = [ordered]@{{schema='openmitrastar.f301-vlan-aelita-monitor/v1';tcp22_pass=$ok;tcp22_fail=$failed;pass=($ok -gt 0 -and $failed -eq 0);client_identifiers_logged=$false}}
[IO.File]::WriteAllText('{result_path}', (($payload | ConvertTo-Json -Compress) + "`n"), [Text.UTF8Encoding]::new($false))
'''


def start_aelita_monitor(host: str, user: str, router_host: str, seconds: int) -> dict[str, str]:
    run_id = uuid.uuid4().hex[:12]
    root = r"C:\ProgramData\OpenMitraStar\vlan4090"
    result = rf"{root}\monitor-{run_id}.json"
    task_name = f"OpenMitraStar-F301-VLAN-{run_id}"
    worker = aelita_monitor_script(router_host, seconds, result)
    encoded = __import__("base64").b64encode(worker.encode("utf-16le")).decode("ascii")
    command = rf'''
$ErrorActionPreference='Stop'
$root='{root}'; New-Item -ItemType Directory -Force -Path $root | Out-Null
$action=New-ScheduledTaskAction -Execute "$env:WINDIR\System32\WindowsPowerShell\v1.0\powershell.exe" -Argument '-NoProfile -EncodedCommand {encoded}'
$trigger=New-ScheduledTaskTrigger -Once -At ([DateTime]::Now.AddSeconds(2))
$principal=New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
Register-ScheduledTask -TaskName '{task_name}' -Action $action -Trigger $trigger -Principal $principal -Force | Out-Null
Start-ScheduledTask -TaskName '{task_name}'
[ordered]@{{task='{task_name}';result='{result}';started=$true}} | ConvertTo-Json -Compress
'''
    return json.loads(wpa.oracle_ps(host, user, command, timeout=60).strip())


def collect_aelita_monitor(host: str, user: str, task: dict[str, str], timeout: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        command = rf"if(Test-Path -LiteralPath '{task['result']}'){{Get-Content -Raw -LiteralPath '{task['result']}'}}"
        raw = wpa.oracle_ps(host, user, command, timeout=30).strip()
        if raw:
            payload = json.loads(raw)
            cleanup = rf"Unregister-ScheduledTask -TaskName '{task['task']}' -Confirm:$false -ErrorAction SilentlyContinue; Remove-Item -LiteralPath '{task['result']}' -Force -ErrorAction SilentlyContinue"
            wpa.oracle_ps(host, user, cleanup, timeout=30)
            return payload
        time.sleep(2)
    raise RuntimeError("AELITA management monitor result timeout")


def cleanup_aelita_monitor(host: str, user: str, task: dict[str, str]) -> None:
    if not task:
        return
    command = rf"Unregister-ScheduledTask -TaskName '{task.get('task', '')}' -Confirm:$false -ErrorAction SilentlyContinue; Remove-Item -LiteralPath '{task.get('result', '')}' -Force -ErrorAction SilentlyContinue"
    try:
        wpa.oracle_ps(host, user, command, timeout=30)
    except Exception:
        pass


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--execute", action="store_true")
    result.add_argument("--ack", default="")
    result.add_argument("--router-host", default="192.168.1.90")
    result.add_argument("--oracle-host", default="192.168.1.63")
    result.add_argument("--oracle-user", default="AELITA")
    result.add_argument("--controller-interface", default="")
    result.add_argument("--uart-port", default="COM3")
    result.add_argument("--uart-pnp-device-id", default=EXPECTED_UART_PNP)
    result.add_argument("--watchdog-seconds", type=int, default=WATCHDOG_SECONDS)
    result.add_argument("--packet-count", type=int, default=PACKET_COUNT)
    result.add_argument("--output-dir", type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    if not 180 <= args.watchdog_seconds <= 900:
        raise SystemExit("--watchdog-seconds must be 180..900")
    if not 16 <= args.packet_count <= 4096:
        raise SystemExit("--packet-count must be 16..4096")
    if ipaddress.ip_address(args.router_host).version != 4 or ipaddress.ip_address(args.oracle_host).version != 4:
        raise SystemExit("router and oracle hosts must be IPv4 addresses")
    if args.output_dir is None:
        args.output_dir = ROOT / f"outputs/certification/f301-vlan4090-{utcnow():%Y%m%dT%H%M%SZ}"
    args.output_dir = args.output_dir.resolve()
    if args.output_dir.exists() and any(args.output_dir.iterdir()):
        raise SystemExit("refusing to overwrite VLAN evidence")
    args.output_dir.mkdir(parents=True, exist_ok=True)

    local = local_preflight()
    conflicts = active_workflow_evidence()
    plan = {
        "schema": PLAN_SCHEMA,
        "generated_at": utcnow().isoformat(),
        "mode": "execute" if args.execute else "dry-run",
        "required_firmware": EXPECTED_VERSION,
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "vlan": {
            "id": VLAN_ID,
            "parent": "eth0",
            "interface": VLAN_INTERFACE,
            "router_address": f"{ROUTER_VLAN_IP}/{PREFIX_LENGTH}",
            "controller_address": f"{CONTROLLER_VLAN_IP}/{PREFIX_LENGTH}",
            "attached_to_br0": False,
            "qdrv_vlan_path": False,
        },
        "traffic": {
            "tagged_endpoint": "controller dedicated wired adapter",
            "untagged_management_observer": "AELITA TCP/22 monitor",
            "packets": args.packet_count,
            "payload_bytes": PAYLOAD_BYTES,
        },
        "recovery": {
            "router_local_watchdog": True,
            "controller_adapter_watchdog": True,
            "uart_guard": True,
            "uart_port": args.uart_port,
            "uart_pnp_device_id": args.uart_pnp_device_id,
            "all_three_required_before_mutation": True,
        },
        "snapshot": ["br0 ports/state/mtu", "ip_forward", "mtd table hash", "persist mount", "VLAN table", "controller adapter VLAN/IP state"],
        "rollback": "remove eth0.4090, restore exact controller VLAN property, verify br0 invariant, then disarm watchdogs",
        "exclusion": conflicts,
        "local_preflight": local,
        "hardware_preflight": "DEFERRED_UNTIL_EXECUTE",
        "execute_eligible_offline": bool(local.get("ready") and workflow_guard_clear(conflicts)),
        "execute_allowed_now": False,
        "execute_blocked_until": [
            "controller VLAN property and elevation verified live",
            "router and AELITA SSH verified live",
            "router-local rollback watchdog armed",
            "controller restore watchdog armed",
            "UART Magic SysRq help round-trip verified live",
        ],
        "hardware_actions_performed": False,
        "router_persistence": False,
        "mtd_writes": False,
        "flash": False,
    }
    atomic_write_json(args.output_dir / "plan.json", plan)
    print(json.dumps(plan, indent=2, sort_keys=True))
    if not args.execute:
        return 0 if local.get("ready") else 1

    if args.ack != ACK:
        raise SystemExit("exact --ack is required")
    if not args.controller_interface:
        raise SystemExit("--controller-interface is required")
    if args.uart_pnp_device_id != EXPECTED_UART_PNP:
        raise SystemExit("UART PnP identity does not match the pinned recovery device")
    if not local.get("ready") or not workflow_guard_clear(conflicts):
        atomic_write_json(args.output_dir / "blocked.json", {
            "schema": RESULT_SCHEMA,
            "status": "BLOCKED",
            "phase": "offline-preflight-or-exclusion",
            "local_preflight": local,
            "exclusion": conflicts,
            "hardware_actions_performed": False,
        })
        return 2

    before: dict[str, Any] = {}
    after: dict[str, Any] = {}
    controller_snapshot: dict[str, Any] = {}
    controller_restore: dict[str, Any] = {}
    traffic: dict[str, Any] = {}
    aelita_result: dict[str, Any] = {}
    error = ""
    phase = "lock"
    mutation_started = False
    router_watchdog_armed = False
    router_rollback_ok = False
    controller_mutation_possible = False
    uart_guard: subprocess.Popen[str] | None = None
    controller_guard: subprocess.Popen[str] | None = None
    aelita_task: dict[str, str] = {}
    state_dir = args.output_dir / "recovery"
    state_dir.mkdir(parents=True, exist_ok=True)
    controller_snapshot_path = state_dir / "controller-snapshot.json"

    try:
        with hardware_lock.acquire_physical_lock("f301-vlan4090", args.output_dir):
            current = active_workflow_evidence()
            current["shared_lock_present"] = False
            current["processes"] = [item for item in current.get("processes", []) if int(item.get("pid") or 0) != os.getpid()]
            current["active"] = bool(current["processes"])
            if not workflow_guard_clear(current):
                raise RuntimeError("soak, multicast, DFS or another VLAN gate is active or unobservable")

            phase = "controller-audit"
            controller_audit = powershell_json([
                "-File", str(CONTROLLER_SCRIPT), "-Action", "Audit", "-InterfaceAlias", args.controller_interface,
            ])
            atomic_write_json(args.output_dir / "controller-audit.json", controller_audit)
            if controller_audit.get("ready") is not True or controller_audit.get("administrator") is not True:
                raise RuntimeError("controller adapter is not VLAN-ready under an elevated session")

            phase = "ssh-preflight"
            wpa.validate_oracle_target(args.oracle_host, args.oracle_user)
            before = router_snapshot(args.router_host)
            atomic_write_json(args.output_dir / "router-before.json", before)
            if before.get("version") != EXPECTED_VERSION or before.get("vlan_present") != 0:
                raise RuntimeError("router is not clean exact F301")

            phase = "stage-ram-tools"
            router_upload(args.router_host, ENDPOINT, f"{REMOTE_ROOT}/f301-vlan-endpoint")
            upload_bytes(args.router_host, rollback_script(), f"{REMOTE_ROOT}/rollback.sh")
            helper_selftest = router_exec(args.router_host, f"{REMOTE_ROOT}/f301-vlan-endpoint selftest")
            if "OMF301_VLAN_SELFTEST=pass" not in helper_selftest:
                raise RuntimeError("ARC700 endpoint selftest failed")

            phase = "controller-snapshot"
            controller_snapshot = powershell_json([
                "-File", str(CONTROLLER_SCRIPT), "-Action", "Snapshot",
                "-InterfaceAlias", args.controller_interface, "-SnapshotPath", str(controller_snapshot_path),
            ])
            atomic_write_json(args.output_dir / "controller-before.json", controller_snapshot)

            phase = "controller-watchdog"
            controller_guard = start_guard(
                CONTROLLER_SCRIPT,
                ["-Action", "Watchdog", "-SnapshotPath", str(controller_snapshot_path),
                 "-StateDirectory", str(state_dir), "-TimeoutSeconds", str(args.watchdog_seconds - 30)],
                state_dir / "controller-watchdog.stdout.log",
                state_dir / "controller-watchdog.stderr.log",
            )
            controller_guard_ready = wait_json(state_dir / "controller-watchdog-ready.json", 20, "ready", True)

            phase = "router-watchdog"
            router_watchdog = router_exec(
                args.router_host,
                f"set -eu; : > {REMOTE_ROOT}/active; "
                f"(sleep {args.watchdog_seconds - 60}; {REMOTE_ROOT}/rollback.sh router-watchdog) "
                f">{REMOTE_ROOT}/watchdog.log 2>&1 & echo $! > {REMOTE_ROOT}/watchdog.pid; "
                f"kill -0 $(cat {REMOTE_ROOT}/watchdog.pid); echo OMF301_VLAN_ROUTER_WATCHDOG=ready",
            )
            if "OMF301_VLAN_ROUTER_WATCHDOG=ready" not in router_watchdog:
                raise RuntimeError("router-local watchdog did not arm")
            router_watchdog_armed = True

            phase = "uart-guard"
            uart_guard = start_guard(
                UART_GUARD_SCRIPT,
                ["-Port", args.uart_port, "-ExpectedPnpDeviceId", args.uart_pnp_device_id,
                 "-TimeoutSeconds", str(args.watchdog_seconds), "-StateDirectory", str(state_dir)],
                state_dir / "uart-guard.stdout.log",
                state_dir / "uart-guard.stderr.log",
            )
            uart_ready = wait_json(state_dir / "uart-guard-ready.json", 35, "ready", True)
            recovery_ready = bool(controller_guard_ready.get("ready") and uart_ready.get("sysrq_help_verified"))
            if not recovery_ready:
                raise RuntimeError("independent recovery routes are not ready")

            phase = "aelita-monitor"
            aelita_task = start_aelita_monitor(args.oracle_host, args.oracle_user, args.router_host, 75)
            if aelita_task.get("started") is not True:
                raise RuntimeError("AELITA management monitor did not start")

            phase = "router-vlan-create"
            mutation_started = True
            router_exec(args.router_host, f"{REMOTE_ROOT}/f301-vlan-endpoint create eth0 {VLAN_INTERFACE} {VLAN_ID} {ROUTER_VLAN_IP} {VLAN_NETMASK}")
            server_token = uuid.uuid4().hex
            router_exec(
                args.router_host,
                f"({REMOTE_ROOT}/f301-vlan-endpoint serve {ROUTER_VLAN_IP} {UDP_PORT} {server_token} "
                f"{args.packet_count} {PAYLOAD_BYTES} 120 {REMOTE_ROOT}/server.json "
                f">{REMOTE_ROOT}/server.stdout 2>{REMOTE_ROOT}/server.stderr; echo $? >{REMOTE_ROOT}/server.rc) & "
                f"echo $! > {REMOTE_ROOT}/server.pid",
            )

            phase = "controller-vlan-apply"
            controller_mutation_possible = True
            controller_apply = powershell_json([
                "-File", str(CONTROLLER_SCRIPT), "-Action", "Apply", "-SnapshotPath", str(controller_snapshot_path),
                "-VlanId", str(VLAN_ID), "-VlanAddress", CONTROLLER_VLAN_IP, "-PrefixLength", str(PREFIX_LENGTH),
            ], timeout=90)
            atomic_write_json(args.output_dir / "controller-applied.json", controller_apply)
            if controller_apply.get("applied") is not True:
                raise RuntimeError("controller VLAN apply did not complete")

            phase = "tagged-traffic"
            traffic = run_vlan_traffic(server_token, args.packet_count)
            atomic_write_json(args.output_dir / "vlan-traffic.json", traffic)
            if traffic.get("pass") is not True:
                raise RuntimeError("tagged VLAN traffic failed")

            phase = "controller-restore"
            controller_restore = powershell_json([
                "-File", str(CONTROLLER_SCRIPT), "-Action", "Restore", "-SnapshotPath", str(controller_snapshot_path),
            ], timeout=90)
            atomic_write_json(args.output_dir / "controller-restored.json", controller_restore)
            if controller_restore.get("restored") is not True or controller_restore.get("vlan_address_absent") is not True:
                raise RuntimeError("controller adapter did not restore exactly")
            controller_mutation_possible = False

            phase = "router-rollback"
            router_exec(args.router_host, f"{REMOTE_ROOT}/rollback.sh coordinator")
            router_rollback_ok = True
            router_exec(args.router_host, f"if [ -f {REMOTE_ROOT}/watchdog.pid ]; then kill $(cat {REMOTE_ROOT}/watchdog.pid) 2>/dev/null || true; fi")
            router_watchdog_armed = False

            phase = "aelita-result"
            aelita_result = collect_aelita_monitor(args.oracle_host, args.oracle_user, aelita_task, 120)
            atomic_write_json(args.output_dir / "aelita-management.json", aelita_result)

            phase = "final-snapshot"
            after = router_snapshot(args.router_host)
            atomic_write_json(args.output_dir / "router-after.json", after)
    except Exception as exc:
        error = f"{phase}: {type(exc).__name__}: {str(exc)[:900]}"
    finally:
        if controller_mutation_possible:
            try:
                controller_restore = powershell_json([
                    "-File", str(CONTROLLER_SCRIPT), "-Action", "Restore", "-SnapshotPath", str(controller_snapshot_path),
                ], timeout=90)
                controller_mutation_possible = controller_restore.get("restored") is not True
            except Exception:
                (state_dir / "controller-watchdog-trigger").touch()
        if (mutation_started or router_watchdog_armed) and not router_rollback_ok:
            try:
                router_exec(args.router_host, f"{REMOTE_ROOT}/rollback.sh coordinator-finally", timeout=20)
                router_rollback_ok = True
                try:
                    router_exec(args.router_host, f"if [ -f {REMOTE_ROOT}/watchdog.pid ]; then kill $(cat {REMOTE_ROOT}/watchdog.pid) 2>/dev/null || true; fi", timeout=10)
                except Exception:
                    pass
            except Exception:
                (state_dir / "uart-guard-trigger").touch()
        if controller_guard:
            if controller_mutation_possible:
                (state_dir / "controller-watchdog-trigger").touch()
                try:
                    watchdog_result = wait_json(
                        state_dir / "controller-watchdog-result.json", 60, "status", "RESTORED"
                    )
                    controller_restore = watchdog_result
                    controller_mutation_possible = watchdog_result.get("restored") is not True
                except Exception:
                    pass
            else:
                (state_dir / "controller-watchdog-stop").touch()
            try:
                controller_guard.wait(timeout=70 if controller_mutation_possible else 20)
            except subprocess.TimeoutExpired:
                pass
        if uart_guard:
            if router_rollback_ok or not mutation_started:
                (state_dir / "uart-guard-stop").touch()
            try:
                uart_guard.wait(timeout=40)
            except subprocess.TimeoutExpired:
                pass
        if not after and router_rollback_ok:
            try:
                after = router_snapshot(args.router_host)
                atomic_write_json(args.output_dir / "router-after.json", after)
            except Exception:
                pass
        if aelita_task and not aelita_result:
            cleanup_aelita_monitor(args.oracle_host, args.oracle_user, aelita_task)

    management_restored = bool(before and after and immutable_management(before) == immutable_management(after))
    passed = bool(
        not error
        and traffic.get("pass") is True
        and aelita_result.get("pass") is True
        and controller_restore.get("restored") is True
        and router_rollback_ok
        and management_restored
        and after.get("vlan_present") == 0
        and after.get("fatal") == before.get("fatal")
        and after.get("version") == EXPECTED_VERSION
    )
    result = {
        "schema": RESULT_SCHEMA,
        "generated_at": utcnow().isoformat(),
        "status": "PASS" if passed else "FAIL",
        "firmware": EXPECTED_VERSION,
        "candidate_sha256": EXPECTED_CANDIDATE_SHA256,
        "vlan_id": VLAN_ID,
        "traffic": traffic,
        "aelita_management": aelita_result,
        "controller_restore": controller_restore,
        "router_rollback": router_rollback_ok,
        "br0_and_management_restored_exactly": management_restored,
        "vlan_absent_after": after.get("vlan_present") == 0 if after else False,
        "fatal_before": before.get("fatal") if before else None,
        "fatal_after": after.get("fatal") if after else None,
        "error": error,
        "recovery": {
            "router_local_watchdog": True,
            "controller_adapter_watchdog": True,
            "uart_guard": True,
            "fail_closed_before_mutation": True,
        },
        "router_persistence": False,
        "mtd_writes": False,
        "flash": False,
        "secrets_logged": False,
        "client_macs_logged": False,
    }
    atomic_write_json(args.output_dir / "result.json", result)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
