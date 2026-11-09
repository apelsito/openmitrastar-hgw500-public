#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SAFE_MODE = ROOT / "work/mission-state/router-lyoko-v0/safe-mode.json"
EXPECTED_ACK = "OPENMITRASTAR_RESUME_AFTER_TX7_HANG_READONLY"

FORBIDDEN_TEXT = (
    "flashcp",
    "mtd_write ",
    "fw_setenv",
    "saveenv",
    "/dev/mtd",
    "dd if=",
    "dd of=",
    "bootm ",
    "reboot",
    "halt",
    "poweroff",
    "insmod ",
    "rmmod ",
    "modprobe ",
    "ifconfig ",
    "ip addr ",
    "ip route ",
    "brctl ",
    "hostapd_cli ",
    "call_qcsapi ",
    "qweconfig ",
)


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def rel_exists(path_text: str) -> bool:
    return (ROOT / Path(*Path(path_text).parts)).exists()


def validate_safe_mode(safe_mode: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if safe_mode.get("schema") != "router-lyoko.safe-mode/v1":
        errors.append("unexpected safe-mode schema")
    if safe_mode.get("classification") != "STATIC-READONLY-SAFE-MODE-CONTRACT-NO-HARDWARE-ACTION":
        errors.append("unexpected safe-mode classification")
    if safe_mode.get("mode") != "observe_only":
        errors.append("safe-mode must remain observe_only")
    if safe_mode.get("ack_required") != EXPECTED_ACK:
        errors.append("safe-mode ack_required drifted")

    safety = safe_mode.get("safety", {})
    for key in (
        "dashboard_executes_commands",
        "device_write",
        "flash_write",
        "bootenv_write",
        "mtd_write",
        "module_mutation",
        "network_reconfigure",
        "uart_opened_by_dashboard",
    ):
        if safety.get(key) is not False:
            errors.append(f"safety flag must be false: {key}")

    for evidence_path in safe_mode.get("evidence", []):
        if not isinstance(evidence_path, str) or not evidence_path:
            errors.append("invalid evidence path")
        elif not rel_exists(evidence_path):
            errors.append(f"evidence path missing: {evidence_path}")

    sequence = safe_mode.get("operator_sequence", [])
    if not isinstance(sequence, list) or len(sequence) < 3:
        errors.append("operator_sequence must include physical, recovery and next-gate steps")
        sequence = []

    ids = [step.get("id") for step in sequence if isinstance(step, dict)]
    for expected in ("physical-power-cycle", "post-tx7-recovery-proof", "tx11-boot-evidence-collection-plan", "tx11-2g-client-gate-plan"):
        if expected not in ids:
            errors.append(f"missing operator step: {expected}")

    for step in sequence:
        if not isinstance(step, dict):
            errors.append("operator step must be object")
            continue
        sid = step.get("id", "<missing>")
        if step.get("display_only") is not True:
            errors.append(f"operator step must be display_only: {sid}")
        if step.get("requires_human") is not True:
            errors.append(f"operator step must require human: {sid}")
        if sid == "post-tx7-recovery-proof":
            if step.get("requires_ack") != EXPECTED_ACK:
                errors.append("recovery proof step missing expected ACK")
            if EXPECTED_ACK not in step.get("display_command", ""):
                errors.append("recovery proof command missing expected ACK")
        if sid == "tx11-boot-evidence-collection-plan":
            if step.get("prerequisite") != "OMPOSTTX7_RECOVERY_PASS=1":
                errors.append("TX11 boot evidence collection must require recovery PASS")
            if step.get("requires_exact_image_ram_boot") is not True:
                errors.append("TX11 boot evidence collection must require exact RAM boot")
            command = step.get("display_command", "")
            if "collect_w2_tx11_boot_evidence.ps1" not in command:
                errors.append("TX11 boot evidence command missing collector")
            if "OPENMITRASTAR_COLLECT_TX11_BOOT_EVIDENCE_READONLY" not in command:
                errors.append("TX11 boot evidence command missing read-only ACK")
            if "w2-tx11-green-boot-controls-boot-evidence-latest.json" not in command:
                errors.append("TX11 boot evidence command missing output path")
        if sid == "tx11-2g-client-gate-plan":
            if step.get("prerequisite") != "OMTX11_BOOT_EVIDENCE_VERIFIED=1":
                errors.append("TX11 client gate must require boot evidence PASS")
            if step.get("requires_tx11_boot_evidence_json") is not True:
                errors.append("TX11 client gate must require Tx11BootEvidenceJson")
            command = step.get("display_command", "")
            boot_evidence = step.get("tx11_boot_evidence_json", "")
            if "Tx11BootEvidenceJson" not in command:
                errors.append("TX11 client gate command missing Tx11BootEvidenceJson")
            if "w2-tx11-green-boot-controls-boot-evidence-latest.json" not in command:
                errors.append("TX11 client gate command missing boot evidence path")
            if "OPENMITRASTAR_TX11_CLIENT_GATE_RAM_ONLY" not in command:
                errors.append("TX11 client gate command missing exact RAM-only ACK")
            if not isinstance(boot_evidence, str) or "w2-tx11-green-boot-controls-boot-evidence-latest.json" not in boot_evidence:
                errors.append("TX11 client gate missing tx11_boot_evidence_json path")

    rendered = json.dumps(safe_mode, ensure_ascii=False)
    for token in FORBIDDEN_TEXT:
        if token in rendered:
            errors.append(f"forbidden executable/control token in safe-mode: {token!r}")

    forbidden_dashboard_actions = safe_mode.get("forbidden_dashboard_actions", [])
    required_forbidden = (
        "execute shell commands",
        "open UART",
        "change boot environment",
        "write flash or MTD",
        "reload kernel modules",
        "change network configuration",
        "start a 5 GHz experiment before recovery proof",
    )
    for required in required_forbidden:
        if required not in forbidden_dashboard_actions:
            errors.append(f"missing forbidden dashboard action: {required}")

    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Router-Lyoko safe-mode contract.")
    parser.add_argument("--safe-mode", type=Path, default=DEFAULT_SAFE_MODE)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        safe_mode = load_json(args.safe_mode)
        errors = validate_safe_mode(safe_mode)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "safe_mode": str(args.safe_mode),
        "mode": safe_mode["mode"],
        "steps": len(safe_mode.get("operator_sequence", [])),
        "ack_required": safe_mode["ack_required"],
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
