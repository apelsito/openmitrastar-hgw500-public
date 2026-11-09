#!/usr/bin/env python3
"""Observe a real wifi0 client after the W3 AP control-plane gate.

Read-only on the target: waits for the autopilot marker, then samples qcsapi
association count and Linux wifi0 counters. It never changes RF, network
configuration, credentials, or flash.
"""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
CONTROL_PASS = "W3_QTN_5G_AUTOPILOT_AP_CONTROL_PLANE_PASS=1"

REMOTE_SAMPLE = r'''
root=/tmp/w3-qcsapi-5g-ap
runtime=$root/runtime
test -x "$runtime/bin/call_qcsapi" || exit 41
test -e /sys/class/net/wifi0 || exit 42
assoc=$(LD_LIBRARY_PATH="$runtime/lib" "$runtime/lib/ld-uClibc-0.9.29.so" \
  "$runtime/bin/call_qcsapi" get_count_associations wifi0 2>/dev/null) || exit 43
case "$assoc" in ''|*[!0-9]*) exit 44 ;; esac
for name in rx_bytes tx_bytes rx_packets tx_packets; do
  eval "$name=$(cat /sys/class/net/wifi0/statistics/$name 2>/dev/null)"
  eval value=\$$name
  case "$value" in ''|*[!0-9]*) exit 45 ;; esac
done
hostapd=0
test -s "$root/private/hostapd.pid" && kill -0 "$(cat "$root/private/hostapd.pid")" 2>/dev/null && hostapd=1
printf 'OM5GCLIENT assoc=%s rx_bytes=%s tx_bytes=%s rx_packets=%s tx_packets=%s hostapd=%s\n' \
  "$assoc" "$rx_bytes" "$tx_bytes" "$rx_packets" "$tx_packets" "$hostapd"
'''.strip()


def wait_control_plane(path: Path, timeout: int) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file() and CONTROL_PASS in path.read_text(encoding="utf-8", errors="replace"):
            return True
        time.sleep(2)
    return False


def sample(host: str, timeout: int = 15) -> dict[str, int] | None:
    result = subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", REMOTE_SAMPLE,
         "--host", host, "--timeout", str(timeout)],
        cwd=ROOT, text=True, capture_output=True, timeout=timeout + 15, check=False,
    )
    if result.returncode != 0:
        return None
    match = re.search(
        r"OM5GCLIENT assoc=(\d+) rx_bytes=(\d+) tx_bytes=(\d+) "
        r"rx_packets=(\d+) tx_packets=(\d+) hostapd=(\d+)",
        result.stdout,
    )
    if not match:
        return None
    keys = ("assoc", "rx_bytes", "tx_bytes", "rx_packets", "tx_packets", "hostapd")
    return dict(zip(keys, map(int, match.groups()), strict=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--autopilot-log", type=Path, required=True)
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--wait-control-seconds", type=int, default=7200)
    parser.add_argument("--observe-seconds", type=int, default=900)
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if not 30 <= args.wait_control_seconds <= 14400:
        raise SystemExit("--wait-control-seconds must be 30..14400")
    if not 30 <= args.observe_seconds <= 3600:
        raise SystemExit("--observe-seconds must be 30..3600")
    if not 2 <= args.interval_seconds <= 30:
        raise SystemExit("--interval-seconds must be 2..30")
    args.autopilot_log = args.autopilot_log.resolve()

    if args.dry_run:
        print(
            "W3_QTN_5G_CLIENT_MONITOR_DRY_RUN_PASS=1 read_only=1 "
            "association_required=1 bidirectional_counter_progress_required=1",
            flush=True,
        )
        return 0

    print("OM5GCLIENT state=waiting-control-plane", flush=True)
    if not wait_control_plane(args.autopilot_log, args.wait_control_seconds):
        print("W3_QTN_5G_CLIENT_MONITOR_FAIL=1 reason=control-plane-timeout", file=sys.stderr)
        return 1
    print("OM5GCLIENT state=control-plane-ready association=required", flush=True)

    deadline = time.monotonic() + args.observe_seconds
    baseline: dict[str, int] | None = None
    associated_samples = 0
    while time.monotonic() < deadline:
        current = sample(args.host)
        if current is None:
            print("OM5GCLIENT state=sample-failed", flush=True)
        else:
            print(
                "OM5GCLIENT " + " ".join(f"{key}={value}" for key, value in current.items()),
                flush=True,
            )
            if current["hostapd"] != 1:
                print("W3_QTN_5G_CLIENT_MONITOR_FAIL=1 reason=hostapd-dead", file=sys.stderr)
                return 1
            if current["assoc"] > 0:
                associated_samples += 1
                if baseline is None:
                    baseline = current
                elif (
                    associated_samples >= 3
                    and current["rx_bytes"] > baseline["rx_bytes"]
                    and current["tx_bytes"] > baseline["tx_bytes"]
                    and current["rx_packets"] > baseline["rx_packets"]
                    and current["tx_packets"] > baseline["tx_packets"]
                ):
                    print(
                        "W3_QTN_5G_CLIENT_ASSOCIATION_TRAFFIC_PASS=1 "
                        f"associations={current['assoc']} "
                        f"rx_bytes_delta={current['rx_bytes'] - baseline['rx_bytes']} "
                        f"tx_bytes_delta={current['tx_bytes'] - baseline['tx_bytes']} "
                        "internet_speedtest=UNVERIFIED F3=0",
                        flush=True,
                    )
                    return 0
            else:
                baseline = None
                associated_samples = 0
        time.sleep(args.interval_seconds)

    print("W3_QTN_5G_CLIENT_MONITOR_FAIL=1 reason=no-associated-bidirectional-traffic", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
