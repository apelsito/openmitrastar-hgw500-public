#!/usr/bin/env python3
"""Run the AELITA 2.4 GHz WPA2 speed test while sampling router counters.

This helper does not change flash, reboot the router, or print WiFi secrets. It
wraps the existing AELITA WPA2 runtime test and records read-only router state
while the transfer is active, so low-throughput runs can be diagnosed from one
artifact directory.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
from pathlib import Path
import subprocess
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/pydeps"))
sys.path.insert(0, str(ROOT / "tools"))

from run_aelita_2g_wpa2_runtime_psk_once import (  # noqa: E402
    ROUTER_KNOWN_HOSTS,
    oracle_ps,
    parse_powershell_json,
    refresh_router_known_hosts,
    validate_oracle_target,
)


ACK = "OPENMITRASTAR_AELITA_2G_WPA2_RUNTIME_PSK"
OUT_BASE = ROOT / "outputs/f3-certification/realtek-2g-aelita/20260824-throughput-probe"
ROUTER_KEY = (
    ROOT / ".codex_tmp/openmitrastar_ramssh_client_ed25519"
    if (ROOT / ".codex_tmp/openmitrastar_ramssh_client_ed25519").is_file()
    else Path.home() / ".ssh/id_ed25519"
)


def redact_sensitive_text(value: str) -> str:
    value = re.sub(r"(?i)\b(?:[0-9a-f]{2}:){5}[0-9a-f]{2}\b", "[mac-redacted]", value)
    return re.sub(
        r"(?i)\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b",
        "[guid-redacted]",
        value,
    )


def sanitize_client_evidence(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: sanitize_client_evidence(item)
            for key, item in value.items()
            if key.lower() not in {"bssid", "ap_bssid", "guid", "direcci_n", "raw"}
        }
    if isinstance(value, list):
        return [sanitize_client_evidence(item) for item in value]
    if isinstance(value, str):
        return redact_sensitive_text(value)
    return value


ROUTER_SAMPLE_COMMAND = r"""
echo SECTION_UNAME
uname -r
echo SECTION_UPTIME
cat /proc/uptime
echo SECTION_NETDEV
cat /proc/net/dev
echo SECTION_INTERRUPTS
cat /proc/interrupts
echo SECTION_WIRELESS
cat /proc/net/wireless 2>/dev/null || true
echo SECTION_STATION
iw dev wlan0 station dump 2>/dev/null || true
echo SECTION_HOSTAPD_STATUS
hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null || hostapd_cli -i wlan0 status 2>/dev/null || true
echo SECTION_HOSTAPD
hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 all_sta 2>/dev/null || hostapd_cli -i wlan0 all_sta 2>/dev/null || true
echo SECTION_ARP
arp -n 2>/dev/null || true
ip neigh show 2>/dev/null || true
echo SECTION_BRIDGE
brctl show 2>/dev/null || true
brctl showmacs br0 2>/dev/null || true
bridge fdb show br br0 2>/dev/null || true
echo SECTION_ROUTE
ip route show 2>/dev/null || route -n 2>/dev/null || true
echo SECTION_LINK
ip -s link show dev wlan0 2>/dev/null || true
echo SECTION_QDISC
tc -s qdisc show dev wlan0 2>/dev/null || true
echo SECTION_TQE_READONLY
cat /sys/class/net/tqe/dbg 2>/dev/null || true
echo SECTION_EMAC_STATS
cat /sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats 2>/dev/null || true
echo SECTION_CPU
head -n 1 /proc/stat
echo SECTION_MEMORY
grep -E '^(MemAvailable|MemFree):' /proc/meminfo
echo SECTION_PS
iw dev wlan0 get power_save 2>/dev/null || true
echo SECTION_PARAMS
for f in /sys/module/rtl8192ee/parameters/hgw500_* /sys/module/rtl_pci/parameters/*; do
  [ -f "$f" ] || continue
  printf '%s=' "$f"
  cat "$f"
done
echo SECTION_DMESG_TAIL
dmesg | tail -n 120 | grep -E 'OMRTL|OMRTLEAPOL|rtl|wlan0|TX|q1|BE|DOK|RP|WP|sta|auth|assoc' || true
echo SECTION_DONE
"""


def run_router_sample(host: str, user: str, key_path: Path, timeout: int = 12) -> dict[str, Any]:
    started = time.time()
    ROUTER_KNOWN_HOSTS.parent.mkdir(parents=True, exist_ok=True)
    refresh_router_known_hosts(host)
    keys: list[Path] = []
    for candidate in (key_path, Path.home() / ".ssh/id_ed25519"):
        if candidate.is_file() and str(candidate) not in {str(k) for k in keys}:
            keys.append(candidate)
    if not keys:
        return {
            "local_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
            "duration_s": round(time.time() - started, 3),
            "rc": 255,
            "stdout": "",
            "stderr": f"missing router SSH key: {key_path}",
        }
    out = ""
    err = ""
    rc = 255
    for key in keys:
        args = [
            "ssh",
            "-i",
            str(key),
            "-o",
            "IdentitiesOnly=yes",
            "-o",
            "BatchMode=yes",
            "-o",
            f"ConnectTimeout={min(max(timeout, 1), 8)}",
            "-o",
            "StrictHostKeyChecking=accept-new",
            "-o",
            f"UserKnownHostsFile={ROUTER_KNOWN_HOSTS}",
            "-o",
            "HostKeyAlgorithms=+ssh-rsa",
            "-o",
            "PubkeyAcceptedAlgorithms=+ssh-rsa",
            "-o",
            "LogLevel=ERROR",
            f"{user}@{host}",
            ROUTER_SAMPLE_COMMAND,
        ]
        try:
            proc = subprocess.run(
                args,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout,
                check=False,
            )
            out = redact_sensitive_text(proc.stdout or "")
            err = redact_sensitive_text(proc.stderr or "")
            rc = proc.returncode
        except subprocess.TimeoutExpired as exc:
            out = redact_sensitive_text(exc.stdout or "")
            err = redact_sensitive_text(exc.stderr or "")
            rc = 124
        if rc == 0 or "Permission denied (publickey)" not in err:
            break
    return {
        "local_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(started)),
        "duration_s": round(time.time() - started, 3),
        "rc": rc,
        "stdout": out,
        "stderr": err,
    }


def parse_netdev(text: str) -> dict[str, dict[str, int]]:
    parsed: dict[str, dict[str, int]] = {}
    for line in text.splitlines():
        if ":" not in line:
            continue
        iface, raw = line.split(":", 1)
        iface = iface.strip()
        if iface not in {"wlan0", "br0", "eth0"}:
            continue
        parts = raw.split()
        if len(parts) < 16:
            continue
        nums = [int(x) for x in parts[:16]]
        parsed[iface] = {
            "rx_bytes": nums[0],
            "rx_packets": nums[1],
            "rx_errs": nums[2],
            "rx_drop": nums[3],
            "tx_bytes": nums[8],
            "tx_packets": nums[9],
            "tx_errs": nums[10],
            "tx_drop": nums[11],
        }
    return parsed


def parse_irq28(text: str) -> int | None:
    match = re.search(r"(?m)^\s*28:\s+(\d+)\s+.*rtl_pci", text)
    if not match:
        return None
    return int(match.group(1))


def extract_section(text: str, name: str) -> str:
    capture = False
    lines: list[str] = []
    start = f"SECTION_{name}"
    for line in text.splitlines():
        if line == start:
            capture = True
            continue
        if capture and line.startswith("SECTION_"):
            break
        if capture:
            lines.append(line)
    return "\n".join(lines).strip()


def parse_station_rates(text: str) -> dict[str, str]:
    station_text = extract_section(text, "STATION")
    hostapd_text = extract_section(text, "HOSTAPD")
    status_text = extract_section(text, "HOSTAPD_STATUS")
    combined = "\n".join(part for part in (station_text, hostapd_text, status_text) if part)
    rates: dict[str, str] = {}
    if station_text:
        mac = re.search(r"(?mi)^Station\s+([0-9a-f:]{17})\b", station_text)
        if mac:
            rates["station_present"] = "1"
    for key in ("rx bitrate", "tx bitrate", "signal", "tx retries", "tx failed"):
        match = re.search(rf"(?mi)^\s*{re.escape(key)}:\s*(.+?)\s*$", station_text)
        if match:
            rates[key.replace(" ", "_")] = match.group(1).strip()
    for key in ("rx_packets", "tx_packets", "rx_bytes", "tx_bytes", "inactive_msec"):
        match = re.search(rf"(?mi)^{re.escape(key)}=(.+?)\s*$", hostapd_text)
        if match:
            rates[f"hostapd_{key}"] = match.group(1).strip()
    for key in ("state", "num_sta[0]", "channel", "ieee80211n"):
        match = re.search(rf"(?mi)^{re.escape(key)}=(.+?)\s*$", status_text)
        if match:
            rates[f"hostapd_{key.replace('[0]', '')}"] = match.group(1).strip()
    if combined:
        rates["raw_line_count"] = str(len(combined.splitlines()))
    return rates


def parse_qdisc(text: str) -> list[str]:
    capture = False
    lines: list[str] = []
    for line in text.splitlines():
        if line == "SECTION_QDISC":
            capture = True
            continue
        if capture and line.startswith("SECTION_"):
            break
        if capture and line.strip():
            lines.append(line.strip())
    return lines[:12]


def parse_key_values(text: str, section: str) -> dict[str, int | str]:
    result: dict[str, int | str] = {}
    for line in extract_section(text, section).splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        try:
            result[key.strip()] = int(value, 0)
        except ValueError:
            result[key.strip()] = value
    return result


def classify_station_rate(station: dict[str, str] | None) -> dict[str, Any]:
    if not station:
        return {
            "state": "missing",
            "reason": "no station/rate fields captured",
        }
    tx = station.get("tx_bitrate") or ""
    match = re.search(r"([0-9.]+)\s+MBit/s", tx)
    if not match:
        return {
            "state": "unknown",
            "reason": "tx_bitrate not parseable",
            "tx_bitrate": tx,
        }
    mbps = float(match.group(1))
    if mbps < 12:
        state = "low_phy_rate"
    elif mbps < 30:
        state = "mid_phy_rate"
    else:
        state = "ht_phy_rate"
    return {
        "state": state,
        "tx_bitrate": tx,
        "tx_phy_mbps": mbps,
        "rx_bitrate": station.get("rx_bitrate"),
        "signal": station.get("signal"),
    }


def parse_int_field(value: Any) -> int | None:
    if value is None:
        return None
    match = re.search(r"-?\d+", str(value))
    if not match:
        return None
    return int(match.group(0))


def evaluate_router_health(
    parsed_samples: list[dict[str, Any]],
    deltas: dict[str, dict[str, int]],
    irq_delta: int | None,
) -> dict[str, Any]:
    station_samples = [
        sample.get("station") or {}
        for sample in parsed_samples
        if (sample.get("station") or {}).get("station_present")
        or (parse_int_field((sample.get("station") or {}).get("hostapd_num_sta")) or 0) > 0
    ]
    station = station_samples[-1] if station_samples else {}
    rate = classify_station_rate(station)
    wlan = deltas.get("wlan0") or {}
    hostapd_sta = parse_int_field(station.get("hostapd_num_sta"))
    tx_failed = parse_int_field(station.get("tx_failed"))
    checks = {
        "sample_count": len(parsed_samples) >= 2,
        "station_present": bool(station.get("station_present") or (hostapd_sta is not None and hostapd_sta > 0)),
        "hostapd_enabled": station.get("hostapd_state") == "ENABLED",
        "hostapd_sta_present": hostapd_sta is not None and hostapd_sta > 0,
        "ieee80211n_enabled": station.get("hostapd_ieee80211n") == "1",
        "ht_or_mid_phy_rate": rate.get("state") in {"mid_phy_rate", "ht_phy_rate"},
        "irq28_progress": irq_delta is not None and irq_delta > 0,
        "wlan0_rx_progress": wlan.get("rx_packets", 0) > 0 and wlan.get("rx_bytes", 0) > 0,
        "wlan0_tx_progress": wlan.get("tx_packets", 0) > 0 and wlan.get("tx_bytes", 0) > 0,
        "wlan0_no_new_errors": all(wlan.get(key, 0) <= 0 for key in ("rx_errs", "tx_errs")),
        "wlan0_no_new_drops": all(wlan.get(key, 0) <= 0 for key in ("rx_drop", "tx_drop")),
        "station_no_tx_failed": tx_failed in (None, 0),
    }
    failed = [name for name, ok in checks.items() if not ok]
    return {
        "schema": "openmitrastar.aelita-2g-router-health-gate/v1",
        "pass": not failed,
        "failed": failed,
        "checks": checks,
        "last_station_rate_class": rate,
        "wlan0_delta": wlan,
        "irq28_delta": irq_delta,
    }


def summarize(samples: list[dict[str, Any]], result_payload: dict[str, Any] | None) -> dict[str, Any]:
    parsed_samples = []
    for sample in samples:
        text = sample.get("stdout", "")
        parsed_samples.append(
            {
                "local_time": sample.get("local_time"),
                "netdev": parse_netdev(text),
                "irq28": parse_irq28(text),
                "station": parse_station_rates(text),
                "qdisc": parse_qdisc(text),
                "emac_stats": parse_key_values(text, "EMAC_STATS"),
                "memory": extract_section(text, "MEMORY"),
                "cpu": extract_section(text, "CPU"),
                "rc": sample.get("rc"),
            }
        )

    first = parsed_samples[0] if parsed_samples else {}
    last = parsed_samples[-1] if parsed_samples else {}
    netdev_samples = [sample for sample in parsed_samples if sample.get("netdev")]
    netdev_first = netdev_samples[0] if netdev_samples else {}
    netdev_last = netdev_samples[-1] if netdev_samples else {}
    station_samples = [
        sample for sample in parsed_samples
        if (sample.get("station") or {}).get("station_present")
        or (parse_int_field((sample.get("station") or {}).get("hostapd_num_sta")) or 0) > 0
    ]
    station_first = station_samples[0] if station_samples else first
    station_last = station_samples[-1] if station_samples else last
    deltas: dict[str, dict[str, int]] = {}
    for iface, end in netdev_last.get("netdev", {}).items():
        start = netdev_first.get("netdev", {}).get(iface, {})
        deltas[iface] = {k: end.get(k, 0) - start.get(k, 0) for k in end}

    irq_samples = [sample.get("irq28") for sample in parsed_samples if sample.get("irq28") is not None]
    irq_start = irq_samples[0] if irq_samples else None
    irq_end = irq_samples[-1] if irq_samples else None
    controller_download = None
    controller_upload = None
    traffic_direction = "download"
    execution_error = None
    if result_payload:
        test_payload = result_payload.get("test", {})
        controller_download = test_payload.get("controller_download")
        controller_upload = test_payload.get("controller_upload")
        traffic_direction = test_payload.get("traffic_direction") or traffic_direction
        execution_error = result_payload.get("execution_error")

    irq_delta = None if irq_start is None or irq_end is None else irq_end - irq_start
    router_health = evaluate_router_health(parsed_samples, deltas, irq_delta)
    emac_first = first.get("emac_stats", {})
    emac_last = last.get("emac_stats", {})
    emac_delta = {
        key: value - emac_first.get(key, 0)
        for key, value in emac_last.items()
        if isinstance(value, int) and isinstance(emac_first.get(key, 0), int)
    }

    return {
        "schema": "openmitrastar.aelita-2g-throughput-router-probe-summary/v1",
        "sample_count": len(samples),
        "first_time": first.get("local_time"),
        "last_time": last.get("local_time"),
        "netdev_delta": deltas,
        "irq28_delta": irq_delta,
        "emac_stats_first": emac_first,
        "emac_stats_last": emac_last,
        "emac_stats_delta": emac_delta,
        "first_station": station_first.get("station"),
        "last_station": station_last.get("station"),
        "last_station_rate_class": classify_station_rate(station_last.get("station")),
        "router_health_gate": router_health,
        "traffic_direction": traffic_direction,
        "controller_download": controller_download,
        "controller_upload": controller_upload,
        "execution_error": execution_error,
    }


def extract_result_path(stdout_text: str) -> Path | None:
    match = re.search(r"OM2G_WPA2_AELITA_RESULT_LOCAL=(.+)", stdout_text)
    if not match:
        return None
    raw = match.group(1).strip()
    path = Path(raw)
    if not path.is_absolute():
        path = ROOT / path
    return path


def recover_latest_aelita_result(host: str, user: str, started_epoch: float) -> tuple[dict[str, Any], str] | None:
    cutoff_epoch = int(started_epoch) - 120
    command = rf'''
$root = 'C:\ProgramData\OpenMitraStar\oracle'
$cutoff = [DateTimeOffset]::FromUnixTimeSeconds({cutoff_epoch}).UtcDateTime
$file = Get-ChildItem -LiteralPath $root -Filter '2g-wpa2-result-*.json' -ErrorAction SilentlyContinue |
    Where-Object {{ $_.LastWriteTimeUtc -ge $cutoff }} |
    Sort-Object LastWriteTimeUtc -Descending |
    Select-Object -First 1
if ($file) {{
    $bytes = [IO.File]::ReadAllBytes($file.FullName)
    [ordered]@{{
        exists = $true
        path = $file.FullName
        last_write_utc = $file.LastWriteTimeUtc.ToString('o')
        payload_b64 = [Convert]::ToBase64String($bytes)
    }} | ConvertTo-Json -Depth 4
}} else {{
    [ordered]@{{ exists = $false }} | ConvertTo-Json -Depth 2
}}
'''
    raw = oracle_ps(host, user, command, timeout=30)
    wrapper = parse_powershell_json(raw)
    if wrapper.get("exists") is not True:
        return None
    payload = base64.b64decode(str(wrapper.get("payload_b64", ""))).decode("utf-8-sig")
    return json.loads(payload), str(wrapper.get("path", ""))


def fetch_aelita_result(host: str, user: str, result_path: str) -> dict[str, Any] | None:
    command = rf'''
$path = {json.dumps(result_path)}
if (Test-Path -LiteralPath $path) {{
    $bytes = [IO.File]::ReadAllBytes($path)
    [ordered]@{{ exists = $true; payload_b64 = [Convert]::ToBase64String($bytes) }} | ConvertTo-Json -Depth 4
}} else {{
    [ordered]@{{ exists = $false }} | ConvertTo-Json -Depth 2
}}
'''
    raw = oracle_ps(host, user, command, timeout=30)
    wrapper = parse_powershell_json(raw)
    if wrapper.get("exists") is not True:
        return None
    payload = base64.b64decode(str(wrapper.get("payload_b64", ""))).decode("utf-8-sig")
    return json.loads(payload)


def result_passed(payload: dict[str, Any] | None) -> bool:
    if not payload:
        return False
    test = payload.get("test", {})
    restore = payload.get("restore", {})
    direction = test.get("traffic_direction") or "download"
    download = test.get("controller_download")
    upload = test.get("controller_upload")
    download_ok = True
    upload_ok = True
    if isinstance(download, dict):
        download_ok = download.get("pass") is True
    if isinstance(upload, dict):
        upload_ok = upload.get("pass") is True
    if direction in {"download", "both"} and not isinstance(download, dict):
        download_ok = False
    if direction in {"upload", "both"} and not isinstance(upload, dict):
        upload_ok = False
    return (
        test.get("connected") is True
        and test.get("router_ping", {}).get("pass") is True
        and restore.get("connected") is True
        and download_ok
        and upload_ok
    )


def should_use_latest_result_fallback(remote_result_path: str | None) -> bool:
    return not remote_result_path or str(remote_result_path).startswith("recovery-error:")


def probe_exit_code(
    summary: dict[str, Any],
    result_payload: dict[str, Any] | None,
    child_rc: int,
    controller_url: str,
    traffic_direction: str,
) -> int:
    if not result_passed(result_payload):
        return child_rc if child_rc != 0 else 1
    router_health = summary.get("router_health_gate")
    if not isinstance(router_health, dict) or router_health.get("pass") is not True:
        return 3
    if controller_url:
        download = summary.get("controller_download")
        upload = summary.get("controller_upload")
        if traffic_direction in {"download", "both"} and (
            not isinstance(download, dict) or download.get("pass") is not True
        ):
            return 2
        if traffic_direction in {"upload", "both"} and (
            not isinstance(upload, dict) or upload.get("pass") is not True
        ):
            return 2
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--router-host", default="192.168.1.90")
    parser.add_argument("--router-user", default="root")
    parser.add_argument("--router-key", type=Path, default=ROUTER_KEY)
    parser.add_argument("--router-known-hosts", type=Path, default=ROUTER_KNOWN_HOSTS)
    parser.add_argument("--oracle-host", default="192.168.1.63")
    parser.add_argument("--oracle-user", default="AELITA")
    parser.add_argument("--controller-url", default="http://192.168.1.43:8008/speed.bin")
    parser.add_argument("--traffic-direction", choices=("download", "upload", "both"), default="download")
    parser.add_argument("--interval", type=float, default=3.0)
    parser.add_argument("--wait-result", type=int, default=240)
    parser.add_argument("--child-timeout", type=int, default=150)
    parser.add_argument("--recovery-window", type=int, default=90)
    parser.add_argument("--restore-watchdog-minutes", type=int, default=5)
    parser.add_argument("--soak-seconds", type=int, default=10)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    if args.router_host != "192.168.1.90":
        raise SystemExit("this helper is pinned to the local OpenMitraStar router")
    validate_oracle_target(args.oracle_host, args.oracle_user)
    if not args.router_key.exists():
        raise SystemExit(f"missing router key: {args.router_key}")
    if not 30 <= args.child_timeout <= 600:
        raise SystemExit("--child-timeout must be 30..600")
    if not 0 <= args.recovery_window <= 300:
        raise SystemExit("--recovery-window must be 0..300")

    stamp = time.strftime("%Y%m%dT%H%M%SZ")
    out_dir = args.output_dir or (OUT_BASE / stamp)
    out_dir.mkdir(parents=True, exist_ok=True)
    samples_path = out_dir / "router-samples.jsonl"
    child_stdout_path = out_dir / "aelita-speed.stdout.log"
    child_stderr_path = out_dir / "aelita-speed.stderr.log"
    summary_path = out_dir / "summary.json"

    cmd = [
        sys.executable,
        str(ROOT / "tools/run_aelita_2g_wpa2_runtime_psk_once.py"),
        "--execute",
        "--ack",
        ACK,
        "--router-host",
        args.router_host,
        "--router-key",
        str(args.router_key),
        "--router-known-hosts",
        str(args.router_known_hosts),
        "--oracle-host",
        args.oracle_host,
        "--oracle-user",
        args.oracle_user,
        "--test-ssid",
        "OpenMitraStar-Lab",
        "--wifi-interface",
        "Wi-Fi",
        "--controller-url",
        args.controller_url,
        "--traffic-direction",
        args.traffic_direction,
        "--restore-watchdog-minutes",
        str(args.restore_watchdog_minutes),
        "--soak-seconds",
        str(args.soak_seconds),
    ]

    samples: list[dict[str, Any]] = []
    started_epoch = time.time()
    result_payload = None
    remote_recovered_path = None
    recovered = False
    result_path = None
    timed_out = False
    timeout_error = None
    try:
        proc = subprocess.run(
            cmd,
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=args.child_timeout,
            check=False,
        )
        stdout_text = proc.stdout or ""
        stderr_text = proc.stderr or ""
        rc = proc.returncode
    except subprocess.TimeoutExpired as exc:
        timed_out = True
        timeout_error = f"child-timeout-after-{args.child_timeout}s"
        stdout_text = exc.stdout or ""
        stderr_text = exc.stderr or ""
        rc = 124
    try:
        try:
            started = parse_powershell_json(stdout_text)
            if isinstance(started.get("result"), str):
                remote_recovered_path = started["result"]
        except Exception:
            remote_recovered_path = None
        deadline = time.monotonic() + args.wait_result + args.recovery_window
        next_result_check = time.monotonic()
        with samples_path.open("w", encoding="utf-8") as fh:
            while time.monotonic() < deadline:
                try:
                    sample = run_router_sample(args.router_host, args.router_user, args.router_key)
                except Exception as exc:
                    sample = {
                        "local_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                        "duration_s": 0,
                        "rc": -1,
                        "stdout": "",
                        "stderr": repr(exc),
                    }
                samples.append(sample)
                fh.write(json.dumps(sample, sort_keys=True) + "\n")
                fh.flush()
                if time.monotonic() >= next_result_check:
                    try:
                        if remote_recovered_path:
                            result_payload = fetch_aelita_result(
                                args.oracle_host,
                                args.oracle_user,
                                remote_recovered_path,
                            )
                        if result_payload is None and should_use_latest_result_fallback(remote_recovered_path):
                            recovered_result = recover_latest_aelita_result(
                                args.oracle_host,
                                args.oracle_user,
                                started_epoch,
                            )
                            if recovered_result:
                                result_payload, remote_recovered_path = recovered_result
                        if result_payload is not None:
                            recovered = True
                            break
                    except Exception:
                        pass
                    next_result_check = time.monotonic() + 5
                time.sleep(args.interval)
    except Exception:
        raise

    child_stdout_path.write_text(stdout_text, encoding="utf-8")
    child_stderr_path.write_text(stderr_text, encoding="utf-8")

    local_stdout_result_path = extract_result_path(stdout_text)
    if local_stdout_result_path and local_stdout_result_path.exists():
        result_path = local_stdout_result_path
        result_payload = json.loads(result_path.read_text(encoding="utf-8-sig"))
    elif result_payload is not None:
        local_recovered = out_dir / "aelita-result-recovered.json"
        local_recovered.write_text(
            json.dumps(sanitize_client_evidence(result_payload), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        result_path = local_recovered
    else:
        try:
            recovered_result = recover_latest_aelita_result(args.oracle_host, args.oracle_user, started_epoch)
        except Exception as exc:
            recovered_result = None
            remote_recovered_path = f"recovery-error: {exc}"
        if recovered_result:
            result_payload, remote_recovered_path = recovered_result
            recovered = True
            local_recovered = out_dir / "aelita-result-recovered.json"
            local_recovered.write_text(
                json.dumps(sanitize_client_evidence(result_payload), indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            result_path = local_recovered

    summary = summarize(samples, result_payload)
    effective_rc = 0 if result_passed(result_payload) else rc
    effective_probe_rc = probe_exit_code(
        summary,
        result_payload,
        rc,
        args.controller_url,
        args.traffic_direction,
    )
    summary.update(
        {
            "output_dir": str(out_dir),
            "aelita_result_path": str(result_path) if result_path else None,
            "aelita_result_recovered": recovered,
            "aelita_result_remote_path": remote_recovered_path,
            "aelita_rc": rc,
            "effective_aelita_rc": effective_rc,
            "effective_probe_rc": effective_probe_rc,
            "timed_out": timed_out,
            "timeout_error": timeout_error,
            "flash": False,
            "reboot": False,
            "router_mutations": False,
        }
    )
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print(f"OM2G_THROUGHPUT_ROUTER_PROBE_SUMMARY={summary_path}")
    return effective_probe_rc


if __name__ == "__main__":
    raise SystemExit(main())
