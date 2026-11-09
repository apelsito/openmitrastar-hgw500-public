#!/usr/bin/env python3

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "work/mission-state/router-lyoko-v0/control/control-policy.json"

FORBIDDEN_IN_ALLOWED = (
    "flashcp",
    "mtd_write",
    "fw_setenv",
    "saveenv",
    "/dev/mtd",
    "bootm",
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

POST_TX7_RECOVERY_GATE = "phase1.current-post-tx7-recovery=PROVEN"
EXPLICIT_ACK_GATE = "user.explicit_ack=PROVEN"


def fail(msg: str) -> int:
    print(json.dumps({"ok": False, "error": msg}, indent=2), file=sys.stderr)
    return 1


def load_policy(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    return json.loads(path.read_text(encoding="utf-8"))


def validate(policy: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if policy.get("schema") != "router-lyoko.control-policy/v1":
        errors.append("unexpected schema")
    if policy.get("classification") != "STAGED-SAFE-CONTROL-NO-DEVICE-WRITE":
        errors.append("unexpected classification")
    if policy.get("mode") != "observe_only":
        errors.append("policy must start in observe_only mode")

    invariants = policy.get("safety_invariants", {})
    for key in ("flash_write", "bootenv_write", "mtd_write", "module_mutation", "network_reconfigure", "secret_exfiltration"):
        if invariants.get(key) is not False:
            errors.append(f"safety invariant must be false: {key}")
    for key in ("requires_exact_image_hash", "requires_recovery_path"):
        if invariants.get(key) is not True:
            errors.append(f"safety invariant must be true: {key}")

    allowed = policy.get("current_allowed_actions", [])
    if not allowed:
        errors.append("must define current_allowed_actions")
    for action in allowed:
        if action.get("writes_device") is not False:
            errors.append(f"allowed action writes device: {action.get('id')}")
        haystack = json.dumps(action, ensure_ascii=False)
        for token in FORBIDDEN_IN_ALLOWED:
            if token in haystack:
                errors.append(f"forbidden token {token!r} in allowed action {action.get('id')}")

    blocked = policy.get("blocked_actions", [])
    blocked_ids = {action.get("id") for action in blocked}
    required_blocked = {
        "control.flash_promote",
        "control.radio_mutation",
        "control.quantenna_5g_start",
        "control.module_reload",
        "control.network_reconfigure",
    }
    missing = sorted(required_blocked - blocked_ids)
    if missing:
        errors.append(f"missing blocked actions: {', '.join(missing)}")
    for action in blocked:
        gates = action.get("blocked_until", [])
        if not gates:
            errors.append(f"blocked action lacks gates: {action.get('id')}")
        if action.get("id") in required_blocked and POST_TX7_RECOVERY_GATE not in gates:
            errors.append(f"blocked action lacks post-TX7 recovery gate: {action.get('id')}")
        if action.get("id") in required_blocked and EXPLICIT_ACK_GATE not in gates:
            errors.append(f"blocked action lacks explicit ACK gate: {action.get('id')}")

    quantenna = next((action for action in blocked if action.get("id") == "control.quantenna_5g_start"), {})
    quantenna_gates = set(quantenna.get("blocked_until", []))
    for gate in ("qdrv.same_boot_module_map=CAPTURED", "qdrv.tx7_misaligned_access_symbolized=PROVEN"):
        if gate not in quantenna_gates:
            errors.append(f"5 GHz start gate missing: {gate}")

    promotions = policy.get("promotion_gates", {})
    observe_to_control = promotions.get("observe_only_to_safe_control") or []
    if not observe_to_control:
        errors.append("missing observe_only_to_safe_control gates")
    elif "post-TX7 recovery PASS on current boot" not in observe_to_control:
        errors.append("observe_only_to_safe_control must require post-TX7 recovery PASS")
    if not promotions.get("safe_control_to_flash_candidate"):
        errors.append("missing safe_control_to_flash_candidate gates")

    return errors


def main(argv: list[str]) -> int:
    path = Path(argv[0]) if argv else POLICY
    try:
        policy = load_policy(path)
        errors = validate(policy)
    except Exception as exc:
        return fail(str(exc))
    if errors:
        return fail("; ".join(errors))
    print(json.dumps({"ok": True, "policy": str(path), "mode": policy["mode"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
