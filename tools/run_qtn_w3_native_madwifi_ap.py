#!/usr/bin/env python3
"""Run the RAM-only native madwifi 5 GHz AP gate with UART and rollback."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
START = ROOT / "tools/qtn_w3_native_madwifi_ap.sh"
ROLLBACK = ROOT / "tools/qtn_w3_native_ap_rollback.sh"
ACK = "OPENMITRASTAR_QTN_W3_NATIVE_MADWIFI_AP_RAM_ONLY"


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


def verify_psk(path: Path) -> None:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) != 1 or not re.fullmatch(r"[ -~]{8,63}", lines[0]):
        raise SystemExit("PSK must be one printable ASCII line of 8..63 characters")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--psk-file", type=Path)
    parser.add_argument("--port", default="COM3")
    args = parser.parse_args()
    if not args.execute:
        print("W3_QTN_NATIVE_MADWIFI_AP_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK or args.psk_file is None:
        raise SystemExit(f"require --ack {ACK} and --psk-file")
    verify_psk(args.psk_file)

    ssh(
        "mkdir -p /tmp/qtn-native-ap; chmod 0700 /tmp/qtn-native-ap; "
        "rm -f /tmp/qtn-native-ap/wpa2.psk"
    )
    upload(START, "/tmp/qtn-native-madwifi-ap.sh", "0700")
    upload(ROLLBACK, "/tmp/qtn-native-ap-rollback.sh", "0700")
    upload(args.psk_file, "/tmp/qtn-native-ap/wpa2.psk", "0600")

    uart_dir = ROOT / "outputs/uart-live" / (
        "w3-qtn-native-ap-" + time.strftime("%Y%m%d-%H%M%S")
    )
    capture = subprocess.Popen(
        ["pwsh.exe", "-NoProfile", "-File", "tools/capture_topaz_uart.ps1",
         "-Port", args.port, "-Seconds", "180",
         "-OutputDirectory", str(uart_dir)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(2)
        result = ssh(
            "sed -i 's/\\r$//' /tmp/qtn-native-madwifi-ap.sh "
            "/tmp/qtn-native-ap-rollback.sh; "
            f"sh /tmp/qtn-native-madwifi-ap.sh {ACK} "
            "/tmp/qtn-native-ap/wpa2.psk",
            timeout=90, check=False,
        )
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        if result.returncode != 0 or "W3_QTN_NATIVE_MADWIFI_AP_EXPERIMENT_PASS=1" not in result.stdout:
            raise RuntimeError(f"native AP failed rc={result.returncode} uart={uart_dir}")

        for index in range(1, 4):
            if index > 1:
                time.sleep(5)
            probe = ssh(
                "test \"$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)\" = 1; "
                "test -e /sys/class/net/br0/brif/eth1_emac1; "
                "test -e /sys/class/net/br0/brif/wifi0; "
                "test -s /tmp/qtn-native-ap/hostapd.pid; "
                "kill -0 $(cat /tmp/qtn-native-ap/hostapd.pid); "
                "test \"$(( $(cat /sys/class/net/wifi0/flags) & 0x41 ))\" -eq 65; "
                "/tmp/hostapd-cli-qtn-v4 -p /var/run/hostapd -i wifi0 ping; "
                "/tmp/hostapd-cli-qtn-v4 -p /var/run/hostapd -i wifi0 get_config; "
                f"echo W3_QTN_NATIVE_SSH_SOAK_PASS index={index}",
                timeout=20,
            )
            print(probe.stdout, end="")
        time.sleep(3)
    finally:
        if capture.poll() is None:
            capture.terminate()
            try:
                capture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture.kill()

    print(f"W3_QTN_NATIVE_MADWIFI_AP_PASS=1 uart={uart_dir} psk=redacted flash=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
