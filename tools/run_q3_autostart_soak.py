#!/usr/bin/env python3
"""Read-only stability soak for an already booted Q3 dual-radio candidate."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LINE = re.compile(
    r"OMQ3SOAK pong=(\d+) state=(\d+) rf=(\d+) carrier=(\d+) led=(\d+) "
    r"assoc=(\d+) wifi_rx=(\d+) wifi_tx=(\d+) eth_rx=(\d+) eth_tx=(\d+) "
    r"irq8=(\d+) irq20=(\d+) bridge=(\d+) radio2=(\d+) fatal=(\d+)"
)


def sample(host: str) -> dict[str, int]:
    remote = r'''
set -u
cli=/usr/sbin/hostapd-cli-qtn
pong=0; "$cli" -p /var/run/hostapd -i wifi0 ping 2>/dev/null | grep -qx PONG && pong=1
state=0; [ "$(cat /run/openmitrastar/radio5g/state 2>/dev/null)" = ready ] && state=1
rf=$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable 2>/dev/null || echo 0)
carrier=$(cat /sys/class/net/wifi0/carrier 2>/dev/null || echo 0)
led=$(cat /sys/class/leds/openmitrastar:green:wlan5g/brightness 2>/dev/null || echo 0)
assoc=$("$cli" -p /var/run/hostapd -i wifi0 all_sta 2>/dev/null | grep -Ec '^[0-9a-fA-F]{2}(:[0-9a-fA-F]{2}){5}$' || true)
wifi_rx=$(cat /sys/class/net/wifi0/statistics/rx_packets 2>/dev/null || echo 0)
wifi_tx=$(cat /sys/class/net/wifi0/statistics/tx_packets 2>/dev/null || echo 0)
eth_rx=$(cat /sys/class/net/eth0/statistics/rx_packets 2>/dev/null || echo 0)
eth_tx=$(cat /sys/class/net/eth0/statistics/tx_packets 2>/dev/null || echo 0)
irq8=$(sed -n 's/^ *8: *\([0-9]*\).*/\1/p' /proc/interrupts)
irq20=$(sed -n 's/^ *20: *\([0-9]*\).*/\1/p' /proc/interrupts)
bridge=0; [ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && [ -e /sys/class/net/br0/brif/wifi0 ] && bridge=1
radio2=0; /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$' && radio2=1
fatal=$(dmesg | grep -Eic 'Kernel panic|Oops:|BUG:|EV_TLB|MuC exception|MuC has halted|forcing reboot|run out of SRAM|No DDR heap memory|use-after-free' || true)
echo OMQ3SOAK pong=$pong state=$state rf=$rf carrier=$carrier led=$led assoc=$assoc wifi_rx=$wifi_rx wifi_tx=$wifi_tx eth_rx=$eth_rx eth_tx=$eth_tx irq8=$irq8 irq20=$irq20 bridge=$bridge radio2=$radio2 fatal=$fatal
'''.strip()
    proc = subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", remote, "--host", host, "--timeout", "20"],
        cwd=ROOT, text=True, capture_output=True, timeout=35, check=False,
    )
    match = LINE.search(proc.stdout)
    if proc.returncode or not match:
        raise RuntimeError(f"sample failed rc={proc.returncode}: {proc.stdout}{proc.stderr}")
    keys = ("pong", "state", "rf", "carrier", "led", "assoc", "wifi_rx", "wifi_tx",
            "eth_rx", "eth_tx", "irq8", "irq20", "bridge", "radio2", "fatal")
    return dict(zip(keys, map(int, match.groups()), strict=True))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    args = parser.parse_args()
    if not args.execute or args.ack != "OPENMITRASTAR_Q3_AUTOSTART_SOAK_READ_ONLY":
        print(json.dumps({"mode": "dry-run", "seconds": args.seconds, "interval": args.interval,
                          "flash": False, "writes_router": False}, sort_keys=True))
        return 0
    if not 180 <= args.seconds <= 900 or not 5 <= args.interval <= 30:
        raise SystemExit("invalid bounded soak duration/interval")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    outdir = ROOT / "work/mission-state/q3-persistent-composite" / f"autostart-soak-{stamp}"
    outdir.mkdir(parents=True, exist_ok=False)
    samples: list[dict[str, int]] = []
    started = time.monotonic()
    deadline = started + args.seconds
    while True:
        current = sample(args.host)
        current["elapsed_s"] = int(time.monotonic() - started)
        samples.append(current)
        print(
            f"OMQ3_SOAK n={len(samples)} t={current['elapsed_s']} pong={current['pong']} "
            f"assoc={current['assoc']} wifi_rx={current['wifi_rx']} wifi_tx={current['wifi_tx']} "
            f"irq8={current['irq8']} irq20={current['irq20']} fatal={current['fatal']}",
            flush=True,
        )
        if any(current[k] != 1 for k in ("pong", "state", "rf", "carrier", "bridge", "radio2")):
            break
        if current["led"] != 255 or current["fatal"] != 0 or time.monotonic() >= deadline:
            break
        time.sleep(min(args.interval, max(0, deadline - time.monotonic())))

    first, last = samples[0], samples[-1]
    stable = all(
        all(s[k] == 1 for k in ("pong", "state", "rf", "carrier", "bridge", "radio2"))
        and s["led"] == 255 and s["fatal"] == 0
        for s in samples
    )
    duration = time.monotonic() - started
    counters = {k: last[k] - first[k] for k in ("wifi_rx", "wifi_tx", "eth_rx", "eth_tx", "irq8", "irq20")}
    management_progress = counters["eth_rx"] > 0 and counters["eth_tx"] > 0 and counters["irq20"] > 0
    qtn_progress = counters["wifi_tx"] > 0 and counters["irq8"] > 0
    associated = max(s["assoc"] for s in samples) > 0
    client_data = associated and counters["wifi_rx"] > 0 and counters["wifi_tx"] > 0
    passed = stable and duration >= args.seconds and management_progress and qtn_progress
    report = {
        "schema": "openmitrastar.q3-autostart-soak/v1",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "candidate_sha256": "1f0c1bf5b29c77c3670be9891db9da6bb3d186f0fb931b8de711a5b5d89c6296",
        "duration_s": duration,
        "samples": len(samples),
        "stable": stable,
        "management_progress": management_progress,
        "qtn_progress": qtn_progress,
        "associated_client_observed": associated,
        "client_data_progress": client_data,
        "counter_deltas": counters,
        "status": "PASS_ASSOCIATED" if passed and client_data else ("PASS_ASSOCIATION_PENDING" if passed else "FAIL"),
        "flash_actions": False,
    }
    (outdir / "samples.json").write_text(json.dumps(samples, indent=2) + "\n", encoding="utf-8")
    (outdir / "summary.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"OMQ3_AUTOSTART_SOAK_{report['status']} report={outdir / 'summary.json'}", flush=True)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
