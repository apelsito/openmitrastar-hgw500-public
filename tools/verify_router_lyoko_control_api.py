#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://192.168.1.90/api/lyoko-control"
REQUIRED_BLOCKED = {
    "flash_promotion",
    "boot_environment_change",
    "mtd_write",
    "module_mutation",
    "radio_mutation",
    "network_change",
    "secret_rendering",
}
REQUIRED_GUARDS_FALSE = (
    "dashboard_executes_commands",
    "device_write",
    "flash_write",
    "bootenv_write",
    "mtd_write",
    "module_mutation",
    "network_reconfigure",
    "radio_control",
)
REQUIRED_SNAPSHOT_KEYS = (
    "control_policy",
    "event_taxonomy",
    "safe_mode",
    "goal_audit",
    "aelita_dialogue",
    "aelita_memory",
    "evidence_bindings",
    "telemetry_contract",
)


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    detail: str


def get_path(doc: dict[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def load_payload(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if args.input_json:
        path = Path(args.input_json)
        return json.loads(path.read_text(encoding="utf-8")), f"file:{path}"
    if args.stdin:
        return json.loads(sys.stdin.read()), "stdin"

    req = urllib.request.Request(
        args.url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "openmitrastar-router-lyoko-control-verifier/1",
        },
        method="GET",
    )
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=args.timeout) as response:
        body = response.read(args.max_bytes + 1)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if len(body) > args.max_bytes:
            raise RuntimeError(f"response exceeded max bytes: {args.max_bytes}")
        return (
            json.loads(body.decode("utf-8")),
            f"url:{args.url} status={response.status} elapsed_ms={elapsed_ms}",
        )


def validate(doc: dict[str, Any]) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check("ok.true", doc.get("ok") is True, "control contract verifier requires the successful GET contract"))
    checks.append(Check("schema", doc.get("schema") == "router-lyoko.control-contract/v1", "unexpected schema"))
    checks.append(
        Check(
            "classification",
            doc.get("classification") == "FAIL-CLOSED-OBSERVE-ONLY-NO-DEVICE-WRITE",
            "control contract must be fail-closed and no-write",
        )
    )
    checks.append(Check("mode.observe_only", doc.get("mode") == "observe_only", "mode must remain observe_only"))
    checks.append(Check("request.status.described", get_path(doc, "request.status") == "described", "request status must be described"))
    checks.append(Check("request.no_exec", get_path(doc, "request.executes") is False, "request must not execute"))
    checks.append(Check("request.no_write", get_path(doc, "request.writes_device") is False, "request must not write"))
    checks.append(Check("persona.aelita", get_path(doc, "persona.name") == "Aelita", "persona.name must be Aelita"))

    snapshot = doc.get("policy_snapshot")
    checks.append(Check("policy_snapshot.object", isinstance(snapshot, dict), "policy_snapshot must be an object"))
    if isinstance(snapshot, dict):
        for key in REQUIRED_SNAPSHOT_KEYS:
            value = snapshot.get(key)
            checks.append(
                Check(
                    f"policy_snapshot.{key}.shape",
                    isinstance(value, dict) and "present" in value and "bytes" in value,
                    f"{key} must expose present/bytes",
                )
            )
            if isinstance(value, dict):
                checks.append(
                    Check(
                        f"policy_snapshot.{key}.present",
                        value.get("present") is True,
                        f"{key} must be present in the staged lyoko-data snapshot",
                    )
                )
                checks.append(
                    Check(
                        f"policy_snapshot.{key}.bytes",
                        isinstance(value.get("bytes"), int) and value.get("bytes", 0) > 0,
                        f"{key} must have non-zero bytes in the staged lyoko-data snapshot",
                    )
                )

    allowed = doc.get("current_allowed_actions")
    checks.append(Check("allowed.array", isinstance(allowed, list) and bool(allowed), "allowed actions must be a non-empty list"))
    if isinstance(allowed, list):
        for action in allowed:
            checks.append(
                Check(
                    f"allowed.{action.get('id', 'unknown')}.no_write",
                    isinstance(action, dict) and action.get("writes_device") is False,
                    "allowed actions must be observe-only",
                )
            )

    blocked = set(doc.get("blocked_action_classes") or [])
    checks.append(
        Check(
            "blocked.required",
            REQUIRED_BLOCKED.issubset(blocked),
            f"blocked_action_classes must include {sorted(REQUIRED_BLOCKED)}",
        )
    )

    guards = doc.get("guards")
    checks.append(Check("guards.object", isinstance(guards, dict), "guards must be an object"))
    if isinstance(guards, dict):
        for guard in REQUIRED_GUARDS_FALSE:
            checks.append(
                Check(
                    f"guards.{guard}.false",
                    guards.get(guard) is False,
                    f"{guard} must be false",
                )
            )

    return checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read-only verifier for /api/lyoko-control.")
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", default=DEFAULT_URL)
    source.add_argument("--input-json")
    source.add_argument("--stdin", action="store_true")
    parser.add_argument("--timeout", type=float, default=3.0)
    parser.add_argument("--max-bytes", type=int, default=128 * 1024)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        doc, source = load_payload(args)
        checks = validate(doc)
        ok = all(check.ok for check in checks)
        report = {
            "ok": ok,
            "classification": "READONLY-CONTROL-CONTRACT-VERIFY-NO-CONTROL",
            "source": source,
            "checks": [asdict(check) for check in checks],
        }
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
        report = {
            "ok": False,
            "classification": "READONLY-CONTROL-CONTRACT-VERIFY-NO-CONTROL",
            "error": str(exc),
        }
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
