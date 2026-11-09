#!/usr/bin/env python3
"""Fail-closed RAM equivalence gate for the exact OpenMitraStar flash candidate.

The default mode is an offline preflight.  ``--execute`` observes an already
RAM-booted candidate; it never writes flash, changes U-Boot state, or carries a
Wi-Fi secret.  PASS requires continuous management plus an associated 2.4 GHz
client whose traffic exercises wlan0 and br0 for the whole soak.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import ipaddress
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = (
    ROOT
    / "work"
    / "mission-state"
    / "f2-flash-candidate"
    / "openmitrastar-linux510-product-webformat.bin"
)
DEFAULT_MANIFEST = DEFAULT_CANDIDATE.with_name("manifest.json")
DEFAULT_OUTPUT = DEFAULT_CANDIDATE.with_name("ram-equivalence.json")
RAM_BOOT_NAME = "linux510-product-minihttpd-posix-private-nowdt-v1-RAM-ONLY.bin"
EXPECTED_SHA256 = "f1c92ce0f15dbfa883fedf42ac92577a7f4b7979fe1efd010b4e8262022c6461"
EXPECTED_BYTES = 6_758_400
ACK = "OPENMITRASTAR_EXACT_RAM_EQUIVALENCE"

FATAL_RE = re.compile(
    r"Kernel panic|\bOops\b|BUG:|use-after-free|KASAN|nobody cared|"
    r"Unable to handle kernel|hard LOCKUP|soft lockup|watchdog.*reset|"
    r"descriptor.*error|DMA.*error|EV_TLB|MuC exception|forcing reboot",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strictly_increasing(values: list[int]) -> bool:
    return len(values) >= 2 and all(b > a for a, b in zip(values, values[1:]))


def nondecreasing(values: list[int]) -> bool:
    return len(values) >= 2 and all(b >= a for a, b in zip(values, values[1:]))


def parse_kv(text: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Z0-9_]+", key):
            parsed[key] = value.strip()
    return parsed


def integer_series(samples: list[dict[str, Any]], key: str) -> list[int]:
    values: list[int] = []
    for sample in samples:
        value = sample.get(key)
        if isinstance(value, int):
            values.append(value)
    return values


def evaluate_samples(
    samples: list[dict[str, Any]], duration_observed: float, duration_required: int
) -> tuple[dict[str, Any], list[str]]:
    keys_strict = (
        "uptime_s",
        "br0_rx_packets",
        "br0_tx_packets",
        "wlan0_rx_packets",
        "wlan0_tx_packets",
        "irq20",
        "irq28",
    )
    summary: dict[str, Any] = {
        "duration_required_s": duration_required,
        "duration_observed_s": round(duration_observed, 3),
        "sample_count": len(samples),
        "all_local_ping": bool(samples) and all(s.get("local_ping") is True for s in samples),
        "all_ssh_primary": bool(samples) and all(s.get("ssh_primary") is True for s in samples),
        "all_ssh_fresh": bool(samples) and all(s.get("ssh_fresh") is True for s in samples),
        "all_hostapd_enabled": bool(samples) and all(s.get("hostapd_enabled") == 1 for s in samples),
        "all_bridge_members": bool(samples)
        and all(s.get("bridge_eth0") == 1 and s.get("bridge_wlan0") == 1 for s in samples),
        "all_wifi_associated": bool(samples) and all(s.get("station_count", 0) >= 1 for s in samples),
        "all_wifi_client_ping": bool(samples) and all(s.get("wifi_client_ping") == 1 for s in samples),
        "all_boot_ready": bool(samples) and all(s.get("boot_ready") == 1 for s in samples),
        "all_minihttpd_alive": bool(samples) and all(s.get("minihttpd_alive") == 1 for s in samples),
        "all_cgi_executed": bool(samples) and all(s.get("cgi_executed") is True for s in samples),
        "all_zero_errors": bool(samples)
        and all(s.get("br0_rx_errors") == 0 and s.get("br0_tx_errors") == 0 for s in samples),
    }
    for key in keys_strict:
        series = integer_series(samples, key)
        summary[f"{key}_start"] = series[0] if series else None
        summary[f"{key}_end"] = series[-1] if series else None
        summary[f"{key}_strict_progress"] = strictly_increasing(series)
    for key in ("br0_rx_errors", "br0_tx_errors", "wlan0_rx_errors", "wlan0_tx_errors"):
        series = integer_series(samples, key)
        summary[f"{key}_nondecreasing"] = nondecreasing(series)
        summary[f"{key}_delta"] = series[-1] - series[0] if len(series) >= 2 else None

    checks = [
        (len(samples) >= 2, "insufficient_samples"),
        (duration_observed >= duration_required, "duration_short"),
        (summary["all_local_ping"], "management_icmp_failure"),
        (summary["all_ssh_primary"], "management_ssh_failure"),
        (summary["all_ssh_fresh"], "fresh_ssh_failure"),
        (summary["all_hostapd_enabled"], "hostapd_not_enabled"),
        (summary["all_bridge_members"], "bridge_membership_lost"),
        (summary["all_wifi_associated"], "wifi_client_not_associated"),
        (summary["all_wifi_client_ping"], "wifi_client_traffic_failure"),
        (summary["all_boot_ready"], "product_boot_not_ready"),
        (summary["all_minihttpd_alive"], "minihttpd_not_alive"),
        (summary["all_cgi_executed"], "cgi_not_executed"),
        (summary["all_zero_errors"], "bridge_errors_nonzero"),
    ]
    for key in keys_strict:
        checks.append((bool(summary[f"{key}_strict_progress"]), f"{key}_frozen"))
    for key in ("br0_rx_errors", "br0_tx_errors", "wlan0_rx_errors", "wlan0_tx_errors"):
        checks.append((summary[f"{key}_delta"] == 0, f"{key}_increased"))
    failures = [reason for passed, reason in checks if not passed]
    summary["fail_reasons"] = failures
    summary["pass"] = not failures
    return summary, failures


def run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def local_ping(host: str) -> bool:
    proc = run(["ping.exe", "-n", "2", "-w", "1000", host], timeout=8)
    return proc.returncode == 0


def ssh(host: str, command: str, timeout: int = 25) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            str(ROOT / "tools" / "ramssh_exec.py"),
            command,
            "--host",
            host,
            "--timeout",
            str(timeout),
        ],
        timeout=timeout + 15,
    )


def cgi_executes(host: str) -> bool:
    conn = http.client.HTTPConnection(host, 8080, timeout=5)
    try:
        conn.request("GET", "/index.cgi", headers={"Connection": "close"})
        response = conn.getresponse()
        body = response.read(128 * 1024).decode("utf-8", "replace")
        content_type = response.getheader("Content-Type", "")
        return (
            response.status == 200
            and "text/html" in content_type.lower()
            and "OpenMitraStar" in body
            and "#!/bin/ash" not in body
            and "OM_WEB_DISPATCHER" not in body
        )
    except OSError:
        return False
    finally:
        conn.close()


def remote_snapshot_command(wifi_client_ip: str) -> str:
    # Output is deliberately aggregate-only: no PSK, cookies, keys or station MACs.
    return f"""set -u
devstat() {{ awk -v dev="$1" '$1 == dev":" {{print $2, $3, $10, $11}}' /proc/net/dev; }}
irqsum() {{ awk -v irq="$1:" '$1 == irq {{s=0; for(i=2;i<=NF;i++){{if($i ~ /^[0-9]+$/) s+=$i; else break}}; print s; found=1}} END{{if(!found) print -1}}' /proc/interrupts; }}
set -- $(devstat br0); echo BR0_RX_PACKETS=${{1:--1}}; echo BR0_RX_ERRORS=${{2:--1}}; echo BR0_TX_PACKETS=${{3:--1}}; echo BR0_TX_ERRORS=${{4:--1}}
set -- $(devstat wlan0); echo WLAN0_RX_PACKETS=${{1:--1}}; echo WLAN0_RX_ERRORS=${{2:--1}}; echo WLAN0_TX_PACKETS=${{3:--1}}; echo WLAN0_TX_ERRORS=${{4:--1}}
echo UPTIME_S=$(cut -d. -f1 /proc/uptime)
echo IRQ20=$(irqsum 20)
echo IRQ28=$(irqsum 28)
test -e /sys/class/net/br0/brif/eth0 && echo BRIDGE_ETH0=1 || echo BRIDGE_ETH0=0
test -e /sys/class/net/br0/brif/wlan0 && echo BRIDGE_WLAN0=1 || echo BRIDGE_WLAN0=0
/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$' && echo HOSTAPD_ENABLED=1 || echo HOSTAPD_ENABLED=0
stations=$(/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 all_sta 2>/dev/null | grep -Ec '^[0-9a-fA-F]{{2}}(:[0-9a-fA-F]{{2}}){{5}}$' || true); echo STATION_COUNT=$stations
ping -c 3 -W 1 {wifi_client_ip} >/dev/null 2>&1 && echo WIFI_CLIENT_PING=1 || echo WIFI_CLIENT_PING=0
test "$(cat /run/openmitrastar/boot-state 2>/dev/null)" = ready && echo BOOT_READY=1 || echo BOOT_READY=0
pid=$(cat /run/openmitrastar/web/mini_httpd.pid 2>/dev/null || true); case "$pid" in ''|*[!0-9]*) echo MINIHTTPD_ALIVE=0;; *) kill -0 "$pid" 2>/dev/null && echo MINIHTTPD_ALIVE=1 || echo MINIHTTPD_ALIVE=0;; esac
"""


def collect_sample(host: str, wifi_client_ip: str, elapsed: float) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "elapsed_s": round(elapsed, 3),
        "local_ping": local_ping(host),
        "ssh_primary": False,
        "ssh_fresh": False,
        "cgi_executed": False,
    }
    primary = ssh(host, remote_snapshot_command(wifi_client_ip))
    sample["ssh_primary"] = primary.returncode == 0
    if primary.returncode == 0:
        values = parse_kv(primary.stdout)
        mapping = {
            "UPTIME_S": "uptime_s",
            "IRQ20": "irq20",
            "IRQ28": "irq28",
            "BR0_RX_PACKETS": "br0_rx_packets",
            "BR0_RX_ERRORS": "br0_rx_errors",
            "BR0_TX_PACKETS": "br0_tx_packets",
            "BR0_TX_ERRORS": "br0_tx_errors",
            "WLAN0_RX_PACKETS": "wlan0_rx_packets",
            "WLAN0_RX_ERRORS": "wlan0_rx_errors",
            "WLAN0_TX_PACKETS": "wlan0_tx_packets",
            "WLAN0_TX_ERRORS": "wlan0_tx_errors",
            "BRIDGE_ETH0": "bridge_eth0",
            "BRIDGE_WLAN0": "bridge_wlan0",
            "HOSTAPD_ENABLED": "hostapd_enabled",
            "STATION_COUNT": "station_count",
            "WIFI_CLIENT_PING": "wifi_client_ping",
            "BOOT_READY": "boot_ready",
            "MINIHTTPD_ALIVE": "minihttpd_alive",
        }
        for source, target in mapping.items():
            try:
                sample[target] = int(values.get(source, "-1"))
            except ValueError:
                sample[target] = -1
    fresh = ssh(host, "true", timeout=10)
    sample["ssh_fresh"] = fresh.returncode == 0
    sample["cgi_executed"] = cgi_executes(host)
    return sample


def uart_gate(path: Path, candidate_name: str, candidate_bytes: int) -> tuple[bool, dict[str, Any]]:
    raw = path.read_bytes().replace(b"\x00", b"")
    text = raw.decode("utf-8", "replace")
    markers = {
        "candidate_tftp_name": candidate_name in text,
        "candidate_byte_count": f"Bytes transferred = {candidate_bytes}" in text,
        "linux_5_10": "Linux version 5.10.260-openmitrastar-radiohw" in text,
        "entropy_seeded": "OMPRODUCT_SERIAL_ENTROPY_OK bits=256" in text,
        "network_ready": "OMNETWORK_READY interface=eth0 ipv4=192.168.1.200" in text,
        "product_ready": "OMPRODUCT_READY state=ready schema=1" in text,
        "bootbase_recovery": "topaz>" in text and "TFTP from server" in text,
        "fatal_absent": FATAL_RE.search(text) is None,
    }
    return all(markers.values()), markers


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    parser.add_argument("--uart-log", type=Path)
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--wifi-client-ip")
    parser.add_argument("--duration", type=int, default=600)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    args = parser.parse_args()

    candidate = args.candidate.resolve()
    manifest_path = args.manifest.resolve()
    if not candidate.is_file() or not manifest_path.is_file():
        raise SystemExit("candidate or manifest missing")
    candidate_sha = sha256(candidate)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    static_checks = {
        "candidate_sha256": candidate_sha == args.expected_sha256 == EXPECTED_SHA256,
        "candidate_size": candidate.stat().st_size == EXPECTED_BYTES,
        "manifest_candidate": manifest.get("artifact", {}).get("sha256") == candidate_sha,
        "manifest_target": manifest.get("target", {})
        == {"hardware_revision": "A2", "model": "HGW-500BNA-QCv2", "slot": "linux_live"},
        "manifest_candidate_eligible": manifest.get("candidate_eligible") is True,
        "manifest_not_flash_ready": manifest.get("flash_ready") is False,
    }
    plan = {
        "schema": "openmitrastar.ram-equivalence-runner/v1",
        "mode": "EXECUTE_RAM_OBSERVATION" if args.execute else "DRY_RUN",
        "candidate": relative(candidate),
        "candidate_sha256": candidate_sha,
        "duration_s": args.duration,
        "interval_s": args.interval,
        "requires_wifi_client_ip": True,
        "checks": [
            "exact candidate boot attested by UART",
            "two fresh key-only SSH operations per sample",
            "hostapd ENABLED and station associated for every sample",
            "eth0+wlan0 remain bridge members",
            "router-to-Wi-Fi-client ping every sample",
            "strict br0/wlan0 RX+TX and IRQ20/IRQ28 progress",
            "mini_httpd alive and index.cgi executed, never served as source",
            "no fatal UART/dmesg markers",
            "Bootbase/TFTP recovery observed",
        ],
        "static_checks": static_checks,
        "flash_actions": False,
        "secrets_logged": False,
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    if not all(static_checks.values()):
        print("OM_RAM_EQUIVALENCE_STATIC_FAIL", file=sys.stderr)
        return 2
    if not args.execute:
        print("OM_RAM_EQUIVALENCE_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"--execute requires --ack {ACK}")
    if args.duration < 600 or args.interval < 5 or args.interval > 30:
        raise SystemExit("execute mode requires duration>=600 and 5<=interval<=30")
    if not args.uart_log or not args.uart_log.is_file():
        raise SystemExit("execute mode requires --uart-log from this exact RAM boot")
    if not args.wifi_client_ip:
        raise SystemExit("execute mode requires --wifi-client-ip for real 2.4 GHz traffic")
    ipaddress.ip_address(args.wifi_client_ip)

    uart_ok, uart_markers = uart_gate(args.uart_log, RAM_BOOT_NAME, EXPECTED_BYTES)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = (
        args.evidence_dir.resolve()
        if args.evidence_dir
        else (ROOT / "work" / "mission-state" / "f2-flash-candidate" / f"ram-equivalence-{stamp}")
    )
    evidence_dir.mkdir(parents=True, exist_ok=False)
    samples_path = evidence_dir / "samples.jsonl"
    summary_path = evidence_dir / "summary.json"
    dmesg_path = evidence_dir / "dmesg-final.log"
    uart_attestation_path = evidence_dir / "uart-attestation.json"
    write_json(uart_attestation_path, {"path": relative(args.uart_log), "markers": uart_markers, "pass": uart_ok})

    before = ssh(args.host, "dmesg", timeout=30)
    if before.returncode != 0:
        raise SystemExit("cannot capture initial dmesg over key-only SSH")
    start = time.monotonic()
    samples: list[dict[str, Any]] = []
    while True:
        elapsed = time.monotonic() - start
        sample = collect_sample(args.host, args.wifi_client_ip, elapsed)
        samples.append(sample)
        with samples_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, sort_keys=True) + "\n")
        print(
            "OM_RAM_EQ_SAMPLE "
            f"n={len(samples)} t={sample['elapsed_s']} ping={int(bool(sample.get('local_ping')))} "
            f"ssh={int(bool(sample.get('ssh_primary')))}+{int(bool(sample.get('ssh_fresh')))} "
            f"ap={sample.get('hostapd_enabled', -1)} sta={sample.get('station_count', -1)} "
            f"br={sample.get('bridge_eth0', -1)}+{sample.get('bridge_wlan0', -1)}",
            flush=True,
        )
        remaining = args.duration - (time.monotonic() - start)
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))
    duration_observed = time.monotonic() - start

    after = ssh(args.host, "dmesg", timeout=30)
    dmesg = after.stdout if after.returncode == 0 else "DMESG_FETCH_FAILED\n"
    dmesg_path.write_text(dmesg, encoding="utf-8")
    before_text = before.stdout
    delta = dmesg[len(before_text) :] if dmesg.startswith(before_text) else dmesg
    summary, failures = evaluate_samples(samples, duration_observed, args.duration)
    summary["uart_gate"] = uart_ok
    summary["fatal_dmesg_delta"] = bool(FATAL_RE.search(delta))
    if not uart_ok:
        failures.append("exact_candidate_uart_attestation_failed")
    if after.returncode != 0:
        failures.append("final_dmesg_fetch_failed")
    if summary["fatal_dmesg_delta"]:
        failures.append("fatal_dmesg_marker")
    summary["fail_reasons"] = sorted(set(failures))
    summary["pass"] = not summary["fail_reasons"]
    write_json(summary_path, summary)

    evidence = [
        {"path": relative(path), "sha256": sha256(path)}
        for path in (samples_path, summary_path, dmesg_path, uart_attestation_path)
    ]
    checks = {
        "boot": "PASS" if uart_ok else "FAIL",
        "product_rootfs": "PASS" if summary.get("all_boot_ready") and summary.get("all_minihttpd_alive") else "FAIL",
        "ethernet": "PASS" if summary.get("all_local_ping") and summary.get("irq20_strict_progress") else "FAIL",
        "ssh_key_only": "PASS" if summary.get("all_ssh_primary") and summary.get("all_ssh_fresh") else "FAIL",
        "no_fatal_exception": "PASS" if not summary.get("fatal_dmesg_delta") and uart_markers.get("fatal_absent") else "FAIL",
        "reboot_or_recovery": "PASS" if uart_markers.get("bootbase_recovery") else "FAIL",
        "radio2g": "PASS" if summary.get("all_hostapd_enabled") and summary.get("all_wifi_associated") else "FAIL",
        "bridge": "PASS" if summary.get("all_bridge_members") else "FAIL",
        "management_stability": "PASS" if summary.get("pass") else "FAIL",
        "cgi_execution": "PASS" if summary.get("all_cgi_executed") else "FAIL",
    }
    result = {
        "schema": "openmitrastar.ram-equivalence/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "candidate_sha256": candidate_sha,
        "status": "PASS" if summary["pass"] else "FAIL",
        "checks": checks,
        "evidence": evidence,
        "summary": summary,
        "hardware_actions": "read-only runtime observation",
        "flash_actions": False,
        "secret_values_recorded": False,
    }
    write_json(args.output.resolve(), result)
    print(
        f"OM_RAM_EQUIVALENCE_{result['status']} output={relative(args.output.resolve())} "
        f"failures={','.join(summary['fail_reasons']) or 'none'}"
    )
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
