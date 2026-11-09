#!/usr/bin/env python3
"""Consolidate one or more F306 soak evidence directories offline."""
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


EXPECTED_VERSION = "lyoko-foundation-6.7.3-f306-unified-product-device"
EXPECTED_SHA256 = "a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2"
PLAN_SCHEMA = "openmitrastar.f306-sequential-dual-radio-soak-plan/v1"
CHECKPOINT_SCHEMA = "openmitrastar.f306-sequential-dual-radio-soak-checkpoint/v1"
CYCLE_SCHEMA = "openmitrastar.f306-sequential-dual-radio-cycle/v1"
SEED_SCHEMA = "openmitrastar.f306-soak-continuation-seed/v1"
SUMMARY_SCHEMA = "openmitrastar.f306-soak-chain-summary/v1"
PLAN_STABLE_KEYS = (
    "schema", "mode", "required_firmware", "candidate_file", "candidate_sha256",
    "router_host", "oracle_host", "oracle_user", "controller_url",
    "soak_seconds_per_band", "cycle_pause_seconds", "snapshot_attempts",
    "snapshot_retry_seconds", "radio2_runner", "radio5_runner", "radio5_profile",
    "radio5_ack", "restore_ssid", "aelita_known_hosts_file",
    "aelita_host_key_mode", "aelita_fingerprint_enforced",
    "aelita_ssh_connect_timeout",
)


class ConsolidationError(RuntimeError):
    pass


def canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ConsolidationError(f"cannot read JSON {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConsolidationError(f"expected JSON object: {path}")
    return value


def atomic_write(path: Path, data: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.{time.time_ns()}.tmp")
    try:
        with temporary.open("wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    atomic_write(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True).encode("ascii") + b"\n")


def normalized(path: Path) -> str:
    return os.path.normcase(str(path.resolve(strict=True)))


def require_number(value: object, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ConsolidationError(f"{label} must be numeric")
    number = float(value)
    if not math.isfinite(number) or number < 0:
        raise ConsolidationError(f"{label} must be finite and non-negative")
    return number


def same_float(left: object, right: object, tolerance: float = 0.001) -> bool:
    try:
        return abs(float(left) - float(right)) <= tolerance
    except (TypeError, ValueError):
        return False


def stable_documents(directory: Path, attempts: int = 5) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    if not directory.is_dir():
        raise ConsolidationError(f"source directory not found: {directory}")
    previous_inventory: list[dict[str, Any]] | None = None
    previous_documents: dict[str, dict[str, Any]] | None = None
    for _ in range(attempts):
        documents: dict[str, dict[str, Any]] = {}
        inventory: list[dict[str, Any]] = []
        for path in sorted(directory.rglob("*.json"), key=lambda item: item.relative_to(directory).as_posix()):
            relative = path.relative_to(directory).as_posix()
            data = path.read_bytes()
            documents[relative] = read_json(path)
            inventory.append({"path": relative, "bytes": len(data), "sha256": sha256_bytes(data)})
        if inventory == previous_inventory:
            assert previous_documents is not None
            return previous_documents, previous_inventory
        previous_documents, previous_inventory = documents, inventory
        time.sleep(0.05)
    raise ConsolidationError(f"source changed while being read: {directory}")


def terminal_state(documents: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], str]:
    if "result.json" in documents:
        return documents["result.json"], "result.json"
    if "checkpoint.json" in documents:
        return documents["checkpoint.json"], "checkpoint.json"
    raise ConsolidationError("source has no result.json or checkpoint.json")


def completed_cycles(documents: dict[str, dict[str, Any]]) -> dict[int, dict[str, Any]]:
    cycles: dict[int, dict[str, Any]] = {}
    for relative, value in documents.items():
        parts = Path(relative).parts
        if len(parts) != 2 or parts[1] != "cycle.json" or not parts[0].startswith("cycle-"):
            continue
        suffix = parts[0][6:]
        if not suffix.isdigit():
            continue
        index = int(suffix)
        if value.get("schema") != CYCLE_SCHEMA or value.get("cycle") != index:
            raise ConsolidationError(f"cycle {index} schema/index mismatch")
        if value.get("status") != "PASS":
            raise ConsolidationError(f"cycle {index} is not PASS")
        cycles[index] = value
    indices = sorted(cycles)
    if indices != list(range(1, len(indices) + 1)):
        raise ConsolidationError("PASS cycles are not contiguous from 1")
    return cycles


def load_source(path: Path, role: str) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    documents, inventory = stable_documents(resolved)
    plan = documents.get("plan.json")
    checkpoint = documents.get("checkpoint.json")
    if plan is None or checkpoint is None:
        raise ConsolidationError(f"{role} requires plan.json and checkpoint.json")
    if plan.get("schema") != PLAN_SCHEMA or checkpoint.get("schema") != CHECKPOINT_SCHEMA:
        raise ConsolidationError(f"{role} schema mismatch")
    if plan.get("mode") != "execute":
        raise ConsolidationError(f"{role} is not execute-mode evidence")
    if plan.get("required_firmware") != EXPECTED_VERSION or plan.get("candidate_sha256") != EXPECTED_SHA256:
        raise ConsolidationError(f"{role} is not the exact F306 artifact")
    state, state_file = terminal_state(documents)
    cycles = completed_cycles(documents)
    if int(state.get("cycles_completed") or 0) != len(cycles):
        raise ConsolidationError(f"{role} declared cycle count does not match evidence")
    elapsed = require_number(state.get("active_elapsed_seconds"), f"{role} active elapsed")
    target = require_number(state.get("target_duration_seconds"), f"{role} target")
    if not same_float(target, plan.get("target_duration_seconds")):
        raise ConsolidationError(f"{role} target differs from plan")
    seed = documents.get("seed.json")
    if seed is not None and seed.get("schema") != SEED_SCHEMA:
        raise ConsolidationError(f"{role} seed schema mismatch")
    return {
        "role": role,
        "path": resolved,
        "plan": plan,
        "plan_sha256": sha256_bytes(canonical_bytes(plan)),
        "checkpoint": checkpoint,
        "state": state,
        "state_file": state_file,
        "status": str(state.get("status") or "UNKNOWN"),
        "elapsed": elapsed,
        "target": target,
        "cycles": cycles,
        "seed": seed,
        "inventory": inventory,
    }


def validate_plans(sources: list[dict[str, Any]]) -> None:
    reference = sources[0]["plan"]
    for source in sources[1:]:
        mismatches = [key for key in PLAN_STABLE_KEYS if source["plan"].get(key) != reference.get(key)]
        if mismatches:
            raise ConsolidationError(f"stable plan mismatch in {source['role']}: {', '.join(mismatches)}")
    targets = [source["target"] for source in sources]
    if targets != sorted(targets):
        raise ConsolidationError("target duration moved backwards across seed lineage")
    if any(target not in {21600.0, 86400.0} for target in targets):
        raise ConsolidationError("F306 soak target must be exactly 6 h or 24 h")


def validate_lineage(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if len(sources) == 1:
        return []
    if sources[0]["seed"] is not None:
        raise ConsolidationError("first source in a chain must not be seeded")
    result: list[dict[str, Any]] = []
    for index in range(1, len(sources)):
        previous, current = sources[index - 1], sources[index]
        seed = current["seed"]
        if seed is None:
            raise ConsolidationError(f"{current['role']} requires seed.json")
        if normalized(Path(str(seed.get("source") or ""))) != normalized(previous["path"]):
            raise ConsolidationError(f"{current['role']} seed source mismatch")
        if seed.get("source_status") != previous["status"]:
            raise ConsolidationError(f"{current['role']} seed source status mismatch")
        if int(seed.get("imported_cycles") or 0) != len(previous["cycles"]):
            raise ConsolidationError(f"{current['role']} imported cycle count mismatch")
        imported_elapsed = require_number(seed.get("imported_active_elapsed_seconds"), "imported elapsed")
        if not same_float(imported_elapsed, previous["elapsed"]):
            raise ConsolidationError(f"{current['role']} imported elapsed mismatch")
        if current["elapsed"] + 0.001 < imported_elapsed:
            raise ConsolidationError(f"{current['role']} elapsed moved backwards")
        for cycle_index, cycle in previous["cycles"].items():
            if current["cycles"].get(cycle_index) != cycle:
                raise ConsolidationError(f"{current['role']} changed inherited cycle {cycle_index}")
        result.append({
            "from": str(previous["path"]),
            "to": str(current["path"]),
            "imported_cycles": len(previous["cycles"]),
            "imported_active_elapsed_seconds": round(imported_elapsed, 3),
            "reason": seed.get("reason"),
            "validated": True,
        })
    return result


def deduplicate_cycles(sources: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int]:
    unique: dict[int, dict[str, Any]] = {}
    copies = 0
    for source in sources:
        for index, cycle in source["cycles"].items():
            if index in unique:
                copies += 1
                if unique[index] != cycle:
                    raise ConsolidationError(f"divergent duplicate cycle {index}")
            else:
                unique[index] = cycle
    indices = sorted(unique)
    if indices != list(range(1, len(indices) + 1)):
        raise ConsolidationError("deduplicated cycles are not contiguous")
    return [unique[index] for index in indices], copies


def metrics(cycles: list[dict[str, Any]]) -> dict[str, Any]:
    def values(section: str, key: str) -> list[float]:
        return [float(cycle[section][key]) for cycle in cycles]
    return {
        "median_mbps": {
            "radio2_down": round(statistics.median(values("radio2", "download_mbps")), 3) if cycles else 0,
            "radio2_up": round(statistics.median(values("radio2", "upload_mbps")), 3) if cycles else 0,
            "radio5_down": round(statistics.median(values("radio5", "download_mbps")), 3) if cycles else 0,
            "radio5_up": round(statistics.median(values("radio5", "upload_mbps")), 3) if cycles else 0,
        },
        "radio5_disconnects": sum(int(cycle["radio5"].get("disconnects") or 0) for cycle in cycles),
        "rx_restarts": sum(int(cycle["radio2"].get("rx_restarts") or 0) for cycle in cycles),
        "fatal_total": sum(int(cycle["router"].get("fatal") or 0) for cycle in cycles),
        "minimum_memavailable_kb": min((int(cycle["router"].get("memavailable_kb") or 0) for cycle in cycles), default=0),
    }


def final_status(last: dict[str, Any], duration_reached: bool, cycles: list[dict[str, Any]]) -> str:
    all_passed = bool(cycles) and all(cycle.get("status") == "PASS" for cycle in cycles)
    if last["status"] == "FAIL" or not all_passed:
        return "FAIL"
    if last["status"] == "PASS":
        return "PASS" if duration_reached else "INVALID_FINAL"
    if last["status"] in {"PAUSED", "IN_PROGRESS"}:
        return "PAUSED"
    return "UNKNOWN"


def build_summary(paths: list[Path]) -> dict[str, Any]:
    if not paths:
        raise ConsolidationError("at least one source is required")
    sources = [load_source(path, f"source{index + 1}") for index, path in enumerate(paths)]
    if len({normalized(source["path"]) for source in sources}) != len(sources):
        raise ConsolidationError("source directories must be unique")
    validate_plans(sources)
    lineage = validate_lineage(sources)
    cycles, duplicate_count = deduplicate_cycles(sources)
    last = sources[-1]
    active_elapsed = last["elapsed"]
    target = last["target"]
    duration_reached = active_elapsed >= target
    status = final_status(last, duration_reached, cycles)
    return {
        "schema": SUMMARY_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "firmware": EXPECTED_VERSION,
        "candidate_sha256": EXPECTED_SHA256,
        "target_duration_seconds": round(target, 3),
        "active_elapsed_seconds": round(active_elapsed, 3),
        "duration_reached": duration_reached,
        "cycles_completed": len(cycles),
        "cycles_deduplicated": duplicate_count,
        "cycles": cycles,
        "metrics": metrics(cycles),
        "lineage": lineage,
        "sources": [{
            "role": source["role"],
            "path": str(source["path"]),
            "status": source["status"],
            "target_duration_seconds": round(source["target"], 3),
            "active_elapsed_seconds": round(source["elapsed"], 3),
            "cycles_completed": len(source["cycles"]),
            "plan_sha256": source["plan_sha256"],
            "evidence_inventory": source["inventory"],
        } for source in sources],
        "integrity": {
            "exact_f306_artifact": True,
            "stable_plan_contract": True,
            "seed_lineage": True,
            "duplicate_cycles_identical": True,
            "duration_status_fail_closed": True,
            "source_evidence_immutable": True,
        },
        "hardware_actions_performed": False,
        "flash": False,
        "mtd_writes": False,
    }


def render_markdown(summary: dict[str, Any]) -> str:
    medians = summary["metrics"]["median_mbps"]
    return "\n".join([
        "# F306 Soak Consolidation",
        "",
        f"- Status: **{summary['status']}**",
        f"- Active duration: **{summary['active_elapsed_seconds']:.3f} / {summary['target_duration_seconds']:.3f} s**",
        f"- Duration reached: **{str(summary['duration_reached']).lower()}**",
        f"- Unique PASS cycles: **{summary['cycles_completed']}**",
        f"- Duplicate inherited cycles removed: **{summary['cycles_deduplicated']}**",
        f"- 2.4 GHz median: **{medians['radio2_down']:.3f} / {medians['radio2_up']:.3f} Mbps**",
        f"- 5 GHz median: **{medians['radio5_down']:.3f} / {medians['radio5_up']:.3f} Mbps**",
        "- Hardware actions performed by consolidation: **none**",
        "",
    ])


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-dir", type=Path, action="append", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output = args.output_dir.resolve()
    try:
        for source in args.source_dir:
            resolved = source.resolve(strict=True)
            try:
                output.relative_to(resolved)
            except ValueError:
                pass
            else:
                raise ConsolidationError("output must not be inside a source directory")
        summary = build_summary(args.source_dir)
        atomic_write_json(output / "summary.json", summary)
        atomic_write(output / "summary.md", render_markdown(summary).encode("ascii"))
    except (ConsolidationError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
