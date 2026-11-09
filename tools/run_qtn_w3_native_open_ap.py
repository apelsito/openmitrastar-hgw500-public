#!/usr/bin/env python3
"""Run the RAM-only open Quantenna 5 GHz AP gate."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "tools/qtn_w3_native_madwifi_open_ap.sh"
ROLLBACK = ROOT / "tools/qtn_w3_native_ap_rollback.sh"
ACK = "OPENMITRASTAR_QTN_W3_NATIVE_OPEN_AP_RAM_ONLY"


def run(command: list[str], timeout: int = 120, check: bool = True):
    return subprocess.run(
        command, cwd=ROOT, text=True, capture_output=True,
        timeout=timeout, check=check,
    )


def ssh(command: str, timeout: int = 30, check: bool = True):
    return run(
        [sys.executable, "tools/ramssh_exec.py", command,
         "--host", "192.168.1.200", "--timeout", str(timeout)],
        timeout=timeout + 20, check=check,
    )


def upload(source: Path, destination: str, mode: str) -> None:
    result = run(
        [sys.executable, "tools/ramssh_upload.py", str(source), destination,
         "--host", "192.168.1.200", "--mode", mode],
        timeout=60,
    )
    print(result.stdout, end="")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--rollback-seconds", type=int, default=120)
    parser.add_argument("--defer-commit", action="store_true")
    parser.add_argument("--external-uart-capture", action="store_true")
    args = parser.parse_args()
    if not 120 <= args.rollback_seconds <= 900:
        raise SystemExit("--rollback-seconds must be 120..900")
    if not args.execute:
        print({
            "mode": "dry-run", "scope": "native-open-5g-ap",
            "ssid": "OpenMitraStar-5G", "region": "ES",
            "channel": 36, "bandwidth_mhz": 80,
            "security": "OPEN", "flash": False,
            "rollback_seconds": args.rollback_seconds,
            "defer_commit": args.defer_commit,
        })
        print("W3_QTN_NATIVE_OPEN_AP_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")

    def target_ssh(command: str, timeout: int = 30, check: bool = True):
        return run(
            [sys.executable, "tools/ramssh_exec.py", command,
             "--host", args.host, "--timeout", str(timeout)],
            timeout=timeout + 20, check=check,
        )

    def target_upload(source: Path, destination: str, mode: str) -> None:
        result = run(
            [sys.executable, "tools/ramssh_upload.py", str(source), destination,
             "--host", args.host, "--mode", mode], timeout=60,
        )
        print(result.stdout, end="")

    target_ssh("mkdir -p /tmp/qtn-native-open-ap; chmod 0700 /tmp/qtn-native-open-ap")
    target_upload(START, "/tmp/qtn-native-madwifi-open-ap.sh", "0700")
    target_upload(ROLLBACK, "/tmp/qtn-native-ap-rollback.sh", "0700")

    uart_dir = ROOT / "outputs/uart-live" / (
        "w3-qtn-native-open-ap-" + time.strftime("%Y%m%d-%H%M%S")
    )
    capture = None
    if not args.external_uart_capture:
        capture = subprocess.Popen(
            ["pwsh.exe", "-NoProfile", "-File", "tools/capture_topaz_uart.ps1",
             "-Port", args.port, "-Seconds", str(args.rollback_seconds + 30),
             "-OutputDirectory", str(uart_dir)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
    try:
        time.sleep(2)
        result = target_ssh(
            "sed -i 's/\\r$//' /tmp/qtn-native-madwifi-open-ap.sh "
            "/tmp/qtn-native-ap-rollback.sh; "
            f"sh /tmp/qtn-native-madwifi-open-ap.sh {ACK} "
            f"{args.rollback_seconds} {'deferred' if args.defer_commit else 'auto'}",
            timeout=90, check=False,
        )
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        marker = "W3_QTN_NATIVE_OPEN_AP_EXPERIMENT_PASS=1"
        if result.returncode != 0 or marker not in result.stdout:
            raise RuntimeError(f"native open AP failed rc={result.returncode} uart={uart_dir}")

        for index in range(1, 4):
            if index > 1:
                time.sleep(5)
            probe = target_ssh(
                "test \"$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)\" = 1; "
                "(test -e /sys/class/net/br0/brif/eth1_emac1 || "
                " (test -e /sys/class/net/br0/brif/eth0 && "
                "  dmesg | grep -Fq 'OMEMACSW stage=symbols-only-ready target=mitrastar,hgw-500bna-qcv2')); "
                "test -e /sys/class/net/br0/brif/wifi0; "
                "test -s /tmp/qtn-native-open-ap/hostapd.pid; "
                "kill -0 $(cat /tmp/qtn-native-open-ap/hostapd.pid); "
                "test \"$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))\" -eq 65; "
                "/tmp/hostapd-cli-qtn-v4 -p /var/run/hostapd -i wifi0 ping; "
                "/tmp/hostapd-cli-qtn-v4 -p /var/run/hostapd -i wifi0 get_config; "
                f"echo W3_QTN_NATIVE_OPEN_SSH_SOAK_PASS index={index}",
                timeout=20,
            )
            print(probe.stdout, end="")
        time.sleep(3)
    finally:
        if capture is not None and capture.poll() is None:
            capture.terminate()
            try:
                capture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture.kill()

    print(
        f"W3_QTN_NATIVE_OPEN_AP_PASS=1 uart={uart_dir} flash=0 "
        f"rollback_pending={1 if args.defer_commit else 0}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
