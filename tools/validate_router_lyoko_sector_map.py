#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MAP = ROOT / "work/mission-state/router-lyoko-v0/sector-map.json"
DEFAULT_TRUTH = ROOT / "work/mission-state/router-lyoko-v0/mission-truth.json"

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
    return json.loads(path.read_text(encoding="utf-8"))


def rel_exists(path_text: str) -> bool:
    path = ROOT / Path(*Path(path_text).parts)
    return path.exists()


def validate_sector_map(sector_map: dict[str, Any], truth: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if sector_map.get("schema") != "router-lyoko.sector-map/v1":
        errors.append("unexpected sector-map schema")
    if sector_map.get("classification") != "STATIC-READONLY-MAP-NO-HARDWARE-PROOF":
        errors.append("unexpected sector-map classification")
    if truth.get("schema") != "router-lyoko.truth/v1":
        errors.append("unexpected mission-truth schema")

    safety = sector_map.get("safety", {})
    for key in (
        "device_write",
        "flash_write",
        "bootenv_write",
        "network_reconfigure",
        "module_mutation",
        "executable_control",
    ):
        if safety.get(key) is not False:
            errors.append(f"safety flag must be false: {key}")

    rendered = json.dumps(sector_map, ensure_ascii=False)
    for token in FORBIDDEN_TEXT:
        if token in rendered:
            errors.append(f"forbidden executable/control token in sector-map: {token!r}")

    gates = {gate.get("id"): gate for gate in truth.get("gates", []) if gate.get("id")}
    if not gates:
        errors.append("mission-truth contains no gates")

    sectors = sector_map.get("sectors", [])
    towers = sector_map.get("towers", [])
    if not isinstance(sectors, list) or not sectors:
        errors.append("sector-map must define sectors")
        sectors = []
    if not isinstance(towers, list) or not towers:
        errors.append("sector-map must define towers")
        towers = []

    sector_ids: set[str] = set()
    for sector in sectors:
        sid = sector.get("id")
        if not sid:
            errors.append("sector missing id")
            continue
        if sid in sector_ids:
            errors.append(f"duplicate sector id: {sid}")
        sector_ids.add(sid)
        for field in ("label", "lyoko_role", "real_component", "current_gate", "status"):
            if not sector.get(field):
                errors.append(f"sector {sid} missing {field}")
        gate_id = sector.get("current_gate")
        gate = gates.get(gate_id)
        if not gate:
            errors.append(f"sector {sid} references unknown gate: {gate_id}")
        elif sector.get("status") != gate.get("status"):
            errors.append(
                f"sector {sid} status {sector.get('status')} != gate {gate_id} status {gate.get('status')}"
            )
        evidence = sector.get("evidence", [])
        if not evidence:
            errors.append(f"sector {sid} has no evidence paths")
        for evidence_path in evidence:
            if not isinstance(evidence_path, str) or not evidence_path:
                errors.append(f"sector {sid} has invalid evidence path")
            elif not rel_exists(evidence_path):
                errors.append(f"sector {sid} evidence path missing: {evidence_path}")

    tower_ids: set[str] = set()
    for tower in towers:
        tid = tower.get("id")
        if not tid:
            errors.append("tower missing id")
            continue
        if tid in tower_ids:
            errors.append(f"duplicate tower id: {tid}")
        tower_ids.add(tid)
        for field in ("label", "real_service", "sector", "status", "gate"):
            if not tower.get(field):
                errors.append(f"tower {tid} missing {field}")
        if tower.get("sector") not in sector_ids:
            errors.append(f"tower {tid} references unknown sector: {tower.get('sector')}")
        gate_id = tower.get("gate")
        gate = gates.get(gate_id)
        if not gate:
            errors.append(f"tower {tid} references unknown gate: {gate_id}")
        elif tower.get("status") != gate.get("status"):
            errors.append(
                f"tower {tid} status {tower.get('status')} != gate {gate_id} status {gate.get('status')}"
            )
        evidence = tower.get("evidence", [])
        if not evidence:
            errors.append(f"tower {tid} has no evidence paths")
        for evidence_path in evidence:
            if not isinstance(evidence_path, str) or not evidence_path:
                errors.append(f"tower {tid} has invalid evidence path")
            elif not rel_exists(evidence_path):
                errors.append(f"tower {tid} evidence path missing: {evidence_path}")

    expected_sectors = {"core", "bridge", "realtek", "quantenna", "memory", "interface", "aelita"}
    missing = sorted(expected_sectors - sector_ids)
    if missing:
        errors.append(f"missing required sectors: {', '.join(missing)}")

    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Router-Lyoko sector-map consistency.")
    parser.add_argument("--sector-map", type=Path, default=DEFAULT_MAP)
    parser.add_argument("--truth", type=Path, default=DEFAULT_TRUTH)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        sector_map = load_json(args.sector_map)
        truth = load_json(args.truth)
        errors = validate_sector_map(sector_map, truth)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps({
        "ok": True,
        "sector_map": str(args.sector_map),
        "truth": str(args.truth),
        "sectors": len(sector_map.get("sectors", [])),
        "towers": len(sector_map.get("towers", [])),
    }, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
