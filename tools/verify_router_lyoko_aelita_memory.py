#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATA_DIR = (
    ROOT
    / "work"
    / "mission-state"
    / "router-lyoko-v0"
    / "rootfs"
    / "var"
    / "www"
    / "lyoko-data"
)

REQUIRED_MEMORY_GATES = {
    "post_tx7_recovery_pass",
    "ethernet_ssh_soak_pass",
    "realtek_2g_client_data_pass",
    "rollback_path_current",
    "exact_image_hash_recorded",
}

REQUIRED_FILES = {
    "aelita-memory.json",
    "aelita-dialogue.json",
    "aelita-mission-log.jsonl",
    "LATEST_MISSION.md",
    "goal-audit.json",
    "mission-truth.json",
    "AELITA_REENTRY_CHECKPOINT_20260822.md",
}

ALLOWED_NON_FILE_SOURCES = {"project_brief"}


@dataclass(frozen=True)
class Finding:
    kind: str
    path: str
    detail: str


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def add(finding_list: list[Finding], kind: str, path: str, detail: str) -> None:
    finding_list.append(Finding(kind=kind, path=path, detail=detail))


def verify_index(data_dir: Path, findings: list[Finding]) -> dict[str, Any]:
    index_path = data_dir / "index.json"
    if not index_path.is_file():
        add(findings, "missing_file", "index.json", "static data index is missing")
        return {"files": {}}
    try:
        index = load_json(index_path)
    except Exception as exc:
        add(findings, "invalid_json", "index.json", str(exc))
        return {"files": {}}

    if index.get("schema") != "router-lyoko.static-data/v1":
        add(findings, "bad_schema", "index.json", "unexpected static data schema")
    if index.get("safety", {}).get("device_write") is not False:
        add(findings, "unsafe_index", "index.json", "device_write must be false")

    files = index.get("files", {})
    for name in REQUIRED_FILES:
        if name not in files:
            add(findings, "index_missing_required_file", "index.json", f"{name} is not indexed")
            continue
        path = data_dir / name
        if not path.is_file():
            add(findings, "missing_file", name, "indexed file is missing")
            continue
        payload = path.read_bytes()
        meta = files[name]
        if meta.get("bytes") != len(payload):
            add(findings, "index_bytes_mismatch", name, "indexed byte count does not match file")
        if meta.get("sha256") != sha256_bytes(payload):
            add(findings, "index_sha256_mismatch", name, "indexed sha256 does not match file")
    return index


def verify_aelita_memory(data_dir: Path, index: dict[str, Any], findings: list[Finding]) -> dict[str, Any]:
    path = data_dir / "aelita-memory.json"
    try:
        memory = load_json(path)
    except Exception as exc:
        add(findings, "invalid_json", "aelita-memory.json", str(exc))
        return {}

    if memory.get("schema") != "router-lyoko.aelita-memory/v1":
        add(findings, "bad_schema", "aelita-memory.json", "unexpected memory schema")
    if memory.get("classification") != "STAGED-PERSISTENT-MEMORY-CONTRACT-NO-HARDWARE-PROOF":
        add(findings, "bad_classification", "aelita-memory.json", "memory must remain a staged no-hardware-proof contract")

    storage = memory.get("storage", {})
    if storage.get("writes_device_now") is not False:
        add(findings, "device_write_enabled", "aelita-memory.json", "writes_device_now must be false")
    gates = set(storage.get("requires_before_persistent_write") or [])
    missing = sorted(REQUIRED_MEMORY_GATES - gates)
    if missing:
        add(findings, "missing_persistence_gate", "aelita-memory.json", f"missing gates: {', '.join(missing)}")

    current = memory.get("current_state", {})
    if current.get("hardware_blocked") is not True:
        add(findings, "missing_hardware_block", "aelita-memory.json", "current_state.hardware_blocked must stay true until live recovery")
    if current.get("status") not in {"staged_read_only", "blocked_by_hardware"}:
        add(findings, "bad_memory_status", "aelita-memory.json", "current memory status must not imply live persistence")

    indexed_files = set((index.get("files") or {}).keys())
    for slot in memory.get("memory_slots") or []:
        source = slot.get("source")
        if not source:
            add(findings, "memory_slot_missing_source", "aelita-memory.json", f"slot {slot.get('id', '<unknown>')} has no source")
            continue
        if source in ALLOWED_NON_FILE_SOURCES:
            continue
        if source not in indexed_files:
            add(findings, "memory_slot_unindexed_source", "aelita-memory.json", f"slot {slot.get('id', '<unknown>')} source {source} is not in index.json")

    forbidden = memory.get("forbidden_memory_claims") or []
    if not any("current hardware recovery" in str(item) for item in forbidden):
        add(findings, "missing_forbidden_claim", "aelita-memory.json", "must forbid claiming current hardware recovery from static data")
    if not any("persistence" in str(item).lower() for item in forbidden):
        add(findings, "missing_forbidden_claim", "aelita-memory.json", "must forbid claiming persistence before gates")
    return memory


def verify_dialogue(data_dir: Path, findings: list[Finding]) -> dict[str, Any]:
    path = data_dir / "aelita-dialogue.json"
    try:
        dialogue = load_json(path)
    except Exception as exc:
        add(findings, "invalid_json", "aelita-dialogue.json", str(exc))
        return {}

    if dialogue.get("schema") != "router-lyoko.aelita-dialogue/v1":
        add(findings, "bad_schema", "aelita-dialogue.json", "unexpected dialogue schema")
    if dialogue.get("writes_device_now") is not False:
        add(findings, "device_write_enabled", "aelita-dialogue.json", "dialogue catalog must not write device state")
    if dialogue.get("classification") != "STATIC-READONLY-DIALOGUE-CATALOG-NO-HARDWARE-PROOF":
        add(findings, "bad_classification", "aelita-dialogue.json", "dialogue must remain static/read-only")

    lines = dialogue.get("lines") or []
    ids = [line.get("id") for line in lines]
    if len(ids) != len(set(ids)):
        add(findings, "duplicate_dialogue_id", "aelita-dialogue.json", "dialogue ids must be unique")
    missing = sorted(set(dialogue.get("selection_order") or []) - set(ids))
    if missing:
        add(findings, "selection_order_missing_line", "aelita-dialogue.json", f"missing ids: {', '.join(missing)}")

    for line in lines:
        source = str(line.get("source") or "")
        condition = str(line.get("condition") or "")
        if not source or not condition:
            add(findings, "dialogue_missing_evidence_condition", "aelita-dialogue.json", f"line {line.get('id', '<unknown>')} needs source and condition")
        if line.get("hardware_claim") is True and "runtime /api/lyoko" not in source:
            add(findings, "static_dialogue_hardware_claim", "aelita-dialogue.json", f"line {line.get('id', '<unknown>')} claims hardware without runtime /api/lyoko source")

    forbidden = dialogue.get("forbidden") or []
    if not any("current recovery" in str(item) for item in forbidden):
        add(findings, "missing_dialogue_forbidden_claim", "aelita-dialogue.json", "dialogue must forbid current recovery claims from static files")
    return dialogue


def event_hash(event: dict[str, Any]) -> str:
    clone = dict(event)
    clone.pop("event_hash", None)
    encoded = json.dumps(clone, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    return sha256_bytes(encoded)


def verify_mission_log(data_dir: Path, findings: list[Finding]) -> dict[str, Any]:
    path = data_dir / "aelita-mission-log.jsonl"
    try:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except Exception as exc:
        add(findings, "missing_or_unreadable_log", "aelita-mission-log.jsonl", str(exc))
        return {"events": 0}

    previous: str | None = None
    last_event: dict[str, Any] | None = None
    parsed = 0
    for line_no, line in enumerate(lines, 1):
        try:
            event = json.loads(line)
        except Exception as exc:
            add(findings, "invalid_jsonl", "aelita-mission-log.jsonl", f"line {line_no}: {exc}")
            continue
        parsed += 1
        if event.get("schema") != "router-lyoko.mission-event/v1":
            add(findings, "bad_event_schema", "aelita-mission-log.jsonl", f"line {line_no} has unexpected schema")
        if event.get("classification") != "LAB-SIDE-MEMORY-NO-DEVICE-WRITE":
            add(findings, "bad_event_classification", "aelita-mission-log.jsonl", f"line {line_no} must remain lab-side/no-device-write")
        safety = event.get("safety") or {}
        for key in ("device_write", "flash_write", "bootenv_write", "network_reconfigure", "contains_secrets"):
            if safety.get(key) is not False:
                add(findings, "unsafe_event_safety", "aelita-mission-log.jsonl", f"line {line_no} safety.{key} must be false")
        if event.get("previous_hash") != previous:
            add(findings, "mission_log_chain_break", "aelita-mission-log.jsonl", f"line {line_no} previous_hash does not match prior event_hash")
        if event.get("event_hash") != event_hash(event):
            add(findings, "mission_log_hash_mismatch", "aelita-mission-log.jsonl", f"line {line_no} event_hash does not match event content")
        previous = event.get("event_hash")
        last_event = event

    if parsed == 0:
        add(findings, "empty_mission_log", "aelita-mission-log.jsonl", "mission log must contain at least one event")
    return {"events": parsed, "last_event_hash": previous, "last_event": last_event}


def verify_latest_mission(data_dir: Path, log_summary: dict[str, Any], findings: list[Finding]) -> None:
    path = data_dir / "LATEST_MISSION.md"
    try:
        latest = path.read_text(encoding="utf-8")
    except Exception as exc:
        add(findings, "missing_or_unreadable_latest_mission", "LATEST_MISSION.md", str(exc))
        return

    last_event = log_summary.get("last_event")
    if not isinstance(last_event, dict):
        add(findings, "latest_mission_without_event", "LATEST_MISSION.md", "latest mission cannot be verified without a parsed last event")
        return

    expected_hash = str(last_event.get("event_hash") or "")
    expected_title = str(last_event.get("title") or "")
    expected_timestamp = str(last_event.get("timestamp") or "")
    expected_next_gate = str((last_event.get("summary") or {}).get("next_gate") or "")

    if expected_hash and f"Event hash: `{expected_hash}`" not in latest:
        add(findings, "latest_mission_hash_mismatch", "LATEST_MISSION.md", "latest mission must reference the last mission event hash")
    if expected_title and expected_title not in latest:
        add(findings, "latest_mission_title_mismatch", "LATEST_MISSION.md", "latest mission must describe the last mission event title")
    if expected_timestamp and expected_timestamp not in latest:
        add(findings, "latest_mission_timestamp_mismatch", "LATEST_MISSION.md", "latest mission must include the last mission event timestamp")
    if expected_next_gate and f"Next gate: `{expected_next_gate}`" not in latest:
        add(findings, "latest_mission_next_gate_mismatch", "LATEST_MISSION.md", "latest mission must expose the last mission event next_gate")

    for phrase in (
        "No device write",
        "Do not use this memory as proof of hardware success",
    ):
        if phrase not in latest:
            add(findings, "latest_mission_missing_safety_text", "LATEST_MISSION.md", f"missing safety text: {phrase}")


def build_report(data_dir: Path) -> dict[str, Any]:
    data_dir = data_dir.resolve()
    findings: list[Finding] = []
    index = verify_index(data_dir, findings)
    memory = verify_aelita_memory(data_dir, index, findings)
    dialogue = verify_dialogue(data_dir, findings)
    log_summary = verify_mission_log(data_dir, findings)
    verify_latest_mission(data_dir, log_summary, findings)
    return {
        "schema": "router-lyoko.aelita-memory-guard/v1",
        "classification": "READONLY-AELITA-MEMORY-GUARD-NO-HARDWARE",
        "ok": not findings,
        "data_dir": str(data_dir),
        "summary": {
            "memory_slots": len(memory.get("memory_slots") or []),
            "dialogue_lines": len(dialogue.get("lines") or []),
            "mission_events": log_summary["events"],
            "writes_device_now": memory.get("storage", {}).get("writes_device_now"),
            "hardware_blocked": memory.get("current_state", {}).get("hardware_blocked"),
        },
        "findings_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Router-Lyoko Aelita memory/dialogue remains evidence-bound and read-only."
    )
    parser.add_argument("--data-dir", type=Path, default=DEFAULT_DATA_DIR)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        report = build_report(args.data_dir)
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2, ensure_ascii=False), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
