#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BINDINGS = ROOT / "work/mission-state/router-lyoko-v0/evidence-bindings.json"
DEFAULT_WEB_ROOT = ROOT / "work/mission-state/router-lyoko-v0/rootfs/var/www"

REQUIRED_BINDINGS = {
    "live.system",
    "live.sectors",
    "live.runtime_status",
    "live.runtime_bridge",
    "live.runtime_clients",
    "live.runtime_recovery",
    "live.runtime_towers",
    "live.runtime_events",
    "static.sector_map",
    "static.goal_audit",
    "static.reentry",
    "static.aelita_memory",
    "static.control_policy",
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
        raise RuntimeError("evidence bindings must be a JSON object")
    return payload


def served_source_paths(source: str) -> list[str]:
    return re.findall(r"/lyoko-data/[A-Za-z0-9_.\-/]+", source)


def served_path_exists(web_root: Path, served_path: str) -> bool:
    relative = Path(*served_path.lstrip("/").split("/"))
    if relative.is_absolute() or ".." in relative.parts:
        return False
    path = (web_root / relative).resolve()
    web_root = web_root.resolve()
    return (path == web_root or web_root in path.parents) and path.is_file()


def validate(bindings_doc: dict[str, Any], *, web_root: Path) -> list[str]:
    errors: list[str] = []
    if bindings_doc.get("schema") != "router-lyoko.evidence-bindings/v1":
        errors.append("unexpected evidence-bindings schema")
    if bindings_doc.get("classification") != "STATIC-READONLY-EVIDENCE-BINDINGS-NO-HARDWARE-PROOF":
        errors.append("unexpected evidence-bindings classification")

    safety = bindings_doc.get("safety", {})
    for key in (
        "device_write",
        "flash_write",
        "bootenv_write",
        "network_reconfigure",
        "module_mutation",
        "dashboard_executes_commands",
    ):
        if safety.get(key) is not False:
            errors.append(f"safety flag must be false: {key}")

    rendered = json.dumps(bindings_doc, ensure_ascii=False)
    for token in FORBIDDEN_TEXT:
        if token in rendered:
            errors.append(f"forbidden executable/control token in evidence-bindings: {token!r}")

    promotion_rule = str(bindings_doc.get("promotion_rule") or "")
    if "static binding can orient" not in promotion_rule:
        errors.append("promotion_rule must state that static bindings only orient the dashboard")
    if "runtime verifier output" not in promotion_rule or "current hardware evidence" not in promotion_rule:
        errors.append("promotion_rule must require runtime verifier output and current hardware evidence")

    bindings = bindings_doc.get("bindings")
    if not isinstance(bindings, list) or not bindings:
        errors.append("bindings must be a non-empty list")
        return errors

    seen: set[str] = set()
    for binding in bindings:
        if not isinstance(binding, dict):
            errors.append("binding must be an object")
            continue
        bid = binding.get("id")
        if not isinstance(bid, str) or not bid:
            errors.append("binding missing id")
            continue
        if bid in seen:
            errors.append(f"duplicate binding id: {bid}")
        seen.add(bid)

        for field in ("panel", "lyoko_surface", "source", "source_type", "failure_mode"):
            if not isinstance(binding.get(field), str) or not binding.get(field).strip():
                errors.append(f"binding {bid} missing {field}")
        if not isinstance(binding.get("hardware_proof"), bool):
            errors.append(f"binding {bid} hardware_proof must be boolean")
        required_fields = binding.get("required_fields")
        if not isinstance(required_fields, list) or not required_fields:
            errors.append(f"binding {bid} must declare required_fields")
        elif not all(isinstance(item, str) and item.strip() for item in required_fields):
            errors.append(f"binding {bid} has invalid required_fields")

        source = str(binding.get("source") or "")
        source_type = str(binding.get("source_type") or "")
        failure_mode = str(binding.get("failure_mode") or "").lower()
        is_live = bid.startswith("live.")
        is_static = bid.startswith("static.")
        if not is_live and not is_static:
            errors.append(f"binding {bid} must be live.* or static.*")

        if is_live:
            if binding.get("hardware_proof") is not True:
                errors.append(f"binding {bid} must set hardware_proof=true")
            if source != "/api/lyoko":
                errors.append(f"binding {bid} runtime source must be /api/lyoko")
            if not source_type.startswith("runtime_"):
                errors.append(f"binding {bid} source_type must be runtime_*")
            if "never" not in failure_mode and "do not" not in failure_mode:
                errors.append(f"binding {bid} failure_mode must forbid inference or promotion")

        if is_static:
            if binding.get("hardware_proof") is not False:
                errors.append(f"binding {bid} must set hardware_proof=false")
            static_sources = served_source_paths(source)
            if not static_sources:
                errors.append(f"binding {bid} static source must reference /lyoko-data/")
            for served_path in static_sources:
                if not served_path_exists(web_root, served_path):
                    errors.append(f"binding {bid} static source missing: {served_path}")
            if "not" not in failure_mode and "unproven" not in failure_mode and "no " not in failure_mode:
                errors.append(f"binding {bid} failure_mode must keep static data non-authoritative")

    missing = sorted(REQUIRED_BINDINGS - seen)
    if missing:
        errors.append(f"missing required bindings: {', '.join(missing)}")
    return errors


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate Router-Lyoko evidence bindings truth contract.")
    parser.add_argument("--bindings", type=Path, default=DEFAULT_BINDINGS)
    parser.add_argument("--web-root", type=Path, default=DEFAULT_WEB_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        bindings_doc = load_json(args.bindings)
        errors = validate(bindings_doc, web_root=args.web_root)
    except Exception as exc:  # noqa: BLE001 - emit concise validation failure
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    if errors:
        print(json.dumps({"ok": False, "errors": errors}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(
        json.dumps(
            {
                "ok": True,
                "schema": "router-lyoko.evidence-bindings-guard/v1",
                "classification": "READONLY-EVIDENCE-BINDINGS-GUARD-NO-HARDWARE",
                "bindings": len(bindings_doc.get("bindings", [])),
                "runtime_bindings": len([b for b in bindings_doc.get("bindings", []) if b.get("id", "").startswith("live.")]),
                "static_bindings": len([b for b in bindings_doc.get("bindings", []) if b.get("id", "").startswith("static.")]),
            },
            indent=2,
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
