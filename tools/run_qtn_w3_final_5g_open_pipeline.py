#!/usr/bin/env python3
"""One-command cold RAM boot to an open Quantenna 5 GHz AP.

This pipeline is deliberately RAM-only.  It first boots the POSIX-timers
product image, then reuses the reviewed switch/HBM and qdrv-core gates before
starting the open channel-36/80-MHz/ES AP.
"""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
ACK = "OPENMITRASTAR_QTN_W3_FINAL_5G_OPEN_RAM_ONLY"
RELEASE = "5.10.260-openmitrastar-radiohw"
IMAGE = ROOT / "work/tftp/omvl/linux510-product-cgi-nowdt-diagnostic-v1-RAM-ONLY.bin"
IMAGE_SHA256 = "b63a31eaa5104e77a7af5bf07197bf30f58b2925ab07e2580487b94a967e8f53"
ART = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-rxalign-20260820"
MODULE_ROOT = ART / f"rootfs/lib/modules/{RELEASE}/extra/quantenna"
COLD_MARKER = ROOT / "work/mission-state/.hbm-cold-required"
HBM = MODULE_ROOT / "platform/topaz/hbm.ko"
QDRV = MODULE_ROOT / "qdrv/qdrv.ko"
HBM_SHA256 = "c5084d18167b20f250718c2e97ad94bf36f059543eb37d7372513352b3aa357b"
QDRV_SHA256 = "9ba6cd3ff63e23fb03fc8e8d5cd6e93f9d710e0d56a0693852f4227cf9dabb20"
PSK = ROOT / "work/mission-state/.openmitrastar-lab.psk"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run(command: list[str], timeout: int = 900, capture: bool = False):
    return subprocess.run(
        command, cwd=ROOT, text=True, timeout=timeout, check=True,
        capture_output=capture,
    )


def ssh(host: str, command: str, timeout: int = 60, check: bool = True):
    return subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", command,
         "--host", host, "--timeout", str(timeout)],
        cwd=ROOT, text=True, timeout=timeout + 30, check=check,
        capture_output=not check,
    )


def upload(host: str, source: Path, destination: str, mode: str = "0600") -> None:
    tool = (
        "tools/ramssh_upload_chunked.py"
        if source.stat().st_size > 256 * 1024
        else "tools/ramssh_upload.py"
    )
    command = [sys.executable, tool, str(source), destination,
               "--host", host, "--mode", mode]
    if tool.endswith("chunked.py"):
        command.extend(["--chunk-bytes", "16384", "--retries", "5"])
    run(command, 180)


def verify_inputs() -> None:
    expected = {
        IMAGE: IMAGE_SHA256,
        ROOT / "outputs/kernel-port/qtn-hostapd-madwifi-v4-20260820/hostapd":
            "338beaae1e3f3bc951b16d4bea1871d42d184170fc95f5efd200aa46e45dc269",
        ROOT / "outputs/kernel-port/qtn-hostapd-madwifi-v4-20260820/hostapd_cli":
            "67df5a9d7e6484101ac29f25c8f178cdea2bef51d4ea3f6fcdeeebb9eb033504",
        ROOT / "outputs/kernel-port/qtn-wireless-tools-v4-noatomic-20260820/iwconfig":
            "5ebc31cb2ca69a1fbe1e0882f4aadba248e131a3b153c1d86d210ba53890c18b",
        ROOT / "outputs/kernel-port/qtn-wireless-tools-v4-noatomic-20260820/iwpriv":
            "94c0d675a2d18fd0c259eb713e6a69d99fe6b2f73f2f838dc2fca2c2bf5f4edd",
        HBM: HBM_SHA256,
        QDRV: QDRV_SHA256,
    }
    for path, expected_hash in expected.items():
        if not path.is_file() or sha256(path) != expected_hash:
            raise SystemExit(f"pinned input mismatch: {path}")
    if not PSK.is_file():
        raise SystemExit("private 2.4 GHz PSK file missing")
    secret = PSK.read_bytes()
    if b"\n" not in secret or len(secret.rstrip(b"\r\n")) not in range(8, 64):
        raise SystemExit("private 2.4 GHz PSK must be one 8..63 byte line")


def cold_boot(port: str, server_ip: str, boot_host: str, timeout: int,
              reboot_current: bool) -> None:
    tftp = subprocess.Popen(
        [sys.executable, "tools/tftp_serve_once.py", "--root", str(IMAGE.parent),
         "--bind", "0.0.0.0", "--port", "69", "--timeout", str(timeout), "--once"],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        time.sleep(0.6)
        boot_command = [
            "pwsh.exe", "-NoProfile", "-File", "tools/reboot_boot_ramssh.ps1",
            "-Port", port, "-Filename", IMAGE.name, "-ServerIp", server_ip,
            "-ClientIp", boot_host, "-TimeoutSeconds", str(timeout),
            "-AutobootWaitSeconds", str(timeout - 300),
            "-EntropyPromptPattern", "(?s)OMPRODUCT_ENTR.{0,4096}OPY_SEED_REQUIRED",
            "-EntropyOkPattern", "OMPRODUCT_SERIAL_ENTROPY_OK bits=256",
            "-ReadyPattern", "OMPRODUCT_READY state=(ready|degraded)",
        ]
        if not reboot_current:
            boot_command.append("-SkipReboot")
        run(boot_command, timeout + 120)
    finally:
        if tftp.poll() is None:
            tftp.terminate()
            try:
                tftp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tftp.kill()

    # This local marker describes the previous warm state.  Clearing it is
    # valid only after the supervised cold boot above has reached READY.
    COLD_MARKER.unlink(missing_ok=True)
    ssh(
        boot_host,
        "test \"$(uname -r)\" = 5.10.260-openmitrastar-radiohw; "
        "test -e /sys/class/net/eth0; "
        "! dmesg | grep -Eq 'OMWDT stage=(armed|pet first=1)'; "
        "echo W3_NOWDT_DIAGNOSTIC_COLD_BOOT_PASS",
        30,
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--autoboot-wait-seconds", type=int, default=900)
    parser.add_argument("--reboot-current", action="store_true")
    parser.add_argument("--boot-host", default="192.168.1.200")
    parser.add_argument("--management-host", default="192.168.1.90")
    parser.add_argument("--soak-seconds", type=int, default=180)
    parser.add_argument("--association-wait-seconds", type=int, default=300)
    args = parser.parse_args()
    verify_inputs()
    if not args.execute:
        print({
            "mode": "dry-run", "image": str(IMAGE.relative_to(ROOT)),
            "image_sha256": IMAGE_SHA256, "ssid": "OpenMitraStar-5G",
            "region": "ES", "channel": 36, "bandwidth_mhz": 80,
            "security": "OPEN", "flash": False,
            "boot_host": args.boot_host,
            "management_host": args.management_host,
            "hbm_sha256": HBM_SHA256,
            "qdrv_sha256": QDRV_SHA256,
            "hbm_timer_reclaim": False,
            "hardware_watchdog": False,
            "radio2g_preserved": True,
            "skip_ioss_reset_pulse": True,
            "uart_reboot_on_switch_failure": False,
            "soak_seconds": args.soak_seconds,
            "association_required": True,
        })
        print("W3_FINAL_5G_OPEN_PIPELINE_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")
    if not 600 <= args.autoboot_wait_seconds <= 1800:
        raise SystemExit("--autoboot-wait-seconds must be 600..1800")
    if not 180 <= args.soak_seconds <= 600:
        raise SystemExit("--soak-seconds must be 180..600")
    if not 30 <= args.association_wait_seconds <= 600:
        raise SystemExit("--association-wait-seconds must be 30..600")
    rollback_seconds = args.association_wait_seconds + args.soak_seconds + 90
    if rollback_seconds > 900:
        raise SystemExit("association wait + soak exceeds local rollback ceiling")

    cold_boot(args.port, args.server_ip, args.boot_host,
              args.autoboot_wait_seconds + 300,
              args.reboot_current)
    run([
        "pwsh.exe", "-NoProfile", "-File", "tools/run_product_rootfs_secure_ap.ps1",
        "-ExecuteRam", "-AckRamOnly", "OPENMITRASTAR_PRODUCT_SECURE_AP_RAM_ONLY",
        "-PskFile", str(PSK), "-HostAddress", args.boot_host,
        "-TimeoutSeconds", "120",
    ], 180)
    run([
        sys.executable, "tools/run_qtn_w3_switch_emac_handoff.py",
        "--rx-align", "--use-current-no-watchdog-boot", "--execute", "--ack",
        "OPENMITRASTAR_QTN_W3_SWITCH_EMAC_HANDOFF_RAM_ONLY",
        "--host", args.boot_host, "--management-host", args.management_host,
        "--preserve-2g", "--server-ip", args.server_ip,
        "--skip-ioss-reset-pulse", "--no-uart-reboot-on-failure",
        "--port", args.port, "--rollback-seconds", "120", "--timeout", "900",
    ], 1050)
    run([
        sys.executable, "tools/run_qtn_w3_qdrv_hostlink_core.py",
        "--rx-align", "--no-hw-watchdog", "--execute", "--ack",
        "OPENMITRASTAR_QTN_W3_QDRV_HOSTLINK_CORE_RAM_ONLY",
        "--host", args.management_host, "--port", args.port,
    ], 500)

    upload(args.management_host,
           ROOT / "tools/qtn_w3_qdrv_hostlink_vap_once_remote.sh",
           "/tmp/w3-qdrv-hostlink-vap.sh", "0700")
    ssh(
        args.management_host,
        "sed -i 's/\\r$//' /tmp/w3-qdrv-hostlink-vap.sh; "
        "sh /tmp/w3-qdrv-hostlink-vap.sh "
        "OPENMITRASTAR_QTN_W3_HOSTLINK_VAP_ONCE_RAM_ONLY",
        60,
    )
    for name in ("wlan_scan_ap", "wlan_ccmp", "wlan_xauth"):
        upload(args.management_host, MODULE_ROOT / f"wlan/{name}.ko", f"/tmp/{name}.ko")
    upload(args.management_host,
           ROOT / "outputs/kernel-port/qtn-wireless-tools-v4-noatomic-20260820/iwconfig",
           "/tmp/iwconfig-v4", "0700")
    upload(args.management_host,
           ROOT / "outputs/kernel-port/qtn-wireless-tools-v4-noatomic-20260820/iwpriv",
           "/tmp/iwpriv-v4", "0700")
    ssh(
        args.management_host,
        "insmod /tmp/wlan_scan_ap.ko; insmod /tmp/wlan_ccmp.ko; "
        "insmod /tmp/wlan_xauth.ko; "
        "rm -f /tmp/wlan_scan_ap.ko /tmp/wlan_ccmp.ko /tmp/wlan_xauth.ko "
        "/tmp/w3-switch-emac/*.ko /tmp/w3-qdrv-hostlink-core/*.ko "
        "/tmp/w3-qdrv-hostlink-core/firmware/* "
        "/tmp/w3-qdrv-hostlink-core/regulatory/* "
        "/tmp/w3-qdrv-hostlink-core/power_tables/*; "
        "echo W3_FINAL_5G_OPEN_TMP_RECLAIM_PASS=1",
        90,
    )
    upload(args.management_host,
           ROOT / "outputs/kernel-port/qtn-hostapd-madwifi-v4-20260820/hostapd",
           "/tmp/hostapd-qtn-v4", "0700")
    upload(args.management_host,
           ROOT / "outputs/kernel-port/qtn-hostapd-madwifi-v4-20260820/hostapd_cli",
           "/tmp/hostapd-cli-qtn-v4", "0700")
    ssh(
        args.management_host,
        "/tmp/iwpriv-v4 wifi0 region 21317; "
        "/tmp/iwpriv-v4 wifi0 mode 11ac80Edge+; "
        "/tmp/iwconfig-v4 wifi0 essid OpenMitraStar-5G; "
        "/tmp/iwconfig-v4 wifi0 channel 36; "
        "test \"$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)\" = 0",
        90,
    )
    uart_dir = ROOT / "outputs/uart-live" / (
        "w3-final-5g-open-oem-parity-" + time.strftime("%Y%m%d-%H%M%S")
    )
    capture = subprocess.Popen(
        ["pwsh.exe", "-NoProfile", "-File", "tools/capture_topaz_uart.ps1",
         "-Port", args.port, "-Seconds", str(rollback_seconds + 30),
         "-OutputDirectory", str(uart_dir)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    committed = False
    try:
        time.sleep(2)
        run([
            sys.executable, "tools/run_qtn_w3_native_open_ap.py",
            "--execute", "--ack", "OPENMITRASTAR_QTN_W3_NATIVE_OPEN_AP_RAM_ONLY",
            "--host", args.management_host, "--port", args.port,
            "--rollback-seconds", str(rollback_seconds), "--defer-commit",
            "--external-uart-capture",
        ], 240)
        run([
            sys.executable, "tools/run_qtn_w3_native_open_soak.py",
            "--execute", "--ack",
            "OPENMITRASTAR_QTN_W3_NATIVE_OPEN_SOAK_READ_ONLY",
            "--host", args.management_host,
            "--seconds", str(args.soak_seconds),
            "--association-wait-seconds", str(args.association_wait_seconds),
        ], rollback_seconds)
        ssh(
            args.management_host,
            "root=/tmp/qtn-native-open-ap; touch $root/commit; chmod 0600 $root/commit; "
            "test -s $root/rollback.pid && kill $(cat $root/rollback.pid) 2>/dev/null || true; "
            "test -e /sys/class/net/br0/brif/wlan0; "
            "test -e /sys/class/net/br0/brif/wifi0; "
            "test \"$(cat /sys/module/hbm/parameters/w3_hbm_timer_reclaim_enable)\" = 0; "
            "echo W3_FINAL_5G_OPEN_LOCAL_ROLLBACK_COMMIT_PASS=1",
            30,
        )
        committed = True
    finally:
        if not committed:
            rollback = ssh(
                args.management_host,
                "sh /tmp/qtn-native-ap-rollback.sh /tmp/qtn-native-open-ap host-runner-failure",
                20, check=False,
            )
            if rollback.returncode:
                print(
                    "W3_FINAL_5G_OPEN_ROLLBACK_PENDING=1 "
                    f"deadline_seconds={rollback_seconds}", file=sys.stderr,
                )
        if capture.poll() is None:
            capture.terminate()
            try:
                capture.wait(timeout=5)
            except subprocess.TimeoutExpired:
                capture.kill()
    print(
        "W3_FINAL_5G_OPEN_PIPELINE_PASS=1 ssid=OpenMitraStar-5G "
        f"region=ES channel=36 bw=80 security=OPEN management={args.management_host} "
        f"soak_seconds={args.soak_seconds} association=PASS rx_tx_irq8=PASS "
        f"radio2g=preserved hbm_timer_reclaim=0 hw_watchdog=0 uart={uart_dir} flash=0 dfs=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
