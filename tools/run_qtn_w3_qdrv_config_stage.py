#!/usr/bin/env python3
"""Stage private MAC and pinned QSR1000 power metadata without start or RF."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-qdrv-staged-20260819"
RELEASE = "5.10.260-openmitrastar-radiohw"
PRIVATE_MAC_SOURCE = ROOT / "work/secrets-backup/20260725-161724-text/mnt__jffs2__wifi_mac_addrs"
POWER_ROOT = ROOT / "work/hgw500-rootfs-live/squashfs-root/etc/power_tables"
POWER_TABLE = POWER_ROOT / "tx_power_QSR1000_es.txt"
POWER_CONF = POWER_ROOT / "power_table.conf"
WATCHDOG_IMAGE = ROOT / "work/tftp/omvl/linux510-product-watchdog-canary-v1-RAM-ONLY.bin"
QDRV = ARTIFACT / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/qdrv/qdrv.ko"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QDRV_CONFIG_STAGE_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QDRV_CONFIG_STAGE_GATE.approved.env"
REMOTE = ROOT / "tools/qtn_w3_qdrv_config_stage_remote.sh"
ACK = "OPENMITRASTAR_QTN_W3_QDRV_CONFIG_STAGE_RAM_ONLY"


def digest(path: Path, algorithm: str = "sha256") -> str:
    result = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            result.update(block)
    return result.hexdigest()


def values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def private_mac_first_line() -> str:
    if not PRIVATE_MAC_SOURCE.is_file() or PRIVATE_MAC_SOURCE.stat().st_size > 256:
        raise SystemExit("private MAC source missing or unexpectedly large")
    lines = PRIVATE_MAC_SOURCE.read_text(encoding="ascii", errors="strict").splitlines()
    if not lines:
        raise SystemExit("private MAC source is empty")
    mac = lines[0].strip()
    if not re.fullmatch(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", mac):
        raise SystemExit("private MAC first line is invalid")
    octets = bytes(int(part, 16) for part in mac.split(":"))
    if octets in (b"\x00" * 6, b"\xff" * 6) or octets[0] & 1:
        raise SystemExit("private MAC first line is not a usable unicast address")
    return mac


def run(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, check=True, text=True,
                          capture_output=True, timeout=timeout)


def verify(gate: dict[str, str]) -> None:
    manifest = ARTIFACT / "module-manifest.tsv"
    expected = {
        "W3_MODULE_MANIFEST_SHA256": digest(manifest),
        "W3_QDRV_SHA256": digest(QDRV),
        "W3_QDRV_MD5": digest(QDRV, "md5"),
        "W3_POWER_TABLE_SHA256": digest(POWER_TABLE),
        "W3_POWER_TABLE_MD5": digest(POWER_TABLE, "md5"),
        "W3_POWER_CONF_SHA256": digest(POWER_CONF),
        "W3_POWER_CONF_MD5": digest(POWER_CONF, "md5"),
        "W3_WATCHDOG_IMAGE_SHA256": digest(WATCHDOG_IMAGE),
    }
    for key, actual in expected.items():
        if gate.get(key) != actual:
            raise SystemExit(f"qdrv config-stage pinned artifact mismatch: {key}")
    if gate["W3_QDRV_SHA256"] != "338b09fcbcff933f716783a955b2d1dcec546a16675c02529570b205810c8791":
        raise SystemExit("qdrv config-stage unpinned qdrv")
    safe = {
        "W3_QDRV_CONFIG_STAGE_ONLY": "1", "W3_RAM_ONLY": "1",
        "W3_WATCHDOG_REQUIRED": "1", "W3_PRIVATE_MAC_REQUIRED": "1",
        "W3_RF_ENABLE": "0", "W3_FLASH_ENABLE": "0", "W3_WIFI_ENABLE": "0",
        "W3_VAP_ENABLE": "0", "W3_QDRV_CLEARSRAM_ENABLE": "0",
        "W3_QDRV_START_ENABLE": "0", "W3_SWITCH_HANDOFF_STATUS": "committed",
        "W3_FIRMWARE_STAGE_STATUS": "staged", "W3_KERNEL_RELEASE": RELEASE,
        "W3_TARGET_COMPATIBLE": "mitrastar,hgw-500bna-qcv2",
    }
    for key, wanted in safe.items():
        if gate.get(key) != wanted:
            raise SystemExit(f"qdrv config-stage gate mismatch: {key}")
    if POWER_CONF.read_text(encoding="ascii") != "power_selection=2\n":
        raise SystemExit("qdrv config-stage power_table.conf mismatch")
    private_mac_first_line()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.200")
    args = parser.parse_args()
    gate_path = APPROVED if args.execute else CLOSED
    gate = values(gate_path)
    verify(gate)
    print({
        "mode": "execute" if args.execute else "dry-run",
        "stage": "qdrv-config-only", "private_mac": "validated-redacted",
        "power_table_sha256": gate["W3_POWER_TABLE_SHA256"],
        "power_table_md5": gate["W3_POWER_TABLE_MD5"],
        "ram_only": True, "watchdog": True, "rf": False, "flash": False,
        "vap": False,
    })
    if not args.execute:
        print("W3_QDRV_CONFIG_STAGE_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")
    if gate.get("W3_QDRV_CONFIG_STAGE_APPROVED") != "1":
        raise SystemExit("qdrv config-stage approved gate is closed")

    remote_root = "/tmp/w3-qdrv-config-stage"
    run([sys.executable, "tools/ramssh_exec.py",
         f"rm -rf {remote_root}; mkdir -p {remote_root}/private {remote_root}/power_tables {remote_root}/provenance",
         "--host", args.host, "--timeout", "20"])
    uploads = (
        (PRIVATE_MAC_SOURCE, f"{remote_root}/private/mac0addr", "0600"),
        (POWER_TABLE, f"{remote_root}/power_tables/tx_power_QSR1000_es.txt", "0600"),
        (POWER_CONF, f"{remote_root}/power_tables/power_table.conf", "0600"),
        (QDRV, f"{remote_root}/provenance/qdrv.ko", "0600"),
        (REMOTE, f"{remote_root}/stage.sh", "0700"),
        (APPROVED, "/tmp/W3_QDRV_CONFIG_STAGE_GATE.env", "0600"),
    )
    for source, destination, mode in uploads:
        run([sys.executable, "tools/ramssh_upload.py", str(source), destination,
             "--host", args.host, "--mode", mode], timeout=90)

    run([sys.executable, "tools/ramssh_exec.py",
         "dmesg | grep -E 'OMWDT stage=(armed|pet first=1)'",
         "--host", args.host, "--timeout", "20"])
    uart_dir = ROOT / "outputs/uart-live" / (
        "qdrv-config-stage-" + time.strftime("%Y%m%d-%H%M%S")
    )
    capture = subprocess.Popen(
        ["pwsh.exe", "-NoProfile", "-File", "tools/capture_topaz_uart.ps1",
         "-Port", "COM3", "-Seconds", "120", "-OutputDirectory", str(uart_dir)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        time.sleep(3.0)
        result = subprocess.run(
            [sys.executable, "tools/ramssh_exec.py",
             f"sed -i 's/\r$//' {remote_root}/stage.sh /tmp/W3_QDRV_CONFIG_STAGE_GATE.env; "
             f"sh {remote_root}/stage.sh {remote_root} /tmp/W3_QDRV_CONFIG_STAGE_GATE.env",
             "--host", args.host, "--timeout", "90"],
            cwd=ROOT, text=True, capture_output=True, timeout=120, check=False,
        )
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        if result.returncode != 0:
            time.sleep(5)
            raise SystemExit(f"qdrv config-stage remote failed rc={result.returncode} uart={uart_dir}")
        if "W3_QDRV_CONFIG_STAGE_EXPERIMENT_PASS=1" not in result.stdout:
            raise SystemExit("qdrv config-stage pass marker missing")
    finally:
        if capture.poll() is None:
            capture.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
