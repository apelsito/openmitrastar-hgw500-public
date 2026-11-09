#!/usr/bin/env python3
"""One-instance qdrv firmware/config/clearsram/start RAM experiment."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-qdrv-sequential-20260819"
PARENT_ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-qdrv-staged-20260819"
RELEASE = "5.10.260-openmitrastar-radiohw"
PRIVATE_MAC_SOURCE = ROOT / "work/secrets-backup/20260725-161724-text/mnt__jffs2__wifi_mac_addrs"
POWER_ROOT = ROOT / "work/hgw500-rootfs-live/squashfs-root/etc/power_tables"
POWER_TABLE = POWER_ROOT / "tx_power_QSR1000_es.txt"
POWER_CONF = POWER_ROOT / "power_table.conf"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QDRV_SEQUENTIAL_BRINGUP_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QDRV_SEQUENTIAL_BRINGUP_GATE.approved.env"
REMOTE = ROOT / "tools/qtn_w3_qdrv_sequential_bringup_remote.sh"
RAM_INSMOD = ROOT / "outputs/kernel-port/ram-insmod-nolibc/ram_insmod_nolibc"
ACK = "OPENMITRASTAR_QTN_W3_QDRV_SEQUENTIAL_RAM_ONLY"
MODULES = ("platform/ruby/gpio.ko", "platform/qtsens/temp_sensor.ko",
           "platform/topaz/temp_sens.ko", "wlan/wlan.ko", "qdrv/qdrv.ko")
FIRMWARE = (
    ("W3_MUCFW_SHA256", "rootfs/lib/firmware/qtn_driver.qtn_ruby.0.bin", "firmware/qtn_driver.qtn_ruby.0.bin"),
    ("W3_AUCFW_SHA256", "rootfs/lib/firmware/auc_driver.nomu.0.bin", "firmware/auc_driver.nomu.0.bin"),
    ("W3_DSPFW_SHA256", "rootfs/lib/firmware/rdsp_driver.0.bin", "firmware/rdsp_driver.0.bin"),
    ("W3_REGDB_SHA256", "rootfs/etc/qtn_regulatory_db.bin", "regulatory/qtn_regulatory_db.bin"),
)


def digest(path: Path, algorithm: str = "sha256") -> str:
    result = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def values(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#") and "=" in line)


def private_mac() -> str:
    if not PRIVATE_MAC_SOURCE.is_file() or PRIVATE_MAC_SOURCE.stat().st_size > 256:
        raise SystemExit("private MAC source missing or unexpectedly large")
    mac = PRIVATE_MAC_SOURCE.read_text(encoding="ascii", errors="strict").splitlines()[0].strip()
    if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac):
        raise SystemExit("private MAC is invalid")
    raw = bytes(int(part, 16) for part in mac.split(":"))
    if raw in (b"\0" * 6, b"\xff" * 6) or raw[0] & 1:
        raise SystemExit("private MAC is not usable unicast")
    return mac


def run(command: list[str], timeout: int = 120, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, check=check, text=True,
                          capture_output=True, timeout=timeout)


def verify(gate: dict[str, str]) -> tuple[Path, Path, list[tuple[Path, str]]]:
    manifest = ARTIFACT / "module-manifest.tsv"
    qdrv = ARTIFACT / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/qdrv/qdrv.ko"
    parent = PARENT_ARTIFACT / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/qdrv/qdrv.ko"
    expected = {"W3_MODULE_MANIFEST_SHA256": digest(manifest),
                "W3_QDRV_SHA256": digest(qdrv),
                "W3_QDRV_PARENT_SHA256": digest(parent),
                "W3_POWER_TABLE_SHA256": digest(POWER_TABLE),
                "W3_POWER_TABLE_MD5": digest(POWER_TABLE, "md5"),
                "W3_POWER_CONF_SHA256": digest(POWER_CONF)}
    uploads: list[tuple[Path, str]] = []
    for key, relative, remote in FIRMWARE:
        source = ARTIFACT / relative
        expected[key] = digest(source)
        uploads.append((source, remote))
    for key, actual in expected.items():
        if gate.get(key) != actual:
            raise SystemExit(f"sequential pinned input mismatch: {key}")
    required = {"W3_QDRV_SEQUENTIAL_BRINGUP_ONLY": "1", "W3_RAM_ONLY": "1",
                "W3_WATCHDOG_REQUIRED": "1", "W3_PRIVATE_MAC_REQUIRED": "1",
                "W3_QDRV_SINGLE_INSTANCE": "1", "W3_QDRV_LOAD_COUNT": "1",
                "W3_QDRV_COMMAND_COUNT": "10", "W3_VAP_CREATE_COUNT": "1",
                "W3_NO_RMMOD": "1",
                "W3_TARGET_COMPATIBLE": "mitrastar,hgw-500bna-qcv2",
                "W3_KERNEL_RELEASE": RELEASE, "W3_SWITCH_HANDOFF_STATUS": "committed",
                "W3_RF_ENABLE": "0", "W3_WIFI_ENABLE": "0",
                "W3_VAP_ENABLE": "0", "W3_FLASH_ENABLE": "0"}
    for key, wanted in required.items():
        if gate.get(key) != wanted:
            raise SystemExit(f"sequential gate mismatch: {key}")
    if POWER_CONF.read_text(encoding="ascii") != "power_selection=2\n":
        raise SystemExit("power_table.conf mismatch")
    private_mac()
    return qdrv, parent, uploads


def wait_for_watchdog(host: str, seconds: int = 180) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        probe = run([sys.executable, "tools/ramssh_exec.py",
                     "uname -r; echo W3_QDRV_SEQUENTIAL_WATCHDOG_RECOVERY_PASS",
                     "--host", host, "--timeout", "8"], timeout=15, check=False)
        if probe.returncode == 0 and "W3_QDRV_SEQUENTIAL_WATCHDOG_RECOVERY_PASS" in probe.stdout:
            print("W3_QDRV_SEQUENTIAL_WATCHDOG_RECOVERY_PASS=1")
            return True
        time.sleep(8)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--port", default="COM3")
    args = parser.parse_args()
    gate_path = APPROVED if args.execute else CLOSED
    gate = values(gate_path)
    qdrv, parent, firmware = verify(gate)
    print({"mode": "execute" if args.execute else "dry-run",
           "stage": "qdrv-sequential-bringup", "qdrv_loads": 1,
           "commands": 10, "private_mac": "validated-redacted",
           "rf": False, "vap": "create-down-only", "cleanup": "watchdog-only"})
    if not args.execute:
        print("W3_QDRV_SEQUENTIAL_BRINGUP_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK or gate.get("W3_QDRV_SEQUENTIAL_BRINGUP_APPROVED") != "1":
        raise SystemExit(f"require --ack {ACK} and approved gate")

    remote_root = "/tmp/w3-qdrv-sequential"
    capture: subprocess.Popen[str] | None = None
    try:
        run([sys.executable, "tools/ramssh_exec.py",
             "dmesg | grep -q 'OMWDT stage=armed'; dmesg | grep -q 'OMWDT stage=pet first=1'; "
             "test \"$(cat /run/openmitrastar/switch-emac-handoff/status)\" = committed; "
             "! grep -Eq '^(qdrv|wlan|temp_sensor|temp_sens) ' /proc/modules",
             "--host", args.host, "--timeout", "20"], timeout=40)
        run([sys.executable, "tools/ramssh_exec.py",
             f"rm -rf {remote_root}; mkdir -p {remote_root}/firmware {remote_root}/regulatory "
             f"{remote_root}/power_tables {remote_root}/private {remote_root}/provenance",
             "--host", args.host, "--timeout", "20"])
        module_root = ARTIFACT / f"rootfs/lib/modules/{RELEASE}/extra/quantenna"
        uploads = [(module_root / rel, f"{remote_root}/{Path(rel).name}", "0600") for rel in MODULES]
        uploads.extend((source, f"{remote_root}/{remote}", "0600") for source, remote in firmware)
        uploads.extend(((POWER_TABLE, f"{remote_root}/power_tables/{POWER_TABLE.name}", "0600"),
                        (POWER_CONF, f"{remote_root}/power_tables/{POWER_CONF.name}", "0600"),
                        (PRIVATE_MAC_SOURCE, f"{remote_root}/private/mac0addr", "0600"),
                        (parent, f"{remote_root}/provenance/qdrv-parent.ko", "0600"),
                        (RAM_INSMOD, f"{remote_root}/ram_insmod", "0700"),
                        (REMOTE, f"{remote_root}/sequential.sh", "0700"),
                        (APPROVED, "/tmp/W3_QDRV_SEQUENTIAL_BRINGUP_GATE.env", "0600")))
        for source, destination, mode in uploads:
            run([sys.executable, "tools/ramssh_upload.py", str(source), destination,
                 "--host", args.host, "--mode", mode], timeout=90)
        uart_dir = ROOT / "outputs/uart-live" / (
            "w3-qdrv-sequential-" + time.strftime("%Y%m%d-%H%M%S"))
        capture = subprocess.Popen(
            ["pwsh.exe", "-NoProfile", "-File", "tools/capture_topaz_uart.ps1",
             "-Port", args.port, "-Seconds", "420", "-OutputDirectory", str(uart_dir)],
            cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True)
        time.sleep(3)
        result = run([sys.executable, "tools/ramssh_exec.py",
                      f"sed -i 's/\r$//' {remote_root}/sequential.sh "
                      "/tmp/W3_QDRV_SEQUENTIAL_BRINGUP_GATE.env; "
                      f"sh {remote_root}/sequential.sh {remote_root} "
                      "/tmp/W3_QDRV_SEQUENTIAL_BRINGUP_GATE.env",
                      "--host", args.host, "--timeout", "300"], timeout=330, check=False)
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        if result.returncode or "W3_QDRV_SEQUENTIAL_BRINGUP_EXPERIMENT_PASS=1" not in result.stdout:
            print(f"W3_QDRV_SEQUENTIAL_FAILURE rc={result.returncode} uart={uart_dir}; waiting for watchdog")
            if not wait_for_watchdog(args.host):
                raise RuntimeError(f"sequential failed; watchdog recovery not yet observed; uart={uart_dir}")
            raise RuntimeError(f"sequential failed; watchdog recovered management; uart={uart_dir}")
        management = run([sys.executable, "tools/ramssh_exec.py",
                          "test \"$(cat /run/openmitrastar/switch-emac-handoff/status)\" = committed; "
                          "test -e /sys/class/net/br0/brif/eth1_emac1; "
                          "grep -q '^qdrv ' /proc/modules; echo W3_QDRV_SEQUENTIAL_MANAGEMENT_PASS",
                          "--host", args.host, "--timeout", "20"], timeout=40)
        if "W3_QDRV_SEQUENTIAL_MANAGEMENT_PASS" not in management.stdout:
            raise RuntimeError("sequential management readback missing")
    finally:
        if capture and capture.poll() is None:
            capture.terminate()
    print("W3_QDRV_SEQUENTIAL_BRINGUP_EXPERIMENT_PASS=1 qdrv_left_loaded=1 management=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
