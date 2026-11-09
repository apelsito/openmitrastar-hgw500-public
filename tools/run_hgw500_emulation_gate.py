#!/usr/bin/env python3
"""Run the HGW-500BNA-QCv2 offline emulation gates.

This gate is deliberately conservative. A firmware candidate is not hardware
eligible unless:

1. the stock dump passes the Bootbase contract emulator;
2. the candidate passes the Bootbase RAS/uImage contract;
3. the ARC QEMU validation log contains the PID1 marker.

The current QEMU target is a validation twin, not a Topaz machine emulator, so
passing QEMU still does not authorize flash by itself. Failing QEMU blocks flash.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_PARTS = ROOT / "hgw500bna-qcv2-firmware-dump-verified"
DEFAULT_CANDIDATE = (
    ROOT
    / "outputs"
    / "emulation"
    / "linux-5.10.260-topaz-engineering-DO-NOT-FLASH-bootbase-ras.bin"
)
DEFAULT_QEMU_LOG = (
    ROOT / "outputs" / "kernel-port" / "linux-5.10.260-qemu-arc700-validation.serial.log"
)
DEFAULT_REPORT = ROOT / "outputs" / "emulation" / "hgw500-emulation-gate-report.json"
BOOTBASE = ROOT / "tools" / "bootbase_contract_emulator.py"


def run_json(command: list[str]) -> tuple[int, dict]:
    proc = subprocess.run(command, cwd=ROOT, text=True, capture_output=True)
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        payload = {
            "result": "FAIL",
            "stdout": proc.stdout,
            "stderr": proc.stderr,
            "decode_error": "command did not emit JSON",
        }
    return proc.returncode, payload


def qemu_status(log_path: Path) -> dict:
    if not log_path.exists():
        return {
            "result": "FAIL",
            "log": str(log_path),
            "marker_found": False,
            "error": "QEMU serial log is missing",
        }
    text = log_path.read_text(errors="replace")
    marker = "OpenMitraStar QEMU validation twin is alive"
    assertion = "find_insn_for_opcode" in text or "Assertion" in text
    return {
        "result": "PASS" if marker in text and not assertion else "FAIL",
        "log": str(log_path),
        "marker_found": marker in text,
        "qemu_assertion": assertion,
        "tail": "\n".join(text.splitlines()[-12:]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--parts-dir", type=Path, default=DEFAULT_PARTS)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--qemu-log", type=Path, default=DEFAULT_QEMU_LOG)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    args = parser.parse_args()

    stock_rc, stock = run_json(
        [
            sys.executable,
            str(BOOTBASE),
            "--parts-dir",
            str(args.parts_dir),
        ]
    )
    candidate_rc, candidate = run_json(
        [
            sys.executable,
            str(BOOTBASE),
            "--parts-dir",
            str(args.parts_dir),
            "--candidate-slot",
            str(args.candidate),
            "--candidate-name",
            args.candidate.name,
        ]
    )
    qemu = qemu_status(args.qemu_log)

    checks = {
        "bootbase_stock": "PASS" if stock_rc == 0 and stock.get("result") == "PASS" else "FAIL",
        "bootbase_candidate": (
            "PASS" if candidate_rc == 0 and candidate.get("result") == "PASS" else "FAIL"
        ),
        "qemu_arc_validation": qemu["result"],
    }
    overall = "PASS" if all(value == "PASS" for value in checks.values()) else "BLOCKED"
    report = {
        "result": overall,
        "checks": checks,
        "flash_authorized": False,
        "flash_policy": (
            "Do not flash. This gate is offline-only and requires all checks to pass; "
            "even then, UART/RAM-only hardware validation is still required."
        ),
        "stock_bootbase": stock,
        "candidate_bootbase": candidate,
        "qemu": qemu,
    }

    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if overall == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
