#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "work" / "mission-state" / "router-lyoko-v0" / "telemetry-contract.json"

REQUIRED_SAFETY_FALSE = (
    "device_write",
    "flash_write",
    "bootenv_write",
    "network_reconfigure",
    "module_mutation",
    "dashboard_executes_commands",
)

REQUIRED_RUNTIME_FIELDS = {
    "telemetry.captured_at_epoch": ("date +%s", True),
    "telemetry.runtime_sources": ("procfs", True),
    "system.kernel": ("uname -r", True),
    "sectors.bridge.irq20": ("/proc/interrupts", True),
    "mission_data.*": ("/var/www/lyoko-data", False),
}

FORBIDDEN_TEXT = (
    "flashcp",
    "mtd_write",
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
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise RuntimeError("telemetry contract must be a JSON object")
    return payload


def validate(contract: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if contract.get("schema") != "router-lyoko.telemetry-contract/v1":
        errors.append("unexpected telemetry-contract schema")
    if contract.get("classification") != "STATIC-READONLY-TELEMETRY-CONTRACT-NO-HARDWARE-PROOF":
        errors.append("unexpected telemetry-contract classification")

    rendered = json.dumps(contract, ensure_ascii=False)
    for token in FORBIDDEN_TEXT:
        if token in rendered:
            errors.append(f"forbidden executable/control token in telemetry-contract: {token!r}")

    truth_rule = str(contract.get("truth_rule") or "").lower()
    if "live router" not in truth_rule or "current boot" not in truth_rule:
        errors.append("truth_rule must require live router telemetry from the current boot")

    if contract.get("runtime_endpoint") != "/api/lyoko":
        errors.append("runtime_endpoint must be /api/lyoko")

    refresh = contract.get("refresh_policy")
    if not isinstance(refresh, dict):
        errors.append("refresh_policy must be an object")
    else:
        for key in ("dashboard_auto_refresh_seconds", "fresh_after_seconds", "stale_after_seconds"):
            if not isinstance(refresh.get(key), int) or refresh.get(key) <= 0:
                errors.append(f"refresh_policy.{key} must be a positive integer")
        fresh = refresh.get("fresh_after_seconds")
        stale = refresh.get("stale_after_seconds")
        if isinstance(fresh, int) and isinstance(stale, int) and fresh >= stale:
            errors.append("refresh_policy.fresh_after_seconds must be lower than stale_after_seconds")
        note = str(refresh.get("operator_note") or "").lower()
        if "observes only" not in note or "does not execute" not in note:
            errors.append("refresh_policy.operator_note must state observe-only/no-execute semantics")

    safety = contract.get("safety")
    if not isinstance(safety, dict):
        errors.append("safety must be an object")
    else:
        for key in REQUIRED_SAFETY_FALSE:
            if safety.get(key) is not False:
                errors.append(f"safety flag must be false: {key}")

    fields = contract.get("runtime_fields")
    if not isinstance(fields, list) or not fields:
        errors.append("runtime_fields must be a non-empty list")
        return errors

    by_path: dict[str, dict[str, Any]] = {}
    for item in fields:
        if not isinstance(item, dict):
            errors.append("runtime_fields entries must be objects")
            continue
        path = item.get("path")
        if not isinstance(path, str) or not path:
            errors.append("runtime field missing path")
            continue
        if path in by_path:
            errors.append(f"duplicate runtime field: {path}")
        by_path[path] = item
        if not isinstance(item.get("source"), str) or not item.get("source").strip():
            errors.append(f"runtime field {path} missing source")
        if not isinstance(item.get("hardware_proof"), bool):
            errors.append(f"runtime field {path} hardware_proof must be boolean")
        if not path.startswith("mission_data.") and item.get("hardware_proof") is not True:
            errors.append(f"runtime field {path} must be hardware_proof=true")
        if path.startswith("mission_data.") and item.get("hardware_proof") is not False:
            errors.append(f"runtime field {path} must be hardware_proof=false")

    for path, (source_fragment, hardware_proof) in REQUIRED_RUNTIME_FIELDS.items():
        item = by_path.get(path)
        if item is None:
            errors.append(f"missing required runtime field: {path}")
            continue
        if source_fragment not in str(item.get("source") or ""):
            errors.append(f"runtime field {path} source must include {source_fragment!r}")
        if item.get("hardware_proof") is not hardware_proof:
            errors.append(f"runtime field {path} hardware_proof must be {str(hardware_proof).lower()}")

    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Router-Lyoko telemetry truth contract.")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        contract = load_json(args.contract)
        errors = validate(contract)
    except Exception as exc:  # noqa: BLE001 - concise validation failure
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "schema": "router-lyoko.telemetry-contract-guard/v1",
                "classification": "READONLY-TELEMETRY-CONTRACT-GUARD-NO-HARDWARE",
                "runtime_fields": len(contract.get("runtime_fields", [])),
                "safety_flags": len(REQUIRED_SAFETY_FALSE),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
