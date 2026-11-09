#!/usr/bin/env python3
"""Load the signed qdrv control plane after a committed switch-EMAC handoff."""
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
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QDRV_CONTROL_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QDRV_CONTROL_GATE.approved.env"
REMOTE = ROOT / "tools/qtn_w3_qdrv_control_remote.sh"
RAM_INSMOD = ROOT / "outputs/kernel-port/ram-insmod-nolibc/ram_insmod_nolibc"
ACK = "OPENMITRASTAR_QTN_W3_QDRV_CONTROL_ONLY"
MODULES = [
    "platform/ruby/gpio.ko",
    "platform/qtsens/temp_sensor.ko",
    "platform/topaz/temp_sens.ko",
    "wlan/wlan.ko",
    "qdrv/qdrv.ko",
]


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


def verify(gate: dict[str, str]) -> None:
    manifest = ARTIFACT / "module-manifest.tsv"
    if sha256(manifest) != gate["W3_MODULE_MANIFEST_SHA256"]:
        raise SystemExit("qdrv-control manifest hash mismatch")
    rows = manifest.read_text(encoding="utf-8").splitlines()
    qdrv_hash = next(row.split("\t", 2)[1] for row in rows[1:]
                     if row.startswith("qdrv/qdrv.ko\t"))
    if qdrv_hash != gate["W3_QDRV_SHA256"]:
        raise SystemExit("qdrv-control qdrv hash mismatch")
    module_root = ARTIFACT / "rootfs/lib/modules" / RELEASE / "extra/quantenna"
    for relative in MODULES:
        if not (module_root / relative).is_file():
            raise SystemExit(f"qdrv-control module missing: {relative}")
    if gate.get("W3_RF_ENABLE") != "0" or gate.get("W3_QDRV_CONTROL_ONLY") != "1":
        raise SystemExit("qdrv-control RF/control gate mismatch")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--stop-after-wlan", action="store_true")
    args = parser.parse_args()
    gate_path = APPROVED if args.execute else CLOSED
    gate = values(gate_path)
    verify(gate)
    print({"mode": "execute" if args.execute else "dry-run", "modules": MODULES,
           "qdrv_sha256": gate["W3_QDRV_SHA256"], "rf": False})
    if not args.execute:
        print("W3_QDRV_CONTROL_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")
    if gate.get("W3_QDRV_CONTROL_APPROVED") != "1":
        raise SystemExit("qdrv control approved gate is closed")
    remote_root = "/tmp/w3-qdrv-control"
    run([sys.executable, "tools/ramssh_exec.py", f"rm -rf {remote_root}; mkdir -p {remote_root}",
         "--host", args.host, "--timeout", "20"])
    module_root = ARTIFACT / "rootfs/lib/modules" / RELEASE / "extra/quantenna"
    uploads = [(module_root / rel, f"{remote_root}/{Path(rel).name}", "0600") for rel in MODULES]
    runtime_gate = ROOT / "work/mission-state/w3-offline/.W3_QDRV_CONTROL_GATE.runtime.env"
    runtime_gate.write_text(
        gate_path.read_text(encoding="utf-8") +
        f"W3_QDRV_STOP_AFTER_WLAN={1 if args.stop_after_wlan else 0}\n",
        encoding="utf-8", newline="\n",
    )
    uploads += [(RAM_INSMOD, f"{remote_root}/ram_insmod", "0700"),
                (REMOTE, f"{remote_root}/control.sh", "0700"),
                (runtime_gate, "/tmp/W3_QDRV_CONTROL_GATE.env", "0600")]
    for source, destination, mode in uploads:
        run([sys.executable, "tools/ramssh_upload.py", str(source), destination,
             "--host", args.host, "--mode", mode], timeout=90)
    uart_dir = ROOT / "outputs/uart-live" / ("qdrv-control-" + time.strftime("%Y%m%d-%H%M%S"))
    capture = subprocess.Popen(
        ["pwsh.exe", "-NoProfile", "-File", "tools/capture_topaz_uart.ps1",
         "-Port", "COM3", "-Seconds", "180", "-OutputDirectory", str(uart_dir)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, text=True,
    )
    try:
        time.sleep(3.0)
        result = subprocess.run(
            [sys.executable, "tools/ramssh_exec.py",
             f"sed -i 's/\r$//' {remote_root}/control.sh /tmp/W3_QDRV_CONTROL_GATE.env; "
             f"sh {remote_root}/control.sh {remote_root} /tmp/W3_QDRV_CONTROL_GATE.env",
             "--host", args.host, "--timeout", "120"],
            cwd=ROOT, text=True, capture_output=True, timeout=150, check=False,
        )
        print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, file=sys.stderr, end="")
        if result.returncode != 0:
            time.sleep(5)
            raise SystemExit(f"qdrv control remote failed rc={result.returncode} uart={uart_dir}")
        expected_marker = (
            "W3_QDRV_WLAN_ONLY_EXPERIMENT_PASS=1"
            if args.stop_after_wlan else "W3_QDRV_CONTROL_EXPERIMENT_PASS=1"
        )
        if expected_marker not in result.stdout:
            raise SystemExit("qdrv control pass marker missing")
    finally:
        runtime_gate.unlink(missing_ok=True)
        if capture.poll() is None:
            capture.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
