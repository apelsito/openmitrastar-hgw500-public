#!/usr/bin/env python3
"""Capture a bounded, read-only state snapshot from the physical HGW."""
from __future__ import annotations

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import re
import socket
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def sections(text: str) -> dict[str, str]:
    result: dict[str, list[str]] = {}
    current = ""
    for line in text.splitlines():
        match = re.fullmatch(r"---([a-z0-9_-]+)---", line.strip())
        if match:
            current = match.group(1)
            result[current] = []
        elif current:
            result[current].append(line)
    return {key: "\n".join(value).strip() for key, value in result.items()}


def parse_release(text: str) -> dict[str, str]:
    return dict(line.split("=", 1) for line in text.splitlines() if "=" in line)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--key", type=Path, default=Path.home() / ".ssh/id_ed25519")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = (args.output_dir or ROOT / "outputs/current-state" / f"hgw500-{stamp}").resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not tcp_open(args.host, 22):
        raise SystemExit("router SSH port is not reachable")
    ssh = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/OpenSSH/ssh.exe"
    remote = r'''printf '%s\n' '---release---'; cat /etc/openmitrastar/release
printf '%s\n' '---kernel---'; uname -r
printf '%s\n' '---uptime---'; cut -d' ' -f1 /proc/uptime
printf '%s\n' '---memory---'; grep -E '^(MemTotal|MemAvailable):' /proc/meminfo
printf '%s\n' '---boot_state---'; cat /run/openmitrastar/boot-state 2>/dev/null || true
printf '%s\n' '---degraded---'; cat /run/openmitrastar/degraded 2>/dev/null || true
printf '%s\n' '---radio2---'; /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null | grep -E '^(state|ssid|channel|num_sta)=' || true
printf '%s\n' '---radio5---'; cat /run/openmitrastar/radio5g/state 2>/dev/null || true
printf '%s\n' '---mtd---'; cat /proc/mtd
printf '%s\n' '---emac---'; cat /sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats 2>/dev/null || true
printf '%s\n' '---fatal_count---'; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV' || true'''
    proc = subprocess.run(
        [
            str(ssh), "-i", str(args.key.resolve()), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
            f"root@{args.host}", remote,
        ],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr.strip() or f"SSH failed rc={proc.returncode}")
    parsed = sections(proc.stdout)
    release = parse_release(parsed.get("release", ""))
    memory = parse_release(parsed.get("memory", "").replace(":", "="))
    radio2 = parse_release(parsed.get("radio2", ""))
    degraded = [line.split()[0] for line in parsed.get("degraded", "").splitlines() if line.strip()]
    result = {
        "schema": "openmitrastar.current-state/v1",
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "target": "HGW-500BNA-QCv2 A2",
        "host": args.host,
        "read_only": True,
        "firmware": release.get("OPENMITRASTAR_PRODUCT_VERSION", "unknown"),
        "build_id": release.get("OPENMITRASTAR_BUILD_ID", "unknown"),
        "kernel": parsed.get("kernel", "unknown"),
        "uptime_seconds": float(parsed.get("uptime", "0") or 0),
        "memory": {key.strip(): value.strip() for key, value in memory.items()},
        "boot_state": parsed.get("boot_state", "unknown"),
        "degraded_services": degraded,
        "radio2": {"state": radio2.get("state", "unknown"), "channel": radio2.get("channel", "unknown"), "stations": radio2.get("num_sta", "unknown")},
        "radio5_state": parsed.get("radio5", "unknown"),
        "mtd": parsed.get("mtd", ""),
        "emac": parse_release(parsed.get("emac", "")),
        "fatal_count": int(parsed.get("fatal_count", "0") or 0),
        "hardware_actions": {"uart": False, "reboot": False, "flash": False, "radio_mutation": False},
    }
    (out / "raw.txt").write_text(proc.stdout, encoding="utf-8")
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps({"status": "PASS", "output": str(out), "firmware": result["firmware"], "boot_state": result["boot_state"], "radio2": result["radio2"]["state"], "radio5": result["radio5_state"], "fatal_count": result["fatal_count"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
