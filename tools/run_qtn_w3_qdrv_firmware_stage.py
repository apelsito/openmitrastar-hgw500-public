#!/usr/bin/env python3
"""Stage pinned qdrv firmware paths in RAM without starting any radio core."""
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-qdrv-staged-20260819"
RELEASE = "5.10.260-openmitrastar-radiohw"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QDRV_FIRMWARE_STAGE_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QDRV_FIRMWARE_STAGE_GATE.approved.env"
REMOTE = ROOT / "tools/qtn_w3_qdrv_firmware_stage_remote.sh"
ACK = "OPENMITRASTAR_QTN_W3_QDRV_FIRMWARE_STAGE_RAM_ONLY"
QDRV = ARTIFACT / f"rootfs/lib/modules/{RELEASE}/extra/quantenna/qdrv/qdrv.ko"
INPUTS = (
    ("W3_MUCFW_SHA256", ARTIFACT / "rootfs/lib/firmware/qtn_driver.qtn_ruby.0.bin",
     "firmware/qtn_driver.qtn_ruby.0.bin", True),
    ("W3_AUCFW_SHA256", ARTIFACT / "rootfs/lib/firmware/auc_driver.nomu.0.bin",
     "firmware/auc_driver.nomu.0.bin", True),
    ("W3_DSPFW_SHA256", ARTIFACT / "rootfs/lib/firmware/rdsp_driver.0.bin",
     "firmware/rdsp_driver.0.bin", True),
    ("W3_REGDB_SHA256", ARTIFACT / "rootfs/etc/qtn_regulatory_db.bin",
     "regulatory/qtn_regulatory_db.bin", False),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def run(command: list[str], timeout: int = 120) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, cwd=ROOT, check=True, text=True,
                          capture_output=True, timeout=timeout)


def verify(gate: dict[str, str]) -> list[tuple[Path, str]]:
    manifest = ARTIFACT / "module-manifest.tsv"
    if sha256(manifest) != gate["W3_MODULE_MANIFEST_SHA256"]:
        raise SystemExit("qdrv firmware-stage manifest hash mismatch")
    if not QDRV.is_file() or sha256(QDRV) != gate["W3_QDRV_SHA256"]:
        raise SystemExit("qdrv firmware-stage qdrv hash mismatch")
    if gate["W3_QDRV_SHA256"] != "338b09fcbcff933f716783a955b2d1dcec546a16675c02529570b205810c8791":
        raise SystemExit("qdrv firmware-stage unpinned qdrv")
    safe = {
        "W3_QDRV_FIRMWARE_STAGE_ONLY": "1", "W3_RAM_ONLY": "1",
        "W3_RF_ENABLE": "0", "W3_FLASH_ENABLE": "0", "W3_WIFI_ENABLE": "0",
        "W3_QDRV_CLEARSRAM_ENABLE": "0", "W3_QDRV_START_ENABLE": "0",
        "W3_SWITCH_HANDOFF_STATUS": "committed",
        "W3_KERNEL_RELEASE": RELEASE,
        "W3_TARGET_COMPATIBLE": "mitrastar,hgw-500bna-qcv2",
    }
    for key, expected in safe.items():
        if gate.get(key) != expected:
            raise SystemExit(f"qdrv firmware-stage gate mismatch: {key}")
    uploads: list[tuple[Path, str]] = []
    for key, source, remote_rel, required in INPUTS:
        available = source.is_file()
        if required and not available:
            raise SystemExit(f"qdrv firmware-stage input missing: {source.name}")
        if key == "W3_REGDB_SHA256":
            if gate.get("W3_REGDB_AVAILABLE") != ("1" if available else "0"):
                raise SystemExit("qdrv firmware-stage regulatory availability mismatch")
        if available:
            if sha256(source) != gate[key]:
                raise SystemExit(f"qdrv firmware-stage input hash mismatch: {source.name}")
            uploads.append((source, remote_rel))
    return uploads


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.200")
    args = parser.parse_args()
    gate_path = APPROVED if args.execute else CLOSED
    gate = values(gate_path)
    inputs = verify(gate)
    print({
        "mode": "execute" if args.execute else "dry-run",
        "stage": "qdrv-firmware-paths-only",
        "qdrv_sha256": gate["W3_QDRV_SHA256"],
        "inputs": [source.name for source, _ in inputs],
        "ram_only": True, "rf": False, "flash": False, "wifi": False,
    })
    if not args.execute:
        print("W3_QDRV_FIRMWARE_STAGE_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")
    if gate.get("W3_QDRV_FIRMWARE_STAGE_APPROVED") != "1":
        raise SystemExit("qdrv firmware-stage approved gate is closed")

    remote_root = "/tmp/w3-qdrv-firmware-stage"
    run([sys.executable, "tools/ramssh_exec.py",
         f"rm -rf {remote_root}; mkdir -p {remote_root}/firmware {remote_root}/regulatory {remote_root}/provenance",
         "--host", args.host, "--timeout", "20"])
    uploads = [(QDRV, f"{remote_root}/provenance/qdrv.ko", "0600")]
    target_by_name = {
        "qtn_driver.qtn_ruby.0.bin": "/lib/firmware/qtn_driver.qtn_ruby.0.bin",
        "auc_driver.nomu.0.bin": "/lib/firmware/auc_driver.nomu.0.bin",
        "rdsp_driver.0.bin": "/lib/firmware/rdsp_driver.0.bin",
        "qtn_regulatory_db.bin": "/etc/qtn_regulatory_db.bin",
    }
    uploads.extend((source, target_by_name[source.name], "0600")
                   for source, _remote_rel in inputs)
    uploads.extend(((REMOTE, f"{remote_root}/stage.sh", "0700"),
                    (APPROVED, "/tmp/W3_QDRV_FIRMWARE_STAGE_GATE.env", "0600")))
    for source, destination, mode in uploads:
        run([sys.executable, "tools/ramssh_upload.py", str(source), destination,
             "--host", args.host, "--mode", mode], timeout=90)

    uart_dir = ROOT / "outputs/uart-live" / (
        "qdrv-firmware-stage-" + time.strftime("%Y%m%d-%H%M%S")
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
             f"sed -i 's/\r$//' {remote_root}/stage.sh /tmp/W3_QDRV_FIRMWARE_STAGE_GATE.env; "
             f"sh {remote_root}/stage.sh {remote_root} /tmp/W3_QDRV_FIRMWARE_STAGE_GATE.env",
             "--host", args.host, "--timeout", "90"],
            cwd=ROOT, text=True, capture_output=True, timeout=120, check=False,
        )
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        if result.returncode != 0:
            time.sleep(5)
            raise SystemExit(
                f"qdrv firmware-stage remote failed rc={result.returncode} uart={uart_dir}"
            )
        if "W3_QDRV_FIRMWARE_STAGE_EXPERIMENT_PASS=1" not in result.stdout:
            raise SystemExit("qdrv firmware-stage pass marker missing")
    finally:
        if capture.poll() is None:
            capture.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
