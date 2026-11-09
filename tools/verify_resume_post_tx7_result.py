#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import verify_router_lyoko_no_secrets as no_secrets


EXPECTED_SCHEMA = "openmitrastar.resume-post-tx7-5g-hang-result/v1"
EXPECTED_PASS_STATUS = "RESUME_POST_TX7_READY_FOR_2G_CLIENT_GATE"
EXPECTED_FAIL_STATUS = "RESUME_POST_TX7_NOT_READY"
RECOVERY_SCHEMA = "openmitrastar.post-tx7-recovery-result/v1"
LYOKO_REENTRY_SCHEMA = "router-lyoko.reentry-live-api-result/v1"
EXPECTED_FALSE_MUTATIONS = (
    "uart_opened",
    "module_reload",
    "network_reconfigure",
    "bootenv",
    "mtd",
    "flash",
)


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    detail: str


def load_json(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if raw.startswith(b"\xff\xfe") or raw.startswith(b"\xfe\xff"):
        return json.loads(raw.decode("utf-16"))
    return json.loads(raw.decode("utf-8-sig"))


def resolve_under(base: Path, candidate: Any) -> Path | None:
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    path = Path(candidate)
    if not path.is_absolute():
        path = base / path
    return path.resolve()


def is_under(path: Path, base: Path) -> bool:
    base = base.resolve()
    path = path.resolve()
    return path == base or base in path.parents


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def scan_no_secrets(label: str, path: Path | None, output_dir: Path) -> Check:
    if path is None or str(path) == ".":
        return Check(f"{label}.no_secrets", False, f"{label} path is missing")
    if not path.is_file() or not is_under(path, output_dir):
        return Check(f"{label}.no_secrets", False, f"{label} must exist under output_dir before secret scan")
    findings = no_secrets.scan_text(read_text(path), label)
    return Check(
        f"{label}.no_secrets",
        not findings,
        f"{label} must not contain concrete secrets; findings={len(findings)}",
    )


def validate(result: dict[str, Any], *, result_path: Path, output_dir_arg: Path | None = None) -> list[Check]:
    checks: list[Check] = []
    checks.append(Check("schema", result.get("schema") == EXPECTED_SCHEMA, f"schema must be {EXPECTED_SCHEMA}"))

    evidence = result.get("evidence")
    checks.append(Check("evidence.object", isinstance(evidence, dict), "evidence must be an object"))
    evidence = evidence if isinstance(evidence, dict) else {}

    recorded_output_dir = resolve_under(result_path.parent, evidence.get("output_dir"))
    output_dir = (output_dir_arg.resolve() if output_dir_arg else recorded_output_dir) or result_path.parent.resolve()
    checks.append(Check("evidence.output_dir.present", recorded_output_dir is not None, "evidence.output_dir must be present"))
    if recorded_output_dir is not None:
        checks.append(Check("evidence.output_dir.exists", recorded_output_dir.is_dir(), "evidence.output_dir must exist"))
        if output_dir_arg is not None:
            checks.append(
                Check(
                    "evidence.output_dir.matches_arg",
                    recorded_output_dir == output_dir,
                    "recorded output_dir must match --output-dir",
                )
            )

    evidence_paths: dict[str, Path] = {}
    for key in (
        "recovery_stdout",
        "recovery_stderr",
        "recovery_result_json",
        "lyoko_stdout",
        "lyoko_stderr",
        "lyoko_result_json",
        "tx11_boot_plan_stdout",
        "tx11_boot_plan_stderr",
        "tx11_2g_plan_stdout",
        "tx11_2g_plan_stderr",
        "result_json",
    ):
        raw = evidence.get(key)
        if raw in (None, "") and key.startswith("lyoko_") and result.get("lyoko_reentry_required") is False:
            continue
        path = resolve_under(output_dir, raw)
        evidence_paths[key] = path if path is not None else Path()
        checks.append(Check(f"evidence.{key}.present", path is not None, f"evidence.{key} must be present"))
        if path is None:
            continue
        checks.append(Check(f"evidence.{key}.under_output_dir", is_under(path, output_dir), f"{key} must stay under output_dir"))
        checks.append(Check(f"evidence.{key}.exists", path.is_file(), f"{key} must exist"))

    result_json_path = evidence_paths.get("result_json")
    if result_json_path and str(result_json_path) != ".":
        checks.append(
            Check(
                "evidence.result_json.self",
                result_json_path.resolve() == result_path.resolve(),
                "evidence.result_json must point to the validated result file",
            )
        )

    secret_scan_keys = [
        "recovery_stdout",
        "recovery_stderr",
        "tx11_boot_plan_stdout",
        "tx11_boot_plan_stderr",
        "tx11_2g_plan_stdout",
        "tx11_2g_plan_stderr",
    ]
    if result.get("lyoko_reentry_required") is True:
        secret_scan_keys.extend(["lyoko_stdout", "lyoko_stderr"])
    for key in secret_scan_keys:
        checks.append(scan_no_secrets(key, evidence_paths.get(key), output_dir))

    mutations = result.get("mutations")
    checks.append(Check("mutations.object", isinstance(mutations, dict), "mutations must be an object"))
    if isinstance(mutations, dict):
        for field in EXPECTED_FALSE_MUTATIONS:
            checks.append(Check(f"mutations.{field}.false", mutations.get(field) is False, f"{field} must be false"))

    recovery_exit = result.get("recovery_exit")
    lyoko_exit = result.get("lyoko_reentry_exit")
    tx11_boot_plan_exit = result.get("tx11_boot_plan_exit")
    tx11_2g_plan_exit = result.get("tx11_2g_plan_exit")
    lyoko_required = result.get("lyoko_reentry_required")
    recovery_pass = result.get("recovery_pass")
    lyoko_pass = result.get("lyoko_reentry_pass")
    tx11_boot_plan_ready = result.get("tx11_boot_plan_ready")
    tx11_2g_plan_ready = result.get("tx11_2g_plan_ready")
    checks.append(Check("recovery_exit.int", isinstance(recovery_exit, int), "recovery_exit must be an integer"))
    checks.append(Check("tx11_boot_plan_exit.int", isinstance(tx11_boot_plan_exit, int), "tx11_boot_plan_exit must be an integer"))
    checks.append(Check("tx11_2g_plan_exit.int", isinstance(tx11_2g_plan_exit, int), "tx11_2g_plan_exit must be an integer"))
    checks.append(Check("lyoko_reentry_required.bool", isinstance(lyoko_required, bool), "lyoko_reentry_required must be a boolean"))
    if lyoko_required:
        checks.append(Check("lyoko_reentry_exit.int", isinstance(lyoko_exit, int), "lyoko_reentry_exit must be an integer when required"))
    for key, value in (
        ("recovery_pass", recovery_pass),
        ("lyoko_reentry_pass", lyoko_pass),
        ("tx11_boot_plan_ready", tx11_boot_plan_ready),
        ("tx11_2g_plan_ready", tx11_2g_plan_ready),
        ("pass", result.get("pass")),
    ):
        checks.append(Check(f"{key}.bool", isinstance(value, bool), f"{key} must be a boolean"))

    recovery_doc = None
    recovery_result_path = evidence_paths.get("recovery_result_json")
    if recovery_result_path and recovery_result_path.is_file() and is_under(recovery_result_path, output_dir):
        try:
            recovery_doc = load_json(recovery_result_path)
            checks.append(Check("recovery_result.json", True, "recovery result JSON parses"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
            checks.append(Check("recovery_result.json", False, f"recovery result JSON must parse: {exc}"))
    else:
        checks.append(Check("recovery_result.json", False, "recovery result JSON path is missing, absent, or outside output_dir"))
    if recovery_doc is not None:
        checks.append(Check("recovery_result.schema", recovery_doc.get("schema") == RECOVERY_SCHEMA, f"recovery schema must be {RECOVERY_SCHEMA}"))
        checks.append(Check("recovery_result.pass.matches", recovery_doc.get("pass") == recovery_pass, "recovery_pass must match child result pass"))
        checks.append(Check("recovery_result.self_verified", recovery_doc.get("result_verifier_ok") is True, "child recovery result must be self-verified"))

    lyoko_doc = None
    if lyoko_required:
        lyoko_result_path = evidence_paths.get("lyoko_result_json")
        if lyoko_result_path and lyoko_result_path.is_file() and is_under(lyoko_result_path, output_dir):
            try:
                lyoko_doc = load_json(lyoko_result_path)
                checks.append(Check("lyoko_result.json", True, "lyoko result JSON parses"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                checks.append(Check("lyoko_result.json", False, f"lyoko result JSON must parse: {exc}"))
        else:
            checks.append(Check("lyoko_result.json", False, "lyoko result JSON path is missing, absent, or outside output_dir"))
        if lyoko_doc is not None:
            checks.append(Check("lyoko_result.schema", lyoko_doc.get("schema") == LYOKO_REENTRY_SCHEMA, f"lyoko schema must be {LYOKO_REENTRY_SCHEMA}"))
            checks.append(Check("lyoko_result.pass.matches", lyoko_doc.get("pass") == lyoko_pass, "lyoko_reentry_pass must match child result pass"))
            checks.append(Check("lyoko_result.self_verified", lyoko_doc.get("result_verifier_ok") is True, "child lyoko result must be self-verified"))
    else:
        checks.append(Check("lyoko_not_required.exit", lyoko_exit in (None, -1), "lyoko exit must be null/-1 when not required"))
        checks.append(Check("lyoko_not_required.pass", lyoko_pass is False, "lyoko pass must be false when not required"))

    tx11_boot_plan_text = ""
    tx11_boot_plan_path = evidence_paths.get("tx11_boot_plan_stdout")
    if tx11_boot_plan_path and tx11_boot_plan_path.is_file() and is_under(tx11_boot_plan_path, output_dir):
        tx11_boot_plan_text = read_text(tx11_boot_plan_path)
        checks.append(Check("tx11_boot_plan_stdout.readable", True, "TX11 boot evidence plan stdout is readable"))
    else:
        checks.append(Check("tx11_boot_plan_stdout.readable", False, "TX11 boot evidence plan stdout must exist under output_dir"))
    computed_tx11_boot_ready = "OMTX11_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1" in tx11_boot_plan_text
    checks.append(Check("tx11_boot_plan_ready.matches_stdout", tx11_boot_plan_ready == computed_tx11_boot_ready, "tx11_boot_plan_ready must match boot evidence plan marker"))

    tx11_2g_plan_text = ""
    tx11_2g_plan_path = evidence_paths.get("tx11_2g_plan_stdout")
    if tx11_2g_plan_path and tx11_2g_plan_path.is_file() and is_under(tx11_2g_plan_path, output_dir):
        tx11_2g_plan_text = read_text(tx11_2g_plan_path)
        checks.append(Check("tx11_2g_plan_stdout.readable", True, "TX11 2.4 GHz plan stdout is readable"))
    else:
        checks.append(Check("tx11_2g_plan_stdout.readable", False, "TX11 2.4 GHz plan stdout must exist under output_dir"))
    computed_tx11_2g_ready = "OM2G_TX11_GATE_PLAN_PASS=1" in tx11_2g_plan_text
    checks.append(Check("tx11_2g_plan_ready.matches_stdout", tx11_2g_plan_ready == computed_tx11_2g_ready, "tx11_2g_plan_ready must match gate plan marker"))

    computed_pass = (
        recovery_exit == 0
        and recovery_pass is True
        and tx11_boot_plan_exit == 0
        and computed_tx11_boot_ready
        and tx11_2g_plan_exit == 0
        and computed_tx11_2g_ready
        and (
            (lyoko_required is False)
            or (lyoko_exit == 0 and lyoko_pass is True)
        )
    )
    declared_pass = result.get("pass")
    checks.append(Check("pass.matches_children", declared_pass == computed_pass, "pass must match child gates and TX11 plans"))
    checks.append(
        Check(
            "status.matches_pass",
            (
                declared_pass is True
                and result.get("status") == EXPECTED_PASS_STATUS
            )
            or (
                declared_pass is False
                and result.get("status") == EXPECTED_FAIL_STATUS
            ),
            "status must be ready only for pass=true, otherwise not-ready",
        )
    )
    return checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate resume-post-TX7 result JSON against child gate evidence.")
    parser.add_argument("result_json", type=Path, help="Path to resume-result.json")
    parser.add_argument("--output-dir", type=Path, help="Expected evidence output directory.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    result_path = args.result_json.resolve()
    try:
        result = load_json(result_path)
        checks = validate(result, result_path=result_path, output_dir_arg=args.output_dir)
        ok = all(check.ok for check in checks)
        report = {
            "ok": ok,
            "classification": "READONLY-RESUME-POST-TX7-RESULT-VERIFY-NO-CONTROL",
            "result_json": str(result_path),
            "checks": [asdict(check) for check in checks],
            "note": "Findings never include the secret value; only evidence stream and count are reported.",
        }
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        report = {
            "ok": False,
            "classification": "READONLY-RESUME-POST-TX7-RESULT-VERIFY-NO-CONTROL",
            "result_json": str(result_path),
            "error": str(exc),
        }
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
