#!/usr/bin/env python3
"""One-command RAM-only 5 GHz pipeline: cold boot through WPA2 AP."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ACK = "OPENMITRASTAR_QTN_W3_FINAL_5G_RAM_ONLY"
RELEASE = "5.10.260-openmitrastar-radiohw"
ART = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-hbm-watchdog-safe-20260820"
MODULE_ROOT = ART / f"rootfs/lib/modules/{RELEASE}/extra/quantenna"
PSK = ROOT / "work/mission-state/.openmitrastar-lab.psk"


def run(command: list[str], timeout: int = 900) -> None:
    completed = subprocess.run(
        command, cwd=ROOT, text=True, timeout=timeout,
    )
    if completed.returncode:
        raise SystemExit(completed.returncode)


def ssh(command: str, timeout: int = 60) -> None:
    run(
        [sys.executable, "tools/ramssh_exec.py", command,
         "--host", "192.168.1.200", "--timeout", str(timeout)],
        timeout + 30,
    )


def upload(source: Path, destination: str, mode: str = "0600") -> None:
    tool = (
        "tools/ramssh_upload_chunked.py"
        if source.stat().st_size > 256 * 1024
        else "tools/ramssh_upload.py"
    )
    command = [sys.executable, tool, str(source), destination,
               "--host", "192.168.1.200", "--mode", mode]
    if tool.endswith("chunked.py"):
        command.extend(["--chunk-bytes", "16384", "--retries", "5"])
    run(command, 180)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--port", default="COM3")
    args = parser.parse_args()
    if not args.execute:
        print({"mode": "dry-run", "scope": "cold-boot-to-wpa2-5g",
               "artifact": str(ART), "rf_open_count": 1,
               "flash": False})
        print("W3_FINAL_5G_PIPELINE_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")

    run([
        sys.executable, "tools/run_qtn_w3_switch_emac_handoff.py",
        "--hbm-reclaim", "--execute", "--ack",
        "OPENMITRASTAR_QTN_W3_SWITCH_EMAC_HANDOFF_RAM_ONLY",
        "--host", "192.168.1.200", "--server-ip", "192.168.1.43",
        "--port", args.port, "--rollback-seconds", "75",
        "--timeout", "900", "--autoboot-wait-seconds", "300",
        "--wait-for-cold-power-cycle",
    ], 1100)
    run([
        sys.executable, "tools/run_qtn_w3_qdrv_hostlink_core.py",
        "--hbm-reclaim", "--execute", "--ack",
        "OPENMITRASTAR_QTN_W3_QDRV_HOSTLINK_CORE_RAM_ONLY",
        "--host", "192.168.1.200", "--port", args.port,
    ], 500)

    upload(ROOT / "tools/qtn_w3_qdrv_hostlink_vap_once_remote.sh",
           "/tmp/w3-qdrv-hostlink-vap.sh", "0700")
    ssh(
        "sed -i 's/\\r$//' /tmp/w3-qdrv-hostlink-vap.sh; "
        "sh /tmp/w3-qdrv-hostlink-vap.sh "
        "OPENMITRASTAR_QTN_W3_HOSTLINK_VAP_ONCE_RAM_ONLY",
        60,
    )

    for name in ("wlan_scan_ap", "wlan_ccmp", "wlan_xauth"):
        upload(MODULE_ROOT / f"wlan/{name}.ko", f"/tmp/{name}.ko")
    upload(ROOT / "outputs/kernel-port/qtn-wireless-tools-v4-noatomic-20260820/iwconfig",
           "/tmp/iwconfig-v4", "0700")
    upload(ROOT / "outputs/kernel-port/qtn-wireless-tools-v4-noatomic-20260820/iwpriv",
           "/tmp/iwpriv-v4", "0700")
    ssh(
        "insmod /tmp/wlan_scan_ap.ko; insmod /tmp/wlan_ccmp.ko; "
        "insmod /tmp/wlan_xauth.ko; "
        "rm -f /tmp/wlan_scan_ap.ko /tmp/wlan_ccmp.ko /tmp/wlan_xauth.ko "
        "/tmp/w3-switch-emac/*.ko /tmp/w3-qdrv-hostlink-core/*.ko "
        "/tmp/w3-qdrv-hostlink-core/firmware/* "
        "/tmp/w3-qdrv-hostlink-core/regulatory/* "
        "/tmp/w3-qdrv-hostlink-core/power_tables/* "
        "/tmp/hostapd-qtn-v4.part; "
        "echo W3_FINAL_5G_TMP_RECLAIM_PASS=1",
        90,
    )
    upload(ROOT / "outputs/kernel-port/qtn-hostapd-madwifi-v4-20260820/hostapd",
           "/tmp/hostapd-qtn-v4", "0700")
    upload(ROOT / "outputs/kernel-port/qtn-hostapd-madwifi-v4-20260820/hostapd_cli",
           "/tmp/hostapd-cli-qtn-v4", "0700")
    ssh(
        "/tmp/iwpriv-v4 wifi0 region 21317; "
        "/tmp/iwpriv-v4 wifi0 mode 11ac80Edge+; "
        "/tmp/iwconfig-v4 wifi0 essid OpenMitraStar-5G; "
        "/tmp/iwconfig-v4 wifi0 channel 36; "
        "test \"$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)\" = 0",
        90,
    )
    run([
        sys.executable, "tools/run_qtn_w3_native_madwifi_ap.py",
        "--execute", "--ack",
        "OPENMITRASTAR_QTN_W3_NATIVE_MADWIFI_AP_RAM_ONLY",
        "--psk-file", str(PSK), "--port", args.port,
    ], 240)
    print("W3_FINAL_5G_PIPELINE_PASS=1 ssid=OpenMitraStar-5G flash=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
