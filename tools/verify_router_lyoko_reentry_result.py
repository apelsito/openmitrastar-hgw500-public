#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


EXPECTED_SCHEMA = "router-lyoko.reentry-live-api-result/v1"
EXPECTED_PASS_STATUS = "LYOKO_REENTRY_PROVEN_READONLY"
EXPECTED_FAIL_STATUS = "LYOKO_REENTRY_NOT_PROVEN"
EXPECTED_FALSE_MUTATIONS = (
    "uart_opened",
    "ssh_command",
    "reboot",
    "network_reconfigure",
    "bootenv",
    "mtd",
    "flash",
)
LANES = {
    "state": {
        "exit_field": "state_verifier_exit",
        "ok_field": "state_verifier_ok",
        "stdout_key": "state_verifier_stdout",
        "stderr_key": "state_verifier_stderr",
        "classification": "READONLY-LIVE-VERIFY-NO-CONTROL",
    },
    "control": {
        "exit_field": "control_verifier_exit",
        "ok_field": "control_verifier_ok",
        "stdout_key": "control_verifier_stdout",
        "stderr_key": "control_verifier_stderr",
        "classification": "READONLY-CONTROL-CONTRACT-VERIFY-NO-CONTROL",
    },
    "static_index": {
        "exit_field": "static_index_verifier_exit",
        "ok_field": "static_index_verifier_ok",
        "stdout_key": "static_index_verifier_stdout",
        "stderr_key": "static_index_verifier_stderr",
        "classification": "READONLY-STATIC-INDEX-VERIFY-NO-CONTROL",
    },
    "served_files": {
        "exit_field": "served_files_verifier_exit",
        "ok_field": "served_files_verifier_ok",
        "stdout_key": "served_files_verifier_stdout",
        "stderr_key": "served_files_verifier_stderr",
        "classification": "READONLY-SERVED-WEB-FILES-VERIFY-NO-CONTROL",
    },
    "served_no_secrets": {
        "exit_field": "served_no_secrets_verifier_exit",
        "ok_field": "served_no_secrets_verifier_ok",
        "stdout_key": "served_no_secrets_verifier_stdout",
        "stderr_key": "served_no_secrets_verifier_stderr",
        "classification": "READONLY-SERVED-NO-SECRETS-VERIFY-NO-CONTROL",
    },
}
REQUIRED_SERVED_FILES_CHECKS = {
    "served./lyoko-data/safe-mode.json.tx11_requires_exact_boot": (
        "served_files.stdout.safe_mode_tx11_requires_exact_boot",
        "served_files stdout must prove safe-mode requires exact TX11 RAM boot evidence",
    ),
    "served./lyoko-data/safe-mode.json.tx11_boot_collector_command": (
        "served_files.stdout.safe_mode_tx11_boot_collector_command",
        "served_files stdout must prove the TX11 boot evidence collector is displayed",
    ),
    "served./lyoko-data/safe-mode.json.tx11_requires_boot_evidence_json": (
        "served_files.stdout.safe_mode_tx11_requires_boot_evidence_json",
        "served_files stdout must prove safe-mode requires Tx11BootEvidenceJson",
    ),
    "served./lyoko-data/safe-mode.json.tx11_command_boot_evidence_json": (
        "served_files.stdout.safe_mode_tx11_command_boot_evidence_json",
        "served_files stdout must prove the TX11 command displays -Tx11BootEvidenceJson",
    ),
    "served./lyoko.js.fetches_safe_mode_contract": (
        "served_files.stdout.lyoko_js_fetches_safe_mode_contract",
        "served_files stdout must prove lyoko.js fetches /lyoko-data/safe-mode.json",
    ),
    "served./lyoko.js.tx11_boot_evidence_guard_visible": (
        "served_files.stdout.lyoko_js_tx11_boot_evidence_guard_visible",
        "served_files stdout must prove lyoko.js visibly guards TX11 with Tx11BootEvidenceJson",
    ),
}


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
        "state_verifier_stdout",
        "state_verifier_stderr",
        "control_verifier_stdout",
        "control_verifier_stderr",
        "static_index_verifier_stdout",
        "static_index_verifier_stderr",
        "served_files_verifier_stdout",
        "served_files_verifier_stderr",
        "served_no_secrets_verifier_stdout",
        "served_no_secrets_verifier_stderr",
        "result_json",
    ):
        path = resolve_under(output_dir, evidence.get(key))
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

    mutations = result.get("mutations")
    checks.append(Check("mutations.object", isinstance(mutations, dict), "mutations must be an object"))
    if isinstance(mutations, dict):
        for field in EXPECTED_FALSE_MUTATIONS:
            checks.append(Check(f"mutations.{field}.false", mutations.get(field) is False, f"{field} must be false"))

    lane_results: dict[str, dict[str, Any]] = {}
    for lane, spec in LANES.items():
        exit_value = result.get(spec["exit_field"])
        lane_ok = result.get(spec["ok_field"])
        checks.append(Check(f"{lane}.exit.int", isinstance(exit_value, int), f"{spec['exit_field']} must be an integer"))
        checks.append(Check(f"{lane}.ok.bool", isinstance(lane_ok, bool), f"{spec['ok_field']} must be a boolean"))

        stdout_path = evidence_paths.get(spec["stdout_key"])
        stdout_doc: dict[str, Any] | None = None
        if stdout_path and stdout_path.is_file() and is_under(stdout_path, output_dir):
            try:
                stdout_doc = load_json(stdout_path)
                checks.append(Check(f"{lane}.stdout.json", True, "stdout JSON parses"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                checks.append(Check(f"{lane}.stdout.json", False, f"stdout JSON must parse: {exc}"))
        else:
            checks.append(Check(f"{lane}.stdout.json", False, "stdout JSON path is missing, absent, or outside output_dir"))

        if stdout_doc is not None:
            stdout_ok = stdout_doc.get("ok")
            checks.append(Check(f"{lane}.stdout.ok.bool", isinstance(stdout_ok, bool), "stdout ok must be a boolean"))
            checks.append(
                Check(
                    f"{lane}.stdout.ok.matches_result",
                    stdout_ok == lane_ok,
                    f"stdout ok must match {spec['ok_field']}",
                )
            )
            checks.append(
                Check(
                    f"{lane}.stdout.classification",
                    stdout_doc.get("classification") == spec["classification"],
                    f"stdout classification must be {spec['classification']}",
                )
            )
            if lane == "served_files":
                stdout_checks = stdout_doc.get("checks")
                checks.append(
                    Check(
                        "served_files.stdout.checks.list",
                        isinstance(stdout_checks, list),
                        "served_files stdout checks must be a list",
                    )
                )
                stdout_check_ok: dict[str, bool] = {}
                if isinstance(stdout_checks, list):
                    for item in stdout_checks:
                        if isinstance(item, dict) and isinstance(item.get("id"), str):
                            stdout_check_ok[item["id"]] = item.get("ok") is True
                served_files_success = exit_value == 0 and lane_ok is True and stdout_doc.get("ok") is True
                for required_id, (check_id, detail) in REQUIRED_SERVED_FILES_CHECKS.items():
                    checks.append(
                        Check(
                            check_id,
                            (not served_files_success) or stdout_check_ok.get(required_id) is True,
                            detail,
                        )
                    )
        lane_results[lane] = {
            "exit_zero": exit_value == 0,
            "result_ok": lane_ok is True,
            "stdout_ok": stdout_doc.get("ok") is True if stdout_doc is not None else False,
        }

    computed_pass = all(
        lane["exit_zero"] and lane["result_ok"] and lane["stdout_ok"]
        for lane in lane_results.values()
    )
    declared_pass = result.get("pass")
    checks.append(Check("pass.bool", isinstance(declared_pass, bool), "pass must be a boolean"))
    checks.append(Check("pass.matches_lanes", declared_pass == computed_pass, "pass must equal all lane exits/stdout/result ok"))
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
            "status must be proven only for pass=true, otherwise not-proven",
        )
    )
    return checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a Router-Lyoko reentry result JSON against its verifier evidence files."
    )
    parser.add_argument("result_json", type=Path, help="Path to lyoko-reentry-result.json")
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
            "classification": "READONLY-REENTRY-RESULT-VERIFY-NO-CONTROL",
            "result_json": str(result_path),
            "checks": [asdict(check) for check in checks],
        }
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        report = {
            "ok": False,
            "classification": "READONLY-REENTRY-RESULT-VERIFY-NO-CONTROL",
            "result_json": str(result_path),
            "error": str(exc),
        }
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
