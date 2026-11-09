#!/usr/bin/env python3
"""Observe native Quantenna hostapd association and bidirectional traffic."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
MAC = re.compile(r"(?mi)^([0-9a-f]{2}(?::[0-9a-f]{2}){5})$")


def remote(timeout: int = 15) -> subprocess.CompletedProcess[str]:
    command = (
        "echo __RF__; cat /sys/module/qdrv/parameters/openmitrastar_rf_enable; "
        "echo __FLAGS__; cat /sys/class/net/wifi0/flags; "
        "echo __PING__; /tmp/hostapd-cli-qtn-v4 -p /var/run/hostapd -i wifi0 ping; "
        "echo __STA__; /tmp/hostapd-cli-qtn-v4 -p /var/run/hostapd -i wifi0 all_sta 2>&1 || true; "
        "echo __NET__; cat /proc/net/dev"
    )
    return subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", command, "--host",
         "192.168.1.200", "--timeout", str(timeout)],
        cwd=ROOT, text=True, capture_output=True, timeout=timeout + 20,
    )


def section(text: str, name: str, next_name: str | None) -> str:
    start = text.split(name + "\n", 1)[1]
    return start if next_name is None else start.split(next_name + "\n", 1)[0]


def counters(text: str, interface: str) -> tuple[int, int]:
    match = re.search(rf"(?m)^\s*{re.escape(interface)}:\s*(\d+)(?:\s+\d+){{7}}\s+(\d+)", text)
    if not match:
        raise ValueError(f"missing counters for {interface}")
    return int(match.group(1)), int(match.group(2))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    log = ROOT / "outputs/uart-live" / f"w3-native-5g-client-{stamp}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.seconds
    baseline: tuple[int, int] | None = None
    associated = False
    bidirectional = False
    samples = 0
    with log.open("w", encoding="utf-8") as handle:
        while time.monotonic() < deadline:
            result = remote()
            samples += 1
            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            if result.returncode != 0:
                line = f"{now} sample={samples} ssh=FAIL rc={result.returncode}\n"
            else:
                sta = section(result.stdout, "__STA__", "__NET__")
                net = section(result.stdout, "__NET__", None)
                rx, tx = counters(net, "wifi0")
                if baseline is None:
                    baseline = (rx, tx)
                clients = MAC.findall(sta)
                associated = associated or bool(clients)
                bidirectional = bidirectional or (
                    associated and rx > baseline[0] and tx > baseline[1]
                )
                line = (
                    f"{now} sample={samples} ssh=PASS rf="
                    f"{section(result.stdout, '__RF__', '__FLAGS__').strip()} "
                    f"flags={section(result.stdout, '__FLAGS__', '__PING__').strip()} "
                    f"ctrl={section(result.stdout, '__PING__', '__STA__').strip()} "
                    f"clients={len(clients)} wifi0_rx={rx} wifi0_tx={tx} "
                    f"bidirectional={int(bidirectional)}\n"
                )
            handle.write(line)
            handle.flush()
            print(line, end="", flush=True)
            if bidirectional:
                print(f"W3_NATIVE_5G_CLIENT_TRAFFIC_PASS=1 samples={samples} log={log}")
                return 0
            time.sleep(args.interval)
    print(
        f"W3_NATIVE_5G_CLIENT_TRAFFIC_PENDING=1 associated={int(associated)} "
        f"bidirectional={int(bidirectional)} samples={samples} log={log}"
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
