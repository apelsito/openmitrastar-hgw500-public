#!/usr/bin/env python3
"""Incremental, offline-only readiness assessment for an OpenMitraStar candidate.

This script deliberately reuses the pinned F2 32/32 report instead of hashing the
16 MiB dump again.  It reads only small certification files, current component
artifacts, manifests, and future candidate evidence.  It contains no serial,
network, MTD, environment-write, or flash operation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from make_spi_slot_image import validate_candidate
from openmitrastar_flash_backup_preflight import validate_current_read_attestation


DEFAULT_CONTRACT = Path("work/mission-state/F2_FLASH_CANDIDATE_INPUT_CONTRACT.json")
DEFAULT_JSON = Path("work/mission-state/F2_FLASH_CANDIDATE_READINESS.json")
DEFAULT_MD = Path("work/mission-state/F2_FLASH_CANDIDATE_READINESS.md")


@dataclass
class Gate:
    gate_id: str
    passed: bool
    blocking: bool
    status: str
    detail: str
    required_input: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": self.gate_id,
            "passed": self.passed,
            "blocking": self.blocking,
            "status": self.status,
            "detail": self.detail,
            "required_input": self.required_input,
        }


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"expected JSON object: {path}")
    return raw


def read_text_auto(path: Path) -> str:
    blob = path.read_bytes()
    if blob.startswith((b"\xff\xfe", b"\xfe\xff")):
        return blob.decode("utf-16")
    if blob[:4096].count(b"\0") > max(8, len(blob[:4096]) // 8):
        return blob.decode("utf-16-le", errors="replace")
    return blob.decode("utf-8", errors="replace")


def resolved(workspace: Path, value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else workspace / path


def pinned_file_gate(
    gate_id: str,
    workspace: Path,
    spec: dict[str, Any],
    *,
    blocking: bool,
) -> tuple[Gate, Path | None]:
    path = resolved(workspace, spec["path"])
    if not path.is_file():
        return (
            Gate(gate_id, False, blocking, "MISSING", f"missing {path}", str(path)),
            None,
        )
    observed = sha256(path)
    expected = spec["sha256"]
    return (
        Gate(
            gate_id,
            observed == expected,
            blocking,
            "PASS" if observed == expected else "DRIFT",
            f"path={path} sha256={observed} expected={expected}",
            None if observed == expected else str(path),
        ),
        path,
    )


def validate_bundle(workspace: Path, manifest_path: Path) -> tuple[bool, str]:
    manifest = read_json(manifest_path)
    bundle_root = manifest_path.parent
    failures: list[str] = []
    for artifact in manifest.get("artifacts", []):
        path = bundle_root / artifact["path"]
        if not path.is_file():
            failures.append(f"missing:{artifact['path']}")
            continue
        observed = sha256(path)
        if observed != artifact["sha256"]:
            failures.append(f"hash:{artifact['path']}:{observed}")
    expected_class = "RAM-ONLY-NO-FLASH"
    if manifest.get("classification") != expected_class:
        failures.append(f"classification:{manifest.get('classification')}")
    if manifest.get("candidate_eligible") is not False:
        failures.append("candidate_eligible_not_false")
    return not failures, ";".join(failures) if failures else "all bundle hashes PASS; RAM-only classification preserved"


def assess(workspace: Path, contract_path: Path) -> dict[str, Any]:
    contract = read_json(contract_path)
    gates: list[Gate] = []

    baseline_spec = contract["cached_f2"]["baseline"]
    report_spec = contract["cached_f2"]["report"]
    baseline_gate, baseline_path = pinned_file_gate(
        "cached-f2-baseline", workspace, baseline_spec, blocking=True
    )
    report_gate, report_path = pinned_file_gate(
        "cached-f2-report", workspace, report_spec, blocking=True
    )
    gates.extend((baseline_gate, report_gate))

    cached_f2_ok = False
    cached_f2_detail = "cached report unavailable"
    baseline: dict[str, Any] | None = None
    if baseline_path and report_path and baseline_gate.passed and report_gate.passed:
        baseline = read_json(baseline_path)
        report = read_json(report_path)
        passed_count = sum(bool(item.get("passed")) for item in report.get("gates", []))
        expected_count = contract["cached_f2"]["expected_passed_gates"]
        cached_f2_ok = (
            report.get("backup_certified") is True
            and report.get("read_only") is True
            and report.get("hardware_access") is False
            and passed_count == expected_count == len(report.get("gates", []))
        )
        cached_f2_detail = (
            f"cached={passed_count}/{len(report.get('gates', []))} "
            f"backup_certified={report.get('backup_certified')} audit_replayed=false"
        )
    gates.append(
        Gate(
            "cached-f2-32-of-32",
            cached_f2_ok,
            True,
            "PASS" if cached_f2_ok else "INVALID",
            cached_f2_detail,
            None if cached_f2_ok else str(report_path or report_spec["path"]),
        )
    )

    rollback_contract = contract.get("safety_rollback_contract")
    if rollback_contract is not None:
        rollback_failures: list[str] = []
        current_unit = contract.get("current_unit_recovery_contract")
        if isinstance(current_unit, dict):
            backup_spec = current_unit.get("backup_manifest", {})
            backup_path = resolved(workspace, backup_spec.get("path", ""))
            if not backup_path.is_file() or sha256(backup_path) != backup_spec.get("sha256"):
                rollback_failures.append("current-unit-backup-manifest-drift")
            else:
                backup = read_json(backup_path)
                if backup.get("physical_image", {}).get("sha256") != backup_spec.get("physical_image_sha256"):
                    rollback_failures.append("current-unit-physical-image-drift")
                parts = {item.get("name"): item for item in backup.get("partitions", [])}
                safety = parts.get("linux_safety", {})
                if safety.get("sha256") != rollback_contract.get("rollback_sha256"):
                    rollback_failures.append("current-unit-rollback-hash-mismatch")
                safety_path = backup_path.parent / str(safety.get("file", ""))
                if (
                    not safety_path.is_file()
                    or safety_path.stat().st_size != rollback_contract.get("rollback_size")
                    or sha256(safety_path) != rollback_contract.get("rollback_sha256")
                ):
                    rollback_failures.append("current-unit-rollback-artifact-drift")
            manual = current_unit.get("manual_uart_rollback", {})
            manual_path = resolved(workspace, manual.get("path", ""))
            if not manual_path.is_file() or sha256(manual_path) != manual.get("sha256"):
                rollback_failures.append("manual-uart-rollback-hash-drift")
            else:
                text = read_text_auto(manual_path)
                missing = [marker for marker in manual.get("required_markers", []) if marker not in text]
                if missing:
                    rollback_failures.append(f"manual-uart-rollback-missing:{missing}")
            if rollback_contract.get("environment_write_forbidden") is not True:
                rollback_failures.append("environment-write-not-forbidden")
            if rollback_contract.get("selection_mode") != "manual-uart-ATGO":
                rollback_failures.append("manual-uart-selection-mode-missing")
        elif baseline is None:
            rollback_failures.append("baseline-unavailable")
        else:
            flash_plan = baseline.get("flash_plan", {})
            partitions = {
                item.get("name"): item for item in baseline.get("partitions", [])
            }
            rollback_name = rollback_contract["rollback_slot"]
            target_name = rollback_contract["target_slot"]
            rollback_partition = partitions.get(rollback_name, {})
            if flash_plan.get("target_slot") != target_name:
                rollback_failures.append("target-slot-mismatch")
            if flash_plan.get("rollback_slot") != rollback_name:
                rollback_failures.append("rollback-slot-mismatch")
            if rollback_name not in flash_plan.get("preserve", []):
                rollback_failures.append("rollback-slot-not-preserved")
            if rollback_partition.get("policy") != "rollback-slot":
                rollback_failures.append("rollback-policy-mismatch")
            if rollback_partition.get("sha256") != rollback_contract["rollback_sha256"]:
                rollback_failures.append("rollback-hash-mismatch")
            if rollback_partition.get("size") != rollback_contract["rollback_size"]:
                rollback_failures.append("rollback-size-mismatch")
        rollback_ok = not rollback_failures
        gates.append(
            Gate(
                "safety-rollback-preserved",
                rollback_ok,
                True,
                "PASS" if rollback_ok else "INVALID",
                (
                    f"target={rollback_contract['target_slot']} "
                    f"rollback={rollback_contract['rollback_slot']} "
                    f"sha256={rollback_contract['rollback_sha256']} "
                    f"selection={rollback_contract.get('selection_mode', 'environment')} "
                    f"failures={rollback_failures}"
                ),
                None if rollback_ok else str(
                    resolved(workspace, current_unit.get("backup_manifest", {}).get("path", ""))
                    if isinstance(current_unit, dict)
                    else (baseline_path or baseline_spec["path"])
                ),
            )
        )

    components = contract["current_components"]
    ram_gate, ram_path = pinned_file_gate(
        "ram-kernel-component", workspace, components["ram_kernel"], blocking=False
    )
    if ram_gate.passed and ram_path:
        try:
            info = validate_candidate(ram_path.read_bytes())
            ram_gate.detail += (
                f" uimage={info['name']} arch={info['arch']} "
                f"hcrc={info['hcrc_ok']} dcrc={info['dcrc_ok']} classification=RAM-ONLY"
            )
        except ValueError as exc:
            ram_gate.passed = False
            ram_gate.status = "INVALID"
            ram_gate.detail += f" format_error={exc}"
    gates.append(ram_gate)

    bundle_spec = components["realtek_bundle"]
    bundle_manifest_path = resolved(workspace, bundle_spec["manifest"])
    if not bundle_manifest_path.is_file():
        gates.append(
            Gate(
                "realtek-ram-bundle",
                False,
                False,
                "MISSING",
                f"missing {bundle_manifest_path}",
                str(bundle_manifest_path),
            )
        )
    else:
        observed_manifest_sha = sha256(bundle_manifest_path)
        bundle_ok, bundle_detail = validate_bundle(workspace, bundle_manifest_path)
        bundle_ok = bundle_ok and observed_manifest_sha == bundle_spec["manifest_sha256"]
        gates.append(
            Gate(
                "realtek-ram-bundle",
                bundle_ok,
                False,
                "PASS" if bundle_ok else "DRIFT",
                f"manifest_sha256={observed_manifest_sha}; {bundle_detail}",
                None if bundle_ok else str(bundle_manifest_path),
            )
        )

    rootfs_spec = components["product_rootfs"]
    rootfs_path = resolved(workspace, rootfs_spec["path"])
    rootfs_manifest_path = resolved(workspace, rootfs_spec["manifest"])
    rootfs_ok = rootfs_path.is_file() and rootfs_manifest_path.is_file()
    rootfs_detail_parts: list[str] = []
    if rootfs_ok:
        observed_rootfs = sha256(rootfs_path)
        observed_manifest = sha256(rootfs_manifest_path)
        rootfs_manifest = read_json(rootfs_manifest_path)
        magic_ok = rootfs_path.read_bytes()[:4] == b"hsqs"
        rootfs_ok = (
            observed_rootfs == rootfs_spec["sha256"]
            and observed_manifest == rootfs_spec["manifest_sha256"]
            and magic_ok
            and rootfs_manifest.get("candidate_eligible") is False
            and rootfs_manifest.get("classification") == rootfs_spec["classification"]
        )
        rootfs_detail_parts.extend(
            (
                f"rootfs_sha256={observed_rootfs}",
                f"manifest_sha256={observed_manifest}",
                f"squashfs_magic={magic_ok}",
                f"classification={rootfs_manifest.get('classification')}",
            )
        )
    else:
        rootfs_detail_parts.append(f"missing rootfs={rootfs_path} or manifest={rootfs_manifest_path}")
    gates.append(
        Gate(
            "product-rootfs-component",
            rootfs_ok,
            False,
            "PASS" if rootfs_ok else "MISSING_OR_DRIFT",
            "; ".join(rootfs_detail_parts),
            None if rootfs_ok else str(rootfs_path),
        )
    )

    runtime = components["realtek_runtime"]
    transcript = resolved(workspace, runtime["probe_transcript"])
    uart_log = resolved(workspace, runtime["uart_log"])
    runtime_ok = transcript.is_file() and uart_log.is_file()
    runtime_text = ""
    if runtime_ok:
        runtime_ok = (
            sha256(transcript) == runtime["probe_transcript_sha256"]
            and sha256(uart_log) == runtime["uart_log_sha256"]
        )
        runtime_text = read_text_auto(transcript) + "\n" + read_text_auto(uart_log)
        missing = [marker for marker in runtime["required_markers"] if marker not in runtime_text]
        runtime_ok = runtime_ok and not missing
    else:
        missing = list(runtime["required_markers"])
    known_gaps = [marker for marker in runtime["known_gap_markers"] if marker in runtime_text]
    gates.append(
        Gate(
            "realtek-probe-runtime-evidence",
            runtime_ok,
            False,
            "PASS_WITH_GAPS" if runtime_ok and known_gaps else ("PASS" if runtime_ok else "MISSING_OR_DRIFT"),
            f"missing_markers={missing}; known_gaps={known_gaps}; proves probe only, not product image",
            None if runtime_ok else f"{transcript};{uart_log}",
        )
    )

    inputs = contract["required_candidate_inputs"]
    candidate_dir = resolved(workspace, inputs["directory"])
    candidate_path = candidate_dir / inputs["candidate"]
    manifest_path = candidate_dir / inputs["candidate_manifest"]
    current_read_path = candidate_dir / inputs["current_read_attestation"]
    equivalence_path = candidate_dir / inputs["ram_equivalence"]

    candidate_sha: str | None = None
    candidate_format: dict[str, Any] | None = None
    if candidate_path.is_file():
        candidate_sha = sha256(candidate_path)
        try:
            candidate_format = validate_candidate(candidate_path.read_bytes())
            candidate_ok = (
                candidate_path.stat().st_size <= contract["device"]["slot_size"]
                and candidate_format.get("hcrc_ok") is True
                and candidate_format.get("dcrc_ok") is True
                and candidate_format.get("arch") == "0x13"
            )
            candidate_detail = (
                f"sha256={candidate_sha} size={candidate_path.stat().st_size} "
                f"name={candidate_format['name']} arch={candidate_format['arch']} "
                f"hcrc={candidate_format['hcrc_ok']} "
                f"dcrc={candidate_format['dcrc_ok']}"
            )
        except ValueError as exc:
            candidate_ok = False
            candidate_detail = f"format_error={exc}"
    else:
        candidate_ok = False
        candidate_detail = f"missing integrated Linux 5.10 candidate webformat: {candidate_path}"
    gates.append(
        Gate(
            "integrated-persistent-candidate",
            candidate_ok,
            True,
            "PASS" if candidate_ok else "MISSING",
            candidate_detail,
            None if candidate_ok else str(candidate_path),
        )
    )

    manifest_ok = False
    profile_ok = False
    manifest_detail = f"missing {manifest_path}"
    profile_detail = f"missing {manifest_path}"
    candidate_manifest: dict[str, Any] | None = None
    if manifest_path.is_file():
        candidate_manifest = read_json(manifest_path)
        manifest_contract = contract["candidate_manifest_contract"]
        target = candidate_manifest.get("target", {})
        artifact = candidate_manifest.get("artifact", {})
        components_in_manifest = candidate_manifest.get("components", {})
        static_checks = candidate_manifest.get("static_checks", {})
        missing_component_keys = [
            key for key in manifest_contract["required_component_keys"] if not components_in_manifest.get(key)
        ]
        component_mismatches = {
            key: {
                "expected": expected,
                "observed": components_in_manifest.get(key),
            }
            for key, expected in manifest_contract["required_component_values"].items()
            if components_in_manifest.get(key) != expected
        }
        failed_static = [
            key for key in manifest_contract["required_static_checks"] if static_checks.get(key) != "PASS"
        ]
        required_capabilities = manifest_contract.get("required_capability_values", {})
        observed_capabilities = candidate_manifest.get("capabilities", {})
        capability_mismatches = {
            key: {"expected": expected, "observed": observed_capabilities.get(key)}
            for key, expected in required_capabilities.items()
            if observed_capabilities.get(key) != expected
        }
        required_claims = manifest_contract.get("required_completion_claims", {})
        observed_claims = candidate_manifest.get("completion_claims", {})
        claim_mismatches = {
            key: {"expected": expected, "observed": observed_claims.get(key)}
            for key, expected in required_claims.items()
            if observed_claims.get(key) != expected
        }
        manifest_ok = (
            candidate_manifest.get("schema") == manifest_contract["schema"]
            and candidate_manifest.get("classification") == manifest_contract["classification"]
            and candidate_manifest.get("candidate_eligible") is True
            and target == manifest_contract["required_target"]
            and candidate_sha is not None
            and artifact.get("sha256") == candidate_sha
            and artifact.get("size") == candidate_path.stat().st_size
            and not missing_component_keys
            and not component_mismatches
            and not failed_static
        )
        manifest_detail = (
            f"schema={candidate_manifest.get('schema')} classification={candidate_manifest.get('classification')} "
            f"candidate_eligible={candidate_manifest.get('candidate_eligible')} target={target} "
            f"missing_component_keys={missing_component_keys} "
            f"component_mismatches={component_mismatches} failed_static={failed_static}"
        )
        profile_ok = (
            candidate_manifest.get("profile") == manifest_contract.get("required_profile")
            and candidate_manifest.get("scope") == manifest_contract.get("required_scope")
            and not capability_mismatches
            and not claim_mismatches
        ) if "required_profile" in manifest_contract else True
        profile_detail = (
            f"profile={candidate_manifest.get('profile')} "
            f"scope={candidate_manifest.get('scope')} "
            f"capability_mismatches={capability_mismatches} "
            f"claim_mismatches={claim_mismatches}"
        )
    gates.append(
        Gate(
            "candidate-manifest-contract",
            manifest_ok,
            True,
            "PASS" if manifest_ok else "MISSING_OR_INCOMPLETE",
            manifest_detail,
            None if manifest_ok else str(manifest_path),
        )
    )
    if "required_profile" in contract["candidate_manifest_contract"]:
        gates.append(
            Gate(
                "candidate-profile-boundary",
                profile_ok,
                True,
                "PASS" if profile_ok else "PROFILE_MISMATCH",
                profile_detail,
                None if profile_ok else str(manifest_path),
            )
        )

    current_read_ok = False
    current_read_detail = f"missing {current_read_path}"
    if current_read_path.is_file() and baseline is not None:
        current_read_ok, current_read_detail = validate_current_read_attestation(
            current_read_path, baseline, contract["device"]["target_slot"],
            contract.get("current_unit_recovery_contract"),
        )
    gates.append(
        Gate(
            "fresh-current-flash-read",
            current_read_ok,
            True,
            "PASS" if current_read_ok else "MISSING_OR_INVALID",
            current_read_detail,
            None if current_read_ok else str(current_read_path),
        )
    )

    equivalence_ok = False
    equivalence_detail = f"missing {equivalence_path}"
    if equivalence_path.is_file() and candidate_sha is not None:
        equivalence = read_json(equivalence_path)
        equivalence_contract = contract["ram_equivalence_contract"]
        checks = equivalence.get("checks", {})
        failed_checks = [
            key for key in equivalence_contract["required_checks"] if checks.get(key) != "PASS"
        ]
        evidence_files = equivalence.get("evidence", [])
        evidence_failures: list[str] = []
        for item in evidence_files:
            evidence_path = resolved(workspace, item.get("path", ""))
            if not evidence_path.is_file() or sha256(evidence_path) != item.get("sha256"):
                evidence_failures.append(str(evidence_path))
        equivalence_ok = (
            equivalence.get("schema") == equivalence_contract["schema"]
            and equivalence.get("status") == equivalence_contract["status"]
            and equivalence.get("candidate_sha256") == candidate_sha
            and not failed_checks
            and bool(evidence_files)
            and not evidence_failures
        )
        equivalence_detail = (
            f"status={equivalence.get('status')} candidate_sha256={equivalence.get('candidate_sha256')} "
            f"failed_checks={failed_checks} evidence_failures={evidence_failures}"
        )
    gates.append(
        Gate(
            "same-candidate-ram-equivalence",
            equivalence_ok,
            True,
            "PASS" if equivalence_ok else "MISSING_OR_INVALID",
            equivalence_detail,
            None if equivalence_ok else str(equivalence_path),
        )
    )

    blocking_gates = [gate for gate in gates if gate.blocking]
    candidate_eligible = all(gate.passed for gate in blocking_gates)
    missing_inputs = [
        {
            "gate": gate.gate_id,
            "required_input": gate.required_input,
            "detail": gate.detail,
        }
        for gate in blocking_gates
        if not gate.passed
    ]
    return {
        "schema": "openmitrastar.flash-candidate-readiness/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "assessment_complete": True,
        "read_only": True,
        "offline_only": True,
        "hardware_access": False,
        "audit_replayed": False,
        "cached_f2_reused": True,
        "profile": contract["profile"],
        "candidate_eligible": candidate_eligible,
        "flash_ready": False,
        "candidate_sha256": candidate_sha,
        "candidate_format": candidate_format,
        "gates": [gate.as_dict() for gate in gates],
        "missing_inputs": missing_inputs,
        "single_command": (
            "python tools/openmitrastar_flash_candidate_readiness.py"
        ),
    }


def render_markdown(report: dict[str, Any]) -> str:
    profile = report.get("profile", "openmitrastar-candidate")
    lines = [
        f"# {profile} candidate readiness",
        "",
        f"Generated: `{report['generated_at']}`  ",
        "Mode: **offline/read-only**; cached F2 reused; 16 MiB audit not replayed.",
        "",
        "## Verdict",
        "",
        f"- `assessment_complete={str(report['assessment_complete']).lower()}`",
        f"- `candidate_eligible={str(report['candidate_eligible']).lower()}`",
        f"- `flash_ready={str(report['flash_ready']).lower()}`",
        f"- `audit_replayed={str(report['audit_replayed']).lower()}`",
        "",
        "## Gates",
        "",
        "| Gate | Blocking | Status | Detail |",
        "|---|---:|---|---|",
    ]
    for gate in report["gates"]:
        detail = gate["detail"].replace("|", "\\|")
        lines.append(
            f"| `{gate['id']}` | `{str(gate['blocking']).lower()}` | **{gate['status']}** | {detail} |"
        )
    lines.extend(("", "## Exact missing inputs", ""))
    if report["missing_inputs"]:
        for item in report["missing_inputs"]:
            lines.append(
                f"- `{item['gate']}` → `{item['required_input']}`: {item['detail']}"
            )
    else:
        lines.append("- None. Candidate contract is complete; run the separate final flash preflight.")
    lines.extend(
        (
            "",
            "## Manifest contract",
            "",
            "The exact schema, pinned component hashes, static checks and RAM-equivalence checks are bound by ",
            "the input contract used in the command above.",
            "A valid manifest must identify `HGW-500BNA-QCv2/A2`, target only `linux_live`, ",
            "bind the candidate file hash/size, bind the current RAM-kernel/rootfs/Realtek hashes, ",
            "and mark every declared static check `PASS`.",
            "",
            "## One command",
            "",
            "```powershell",
            report["single_command"],
            "```",
            "",
            "This command assesses readiness only. It has no flash or hardware path.",
            "",
        )
    )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--json-out", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--md-out", type=Path, default=DEFAULT_MD)
    parser.add_argument("--strict", action="store_true", help="return 2 unless candidate_eligible=true")
    args = parser.parse_args(argv)
    workspace = args.workspace.resolve()
    contract_path = args.contract if args.contract.is_absolute() else workspace / args.contract
    report = assess(workspace, contract_path)
    json_out = args.json_out if args.json_out.is_absolute() else workspace / args.json_out
    md_out = args.md_out if args.md_out.is_absolute() else workspace / args.md_out
    report["single_command"] = (
        "python tools/openmitrastar_flash_candidate_readiness.py "
        f"--contract {args.contract} --json-out {args.json_out} --md-out {args.md_out}"
    )
    json_out.parent.mkdir(parents=True, exist_ok=True)
    md_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    md_out.write_text(render_markdown(report), encoding="utf-8")
    print(
        f"assessment_complete={str(report['assessment_complete']).lower()} "
        f"candidate_eligible={str(report['candidate_eligible']).lower()} "
        f"flash_ready={str(report['flash_ready']).lower()} "
        f"audit_replayed={str(report['audit_replayed']).lower()} "
        f"missing_inputs={len(report['missing_inputs'])}"
    )
    for item in report["missing_inputs"]:
        print(f"MISSING {item['gate']} -> {item['required_input']}")
    return 2 if args.strict and not report["candidate_eligible"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
