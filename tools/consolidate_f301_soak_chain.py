#!/usr/bin/env python3
"""Consolidate an F301 soak/resume chain without touching hardware.

The source directories are immutable evidence. This tool reads a stable
snapshot, validates the continuation lineage, deduplicates inherited PASS
cycles, and writes a derived JSON/Markdown summary atomically.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SUMMARY_SCHEMA = "openmitrastar.f301-soak-chain-summary/v1"
PLAN_SCHEMA = "openmitrastar.f301-sequential-dual-radio-soak-plan/v1"
CHECKPOINT_SCHEMA = "openmitrastar.f301-sequential-dual-radio-soak-checkpoint/v1"
CYCLE_SCHEMA = "openmitrastar.f301-sequential-dual-radio-cycle/v1"
SEED_SCHEMA = "openmitrastar.f301-soak-continuation-seed/v1"

HARNESS_MARKERS = (
    "timeout",
    "timed out",
    "rc=124",
    "ssh",
    "collector",
    "retry",
    "transient",
    "arness",
)
HARDWARE_MARKERS = (
    "fatal",
    "disconnect",
    "router health",
    "radio unhealthy",
    "association lost",
    "wlan error",
    "dma error",
    "thermal",
    "watchdog",
)


class ConsolidationError(RuntimeError):
    pass


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode(
        "ascii"
    )


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json_bytes(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ConsolidationError(f"cannot read {path}: {exc}") from exc
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConsolidationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConsolidationError(f"expected JSON object in {path}")
    return value, data


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.parent / f".{path.name}.{os.getpid()}.tmp"
    try:
        with temporary.open("wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True).encode("ascii") + b"\n")


def normalized_path(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=True)))


def _json_paths(directory: Path) -> list[Path]:
    paths = [path for path in directory.rglob("*.json") if path.is_file()]
    return sorted(paths, key=lambda path: path.relative_to(directory).as_posix())


def _snapshot_once(directory: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    documents: dict[str, dict[str, Any]] = {}
    evidence: list[dict[str, Any]] = []
    for path in _json_paths(directory):
        relative = path.relative_to(directory).as_posix()
        value, data = read_json_bytes(path)
        documents[relative] = value
        evidence.append({"path": relative, "size": len(data), "sha256": sha256_bytes(data)})
    return documents, evidence


def stable_snapshot(directory: Path, attempts: int = 5) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if not directory.is_dir():
        raise ConsolidationError(f"source directory not found: {directory}")
    previous: tuple[dict[str, dict[str, Any]], list[dict[str, Any]]] | None = None
    for _ in range(attempts):
        current = _snapshot_once(directory)
        if previous is not None and current[1] == previous[1]:
            return current
        previous = current
        time.sleep(0.05)
    raise ConsolidationError(f"source changed while being snapshotted: {directory}")


def require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConsolidationError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ConsolidationError(f"{label} must be finite and non-negative")
    return number


def source_state(documents: dict[str, dict[str, Any]]) -> dict[str, Any]:
    result = documents.get("result.json")
    checkpoint = documents.get("checkpoint.json")
    if result is not None:
        return result
    if checkpoint is not None:
        return checkpoint
    raise ConsolidationError("source requires checkpoint.json or result.json")


def load_source(directory: Path, role: str) -> dict[str, Any]:
    resolved = directory.resolve(strict=True)
    documents, evidence = stable_snapshot(resolved)
    plan = documents.get("plan.json")
    checkpoint = documents.get("checkpoint.json")
    if plan is None or checkpoint is None:
        raise ConsolidationError(f"{role} requires plan.json and checkpoint.json")
    if plan.get("schema") != PLAN_SCHEMA:
        raise ConsolidationError(f"{role} plan schema mismatch")
    if checkpoint.get("schema") != CHECKPOINT_SCHEMA:
        raise ConsolidationError(f"{role} checkpoint schema mismatch")
    if plan.get("mode") != "execute":
        raise ConsolidationError(f"{role} is not an execute-mode soak")

    result = documents.get("result.json")
    failure = documents.get("failure.json")
    if result is not None and failure is not None and result != failure:
        raise ConsolidationError(f"{role} result.json and failure.json differ")
    state = source_state(documents)
    elapsed = require_number(state.get("active_elapsed_seconds"), f"{role} active elapsed")
    target = require_number(state.get("target_duration_seconds"), f"{role} target duration")
    plan_target = require_number(plan.get("target_duration_seconds"), f"{role} plan target duration")
    if not same_float(target, plan_target):
        raise ConsolidationError(f"{role} target duration does not match plan")

    cycles: dict[int, dict[str, Any]] = {}
    partial_attempts: list[dict[str, Any]] = []
    cycle_dirs: dict[int, str] = {}
    for relative, value in documents.items():
        parts = Path(relative).parts
        if len(parts) != 2 or not parts[0].startswith("cycle-"):
            continue
        suffix = parts[0][len("cycle-") :]
        if not suffix.isdigit():
            continue
        index = int(suffix)
        cycle_dirs[index] = parts[0]
        if parts[1] == "cycle.json":
            if value.get("schema") != CYCLE_SCHEMA:
                raise ConsolidationError(f"{role} cycle {index} schema mismatch")
            if value.get("cycle") != index or value.get("status") != "PASS":
                raise ConsolidationError(f"{role} cycle {index} is not a matching PASS cycle")
            cycles[index] = value

    for index, name in sorted(cycle_dirs.items()):
        if index in cycles:
            continue
        failure_doc = documents.get(f"{name}/failure.json")
        state_doc = documents.get(f"{name}/state.json")
        if failure_doc is not None or state_doc is not None:
            attempt = failure_doc or state_doc or {}
            partial_attempts.append(
                {
                    "cycle": index,
                    "status": attempt.get("status", "UNKNOWN"),
                    "phase": attempt.get("failure_phase") or attempt.get("phase"),
                    "error": attempt.get("error"),
                    "evidence": f"{name}/failure.json" if failure_doc is not None else f"{name}/state.json",
                }
            )

    indices = sorted(cycles)
    if indices != list(range(1, len(indices) + 1)):
        raise ConsolidationError(f"{role} PASS cycles are not contiguous from 1")
    declared_cycles = int(state.get("cycles_completed") or 0)
    if declared_cycles != len(cycles):
        raise ConsolidationError(
            f"{role} declares {declared_cycles} cycles but contains {len(cycles)} PASS cycles"
        )
    checkpoint_cycles = int(checkpoint.get("cycles_completed") or 0)
    if checkpoint_cycles != len(cycles):
        raise ConsolidationError(
            f"{role} checkpoint declares {checkpoint_cycles} cycles but contains {len(cycles)} PASS cycles"
        )
    if result is not None and checkpoint.get("status") != result.get("status"):
        raise ConsolidationError(f"{role} checkpoint/result status mismatch")

    seed = documents.get("seed.json")
    if seed is not None and seed.get("schema") != SEED_SCHEMA:
        raise ConsolidationError(f"{role} seed schema mismatch")
    return {
        "role": role,
        "path": resolved,
        "plan": plan,
        "plan_sha256": sha256_bytes(canonical_bytes(plan)),
        "checkpoint": checkpoint,
        "result": result,
        "failure": failure,
        "state": state,
        "status": str(state.get("status") or "UNKNOWN"),
        "active_elapsed_seconds": elapsed,
        "target_duration_seconds": target,
        "cycles": cycles,
        "partial_attempts": partial_attempts,
        "seed": seed,
        "evidence": evidence,
    }


def validate_same_plan(sources: list[dict[str, Any]]) -> dict[str, Any]:
    reference = sources[0]["plan"]
    for source in sources[1:]:
        if source["plan"] != reference:
            raise ConsolidationError(f"plan mismatch in {source['role']}")
    firmware = reference.get("required_firmware")
    candidate_hash = reference.get("candidate_sha256")
    if not isinstance(firmware, str) or not firmware:
        raise ConsolidationError("plan required_firmware is missing")
    if not isinstance(candidate_hash, str) or len(candidate_hash) != 64:
        raise ConsolidationError("plan candidate_sha256 is invalid")
    return reference


def same_float(left: object, right: object, tolerance: float = 0.001) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def validate_lineage(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if sources[0]["seed"] is not None:
        raise ConsolidationError("original source must not contain seed.json")
    lineage: list[dict[str, Any]] = []
    for index in range(1, len(sources)):
        previous = sources[index - 1]
        current = sources[index]
        seed = current["seed"]
        if seed is None:
            raise ConsolidationError(f"{current['role']} requires seed.json")
        try:
            seed_source = normalized_path(Path(str(seed.get("source") or "")))
        except (OSError, RuntimeError) as exc:
            raise ConsolidationError(f"{current['role']} seed source is invalid") from exc
        if seed_source != normalized_path(previous["path"]):
            raise ConsolidationError(f"{current['role']} seed does not reference {previous['role']}")
        if seed.get("source_status") != previous["status"]:
            raise ConsolidationError(f"{current['role']} seed source_status mismatch")
        previous_error = (previous["result"] or previous["checkpoint"]).get("error")
        if seed.get("source_error") != previous_error:
            raise ConsolidationError(f"{current['role']} seed source_error mismatch")
        imported_cycles = int(seed.get("imported_cycles") or 0)
        if imported_cycles != len(previous["cycles"]):
            raise ConsolidationError(f"{current['role']} seed imported_cycles mismatch")
        imported_elapsed = require_number(
            seed.get("imported_active_elapsed_seconds"), f"{current['role']} imported elapsed"
        )
        if not same_float(imported_elapsed, previous["active_elapsed_seconds"]):
            raise ConsolidationError(f"{current['role']} seed imported elapsed mismatch")
        if current["active_elapsed_seconds"] + 0.001 < imported_elapsed:
            raise ConsolidationError(f"{current['role']} active elapsed moved backwards")
        for cycle_index in range(1, imported_cycles + 1):
            if current["cycles"].get(cycle_index) != previous["cycles"].get(cycle_index):
                raise ConsolidationError(
                    f"{current['role']} inherited cycle {cycle_index} differs from {previous['role']}"
                )
        lineage.append(
            {
                "from": str(previous["path"]),
                "to": str(current["path"]),
                "imported_cycles": imported_cycles,
                "imported_active_elapsed_seconds": round(imported_elapsed, 3),
                "reason": seed.get("reason"),
                "validated": True,
            }
        )
    return lineage


def consolidate_cycles(sources: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, int]]:
    unique: dict[int, dict[str, Any]] = {}
    copies: dict[int, int] = {}
    for source in sources:
        for index, cycle in source["cycles"].items():
            copies[index] = copies.get(index, 0) + 1
            if index in unique and unique[index] != cycle:
                raise ConsolidationError(f"divergent duplicate evidence for cycle {index}")
            unique[index] = cycle
    indices = sorted(unique)
    if indices != list(range(1, len(indices) + 1)):
        raise ConsolidationError("consolidated PASS cycles are not contiguous from 1")
    return [unique[index] for index in indices], copies


def classify_failures(
    sources: list[dict[str, Any]], unique_cycles: list[dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    passed = {int(cycle["cycle"]): cycle for cycle in unique_cycles}
    harness: list[dict[str, Any]] = []
    hardware: list[dict[str, Any]] = []
    unclassified: list[dict[str, Any]] = []
    for index, source in enumerate(sources):
        failure = source["failure"] or (
            source["result"] if source["status"] == "FAIL" else None
        )
        if failure is None:
            continue
        failure_cycle = int(failure.get("failure_cycle") or 0)
        successor_seed = sources[index + 1]["seed"] if index + 1 < len(sources) else None
        successor_reason = str((successor_seed or {}).get("reason") or "")
        error = str(failure.get("error") or "")
        combined = f"{error} {successor_reason}".lower()
        later_pass = failure_cycle in passed and any(
            failure_cycle in later["cycles"] for later in sources[index + 1 :]
        )
        explicitly_hardware = bool(failure.get("hardware_failure")) or any(
            marker in combined for marker in HARDWARE_MARKERS
        )
        confirmed_harness = (
            successor_seed is not None
            and later_pass
            and any(marker in combined for marker in HARNESS_MARKERS)
            and not explicitly_hardware
        )
        event = {
            "source": str(source["path"]),
            "cycle": failure_cycle or None,
            "phase": failure.get("failure_phase"),
            "error_type": failure.get("error_type"),
            "error": error,
            "active_elapsed_seconds": round(source["active_elapsed_seconds"], 3),
            "later_cycle_passed": later_pass,
            "continuation_reason": successor_reason or None,
            "evidence": ["failure.json", f"cycle-{failure_cycle:03d}/failure.json"]
            if failure_cycle
            else ["failure.json"],
        }
        if confirmed_harness:
            event["classification"] = "HARNESS_FAILURE_RECOVERED"
            harness.append(event)
        elif explicitly_hardware:
            event["classification"] = "HARDWARE_FAILURE"
            hardware.append(event)
        else:
            event["classification"] = "UNCLASSIFIED_FAILURE"
            unclassified.append(event)
    return harness, hardware, unclassified


def cycle_metrics(cycles: list[dict[str, Any]]) -> dict[str, Any]:
    def values(section: str, field: str) -> list[float]:
        return [float(cycle[section][field]) for cycle in cycles]

    return {
        "median_mbps": {
            "radio2_down": round(statistics.median(values("radio2", "download_mbps")), 3)
            if cycles
            else 0,
            "radio2_up": round(statistics.median(values("radio2", "upload_mbps")), 3)
            if cycles
            else 0,
            "radio5_down": round(statistics.median(values("radio5", "download_mbps")), 3)
            if cycles
            else 0,
            "radio5_up": round(statistics.median(values("radio5", "upload_mbps")), 3)
            if cycles
            else 0,
        },
        "radio5_disconnects": sum(int(cycle["radio5"].get("disconnects") or 0) for cycle in cycles),
        "rx_restarts": sum(int(cycle["radio2"].get("rx_restarts") or 0) for cycle in cycles),
        "minimum_memavailable_kb": min(
            (int(cycle["router"].get("memavailable_kb") or 0) for cycle in cycles), default=0
        ),
        "fatal_total": sum(int(cycle["router"].get("fatal") or 0) for cycle in cycles),
    }


def derive_status(last: dict[str, Any], duration_reached: bool, hardware: list[dict[str, Any]]) -> str:
    if hardware:
        return "FAIL"
    status = last["status"]
    if status == "PASS":
        return "PASS" if duration_reached else "INVALID_FINAL"
    if status in {"IN_PROGRESS", "PAUSED"}:
        return status
    if status == "FAIL":
        return "INTERRUPTED"
    return "UNKNOWN"


def build_summary(source_paths: list[Path]) -> dict[str, Any]:
    if len(source_paths) < 2:
        raise ConsolidationError("F301 soak consolidation requires an original and at least one resume")
    sources = [
        load_source(path, "original" if index == 0 else f"resume{index}")
        for index, path in enumerate(source_paths)
    ]
    if len({normalized_path(source["path"]) for source in sources}) != len(sources):
        raise ConsolidationError("source directories must be unique")
    if any(source["status"] != "FAIL" for source in sources[:-1]):
        raise ConsolidationError("every source before the final segment must be a preserved failed run")
    plan = validate_same_plan(sources)
    lineage = validate_lineage(sources)
    cycles, copies = consolidate_cycles(sources)
    harness, hardware, unclassified = classify_failures(sources, cycles)

    segments: list[dict[str, Any]] = []
    previous_elapsed = 0.0
    for index, source in enumerate(sources):
        imported = 0.0 if index == 0 else float(source["seed"]["imported_active_elapsed_seconds"])
        if not same_float(previous_elapsed, imported):
            raise ConsolidationError(f"{source['role']} elapsed lineage does not join previous segment")
        segment_elapsed = source["active_elapsed_seconds"] - imported
        if segment_elapsed < -0.001:
            raise ConsolidationError(f"{source['role']} has negative segment elapsed")
        segments.append(
            {
                "role": source["role"],
                "source": str(source["path"]),
                "cumulative_elapsed_seconds": round(source["active_elapsed_seconds"], 3),
                "segment_elapsed_seconds": round(max(0.0, segment_elapsed), 3),
            }
        )
        previous_elapsed = source["active_elapsed_seconds"]

    active_elapsed = round(sum(segment["segment_elapsed_seconds"] for segment in segments), 3)
    if not same_float(active_elapsed, sources[-1]["active_elapsed_seconds"], 0.01):
        raise ConsolidationError("active elapsed consolidation double-count check failed")
    target = sources[-1]["target_duration_seconds"]
    duration_reached = active_elapsed >= target
    metrics = cycle_metrics(cycles)
    status = derive_status(sources[-1], duration_reached, hardware)

    source_summaries = []
    for source in sources:
        source_summaries.append(
            {
                "role": source["role"],
                "path": str(source["path"]),
                "status": source["status"],
                "cycles_completed": len(source["cycles"]),
                "active_elapsed_seconds": round(source["active_elapsed_seconds"], 3),
                "plan_sha256": source["plan_sha256"],
                "partial_attempts": source["partial_attempts"],
                "evidence_inventory": source["evidence"],
            }
        )

    return {
        "schema": SUMMARY_SCHEMA,
        "generated_at": utcnow_iso(),
        "status": status,
        "firmware": plan["required_firmware"],
        "candidate_sha256": plan["candidate_sha256"],
        "plan_sha256": sources[0]["plan_sha256"],
        "target_duration_seconds": round(target, 3),
        "active_elapsed_seconds": active_elapsed,
        "duration_reached": duration_reached,
        "cycles_completed": len(cycles),
        "cycles_contiguous": True,
        "cycles_deduplicated": sum(copies.values()) - len(cycles),
        "cycle_copy_counts": {str(index): copies[index] for index in sorted(copies)},
        "cycles": cycles,
        "metrics": metrics,
        "elapsed_segments": segments,
        "lineage": lineage,
        "failures": {
            "harness": harness,
            "hardware": hardware,
            "unclassified": unclassified,
        },
        "source_chain": source_summaries,
        "integrity": {
            "same_plan": True,
            "seed_lineage": True,
            "pass_cycles_contiguous": True,
            "duplicate_cycles_identical": True,
            "active_elapsed_without_double_count": True,
            "source_evidence_immutable": True,
        },
        "hardware_actions_performed": False,
        "flash": False,
        "mtd_writes": False,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    metrics = summary["metrics"]["median_mbps"]
    lines = [
        "# F301 Soak Chain Consolidation",
        "",
        f"- Status: **{summary['status']}**",
        f"- Firmware: `{summary['firmware']}`",
        f"- Candidate SHA-256: `{summary['candidate_sha256']}`",
        f"- PASS cycles: **{summary['cycles_completed']}**",
        f"- Active elapsed: **{summary['active_elapsed_seconds']:.3f} / {summary['target_duration_seconds']:.3f} s**",
        f"- Duration reached: **{str(summary['duration_reached']).lower()}**",
        f"- Inherited cycle copies removed: **{summary['cycles_deduplicated']}**",
        "",
        "## Throughput Medians",
        "",
        "| Band | Down Mbps | Up Mbps |",
        "|---|---:|---:|",
        f"| 2.4 GHz | {metrics['radio2_down']:.3f} | {metrics['radio2_up']:.3f} |",
        f"| 5 GHz | {metrics['radio5_down']:.3f} | {metrics['radio5_up']:.3f} |",
        "",
        "## Source Chain",
        "",
        "| Role | Status | PASS cycles | Cumulative active s | Path |",
        "|---|---|---:|---:|---|",
    ]
    for source in summary["source_chain"]:
        lines.append(
            f"| {source['role']} | {source['status']} | {source['cycles_completed']} | "
            f"{source['active_elapsed_seconds']:.3f} | `{source['path']}` |"
        )
    lines.extend(["", "## Failure Classification", ""])
    for label, title in (
        ("harness", "Harness failures"),
        ("hardware", "Hardware failures"),
        ("unclassified", "Unclassified failures"),
    ):
        events = summary["failures"][label]
        lines.append(f"### {title}: {len(events)}")
        lines.append("")
        if not events:
            lines.append("None.")
        else:
            for event in events:
                lines.append(
                    f"- Cycle {event['cycle']}, phase `{event['phase']}`: {event['error']} "
                    f"({event['classification']})."
                )
        lines.append("")
    lines.extend(
        [
            "## Integrity",
            "",
            "- Same firmware, candidate hash and full plan: PASS",
            "- Seed lineage and imported prefixes: PASS",
            "- PASS cycles contiguous and deduplicated: PASS",
            "- Active elapsed consolidated without double counting: PASS",
            "- Source directories modified: no",
            "- Hardware actions, flash or MTD writes: none",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-dir", type=Path, required=True)
    parser.add_argument("--resume1-dir", type=Path)
    parser.add_argument("--resume2-dir", type=Path)
    parser.add_argument(
        "--resume-dir",
        dest="resume_dirs",
        type=Path,
        action="append",
        default=[],
        help="resume directory in lineage order; may be repeated",
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    legacy_resumes = [path for path in (args.resume1_dir, args.resume2_dir) if path is not None]
    if args.resume_dirs and legacy_resumes:
        print("ERROR: use repeated --resume-dir or the legacy resume1/resume2 pair, not both", file=sys.stderr)
        return 1
    if args.resume_dirs:
        source_paths = [args.original_dir, *args.resume_dirs]
    elif len(legacy_resumes) == 2:
        source_paths = [args.original_dir, *legacy_resumes]
    else:
        print("ERROR: provide at least one --resume-dir or both --resume1-dir and --resume2-dir", file=sys.stderr)
        return 1
    output = args.output_dir.resolve()
    try:
        for source in source_paths:
            resolved = source.resolve(strict=True)
            try:
                output.relative_to(resolved)
            except ValueError:
                pass
            else:
                raise ConsolidationError("output directory must not be inside a source directory")
        summary = build_summary(source_paths)
        atomic_write_json(output / "summary.json", summary)
        atomic_write(output / "summary.md", render_markdown(summary).encode("ascii"))
    except ConsolidationError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
