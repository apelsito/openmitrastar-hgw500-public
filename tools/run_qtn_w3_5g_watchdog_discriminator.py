#!/usr/bin/env python3
"""Observe an already-running RAM-only 5 GHz AP and classify a reset/loss.

The runner does not boot, flash, load modules, or alter RF configuration.  It
adds router-local telemetry, captures UART, and performs host-side management
probes long enough to cross both the 60 s HBM monitor period and the 120 s AP
rollback period.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
TELEMETRY = ROOT / "tools/qtn_w3_5g_watchdog_telemetry.sh"
ACK = "OPENMITRASTAR_QTN_W3_5G_WATCHDOG_DISCRIMINATOR_RAM_ONLY"


def run(command: list[str], timeout: int = 60, check: bool = False):
    return subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True,
        timeout=timeout, check=check,
    )


def ssh(command: str, host: str, timeout: int = 20):
    return run(
        [sys.executable, "tools/ramssh_exec.py", command,
         "--host", host, "--timeout", str(timeout)],
        timeout=timeout + 15,
    )


def upload(source: Path, destination: str, host: str, mode: str) -> None:
    result = run(
        [sys.executable, "tools/ramssh_upload.py", str(source), destination,
         "--host", host, "--mode", mode],
        timeout=60,
    )
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)


def newest_log(directory: Path) -> Path | None:
    logs = sorted(directory.glob("*.log"), key=lambda path: path.stat().st_mtime)
    return logs[-1] if logs else None


def classify(text: str, management_ok: int, management_fail: int) -> dict[str, object]:
    reset = bool(re.search(r"Bootbase|Autobooting|topaz>|U-Boot", text, re.I))
    enters = len(re.findall(r"OMHBM stage=timer-reclaim-enter", text))
    exits = len(re.findall(r"OMHBM stage=timer-reclaim-exit", text))
    skips = len(re.findall(r"OMHBM stage=timer-reclaim-skipped", text))
    samples = re.findall(
        r"OM5GSOAK sample=(\d+).*?irq8=(\d+).*?irq20=(\d+).*?"
        r"wifi_rx=([^ ]+).*?wifi_tx=([^ ]+).*?hostapd=([^ ]+)", text,
    )
    result = "INCONCLUSIVE"
    if reset and enters > exits:
        result = "HBM_TIMER_RECLAIM_IRQ_STARVATION"
    elif reset and skips:
        result = "RESET_WITH_TIMER_RECLAIM_DISABLED"
    elif management_fail and samples and not reset:
        result = "MANAGEMENT_PATH_LOSS_WITH_LINUX_ALIVE"
    elif not management_fail and samples:
        result = "SOAK_SURVIVED"
    return {
        "classification": result,
        "reset_seen": reset,
        "timer_reclaim_enters": enters,
        "timer_reclaim_exits": exits,
        "timer_reclaim_skips": skips,
        "uart_samples": len(samples),
        "management_ok": management_ok,
        "management_fail": management_fail,
        "first_sample": samples[0] if samples else None,
        "last_sample": samples[-1] if samples else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--interval", type=int, default=5)
    args = parser.parse_args()
    if args.seconds < 150 or args.seconds > 600:
        raise SystemExit("--seconds must be 150..600")
    if args.interval < 2 or args.interval > 15:
        raise SystemExit("--interval must be 2..15")
    if not args.execute:
        print(json.dumps({
            "mode": "dry-run", "flash": False, "boot": False,
            "module_load": False, "rf_change": False,
            "seconds": args.seconds, "interval": args.interval,
            "crosses_hbm_timer_seconds": 60,
            "crosses_ap_rollback_seconds": 120,
        }, sort_keys=True))
        print("W3_5G_WATCHDOG_DISCRIMINATOR_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")

    preflight = ssh(
        "test \"$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)\" = 1; "
        "test -e /sys/class/net/br0/brif/eth1_emac1; "
        "test -e /sys/class/net/br0/brif/wifi0; "
        "test \"$(cat /sys/module/hbm/parameters/w3_hbm_timer_reclaim_enable)\" = 0; "
        "/tmp/hostapd-cli-qtn-v4 -p /var/run/hostapd -i wifi0 ping | grep -qx PONG; "
        "echo W3_5G_WATCHDOG_PREFLIGHT_PASS=1",
        args.host,
    )
    if preflight.returncode or "PREFLIGHT_PASS=1" not in preflight.stdout:
        raise RuntimeError(preflight.stderr or preflight.stdout)

    upload(TELEMETRY, "/tmp/qtn-w3-5g-watchdog-telemetry.sh", args.host, "0700")
    samples = args.seconds // args.interval
    uart_dir = ROOT / "outputs/uart-live" / (
        "w3-5g-watchdog-discriminator-" + time.strftime("%Y%m%d-%H%M%S")
    )
    capture = subprocess.Popen(
        ["pwsh.exe", "-NoProfile", "-File", "tools/capture_topaz_uart.ps1",
         "-Port", args.port, "-Seconds", str(args.seconds + 20),
         "-OutputDirectory", str(uart_dir)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    management_ok = 0
    management_fail = 0
    try:
        time.sleep(2)
        started = ssh(
            "rm -rf /tmp/qtn-5g-watchdog-soak; "
            "sed -i 's/\\r$//' /tmp/qtn-w3-5g-watchdog-telemetry.sh; "
            f"nohup sh /tmp/qtn-w3-5g-watchdog-telemetry.sh {args.interval} {samples} "
            ">/tmp/qtn-5g-watchdog-telemetry.out 2>&1 & "
            "echo $! >/tmp/qtn-5g-watchdog-telemetry.pid; "
            "echo W3_5G_WATCHDOG_TELEMETRY_STARTED=1",
            args.host,
        )
        if started.returncode:
            raise RuntimeError(started.stderr or started.stdout)
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            probe = ssh(
                "test -e /sys/class/net/br0/brif/eth1_emac1; "
                "test -e /sys/class/net/br0/brif/wifi0; "
                "/tmp/hostapd-cli-qtn-v4 -p /var/run/hostapd -i wifi0 ping "
                "| grep -qx PONG; echo OMHOSTPROBE_PASS=1",
                args.host, timeout=max(5, args.interval),
            )
            if probe.returncode == 0 and "OMHOSTPROBE_PASS=1" in probe.stdout:
                management_ok += 1
            else:
                management_fail += 1
            time.sleep(args.interval)
    finally:
        if capture.poll() is None:
            capture.terminate()
            try:
                capture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture.kill()

    log = newest_log(uart_dir)
    text = log.read_text(errors="replace") if log else ""
    result = classify(text, management_ok, management_fail)
    result["uart_dir"] = str(uart_dir.relative_to(ROOT))
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"W3_5G_WATCHDOG_DISCRIMINATOR_RESULT={result['classification']}")
    return 0 if result["classification"] == "SOAK_SURVIVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())

