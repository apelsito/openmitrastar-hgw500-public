#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LYOKO = ROOT / "work" / "mission-state" / "router-lyoko-v0"
DEFAULT_TRUTH = LYOKO / "mission-truth.json"
DEFAULT_LOG = LYOKO / "memory" / "aelita-mission-log.jsonl"
DEFAULT_LATEST = LYOKO / "memory" / "LATEST_MISSION.md"


SECRET_PATTERNS = (
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(password|passwd|psk|secret|token)\s*[:=]\s*\S{6,}"),
    re.compile(r"(?i)\bCOOKIE_SESSION_KEY\b\s*[:=]\s*\S+"),
)


def canonical_json(data: Any) -> str:
    return json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def assert_no_secret_text(value: str, where: str) -> None:
    for pattern in SECRET_PATTERNS:
        if pattern.search(value):
            raise RuntimeError(f"refusing to record possible secret in {where}")


def walk_strings(value: Any, prefix: str = "$") -> None:
    if isinstance(value, dict):
        for k, v in value.items():
            walk_strings(v, f"{prefix}.{k}")
    elif isinstance(value, list):
        for i, v in enumerate(value):
            walk_strings(v, f"{prefix}[{i}]")
    elif isinstance(value, str):
        assert_no_secret_text(value, prefix)


def load_truth(path: Path) -> dict[str, Any]:
    truth = json.loads(path.read_text(encoding="utf-8"))
    if truth.get("schema") != "router-lyoko.truth/v1":
        raise RuntimeError(f"unexpected truth schema in {path}")
    if truth.get("classification") != "EVIDENCE-LEDGER-READONLY-NO-FLASH":
        raise RuntimeError(f"unexpected truth classification in {path}")
    walk_strings(truth)
    return truth


def latest_previous_hash(log_path: Path) -> str | None:
    if not log_path.is_file():
        return None
    last_hash = None
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        last_hash = item.get("event_hash")
    return last_hash


def event_from_truth(truth: dict[str, Any], *, title: str, timestamp: str, previous_hash: str | None) -> dict[str, Any]:
    counts = truth.get("summary", {}).get("counts", {})
    next_gate = truth.get("summary", {}).get("next_gate")
    gates = truth.get("gates", [])
    incomplete = [
        {
            "id": gate["id"],
            "sector": gate["sector"],
            "status": gate["status"],
            "next_discriminant": gate["next_discriminant"],
        }
        for gate in gates
        if gate.get("status") in {"PARTIAL", "PENDING", "BLOCKED", "UNKNOWN"}
    ]
    ready = [
        {"id": gate["id"], "sector": gate["sector"], "status": gate["status"]}
        for gate in gates
        if gate.get("status") in {"PROVEN", "READY"}
    ]
    event_id = sha256_text(
        canonical_json(
            {
                "schema": "router-lyoko.mission-event/v1",
                "title": title,
                "timestamp": timestamp,
                "truth_hash": sha256_text(canonical_json(truth)),
            }
        )
    )
    base = {
        "schema": "router-lyoko.mission-event/v1",
        "classification": "LAB-SIDE-MEMORY-NO-DEVICE-WRITE",
        "event_id": event_id,
        "title": title,
        "timestamp": timestamp,
        "persona": "Aelita",
        "truth_hash": sha256_text(canonical_json(truth)),
        "previous_hash": previous_hash,
        "summary": {
            "counts": counts,
            "next_gate": next_gate,
            "rule": truth.get("summary", {}).get("truth_rule"),
        },
        "ready_or_proven": ready,
        "incomplete": incomplete,
        "safety": {
            "device_write": False,
            "flash_write": False,
            "bootenv_write": False,
            "network_reconfigure": False,
            "contains_secrets": False,
        },
    }
    event_hash = sha256_text(canonical_json(base))
    return {**base, "event_hash": event_hash}


def existing_event_hashes(log_path: Path) -> set[str]:
    return set(existing_events_by_id(log_path).keys())


def legacy_event_id(item: dict[str, Any]) -> str | None:
    if "event_id" in item:
        return item["event_id"]
    if {"title", "timestamp", "truth_hash"}.issubset(item):
        return sha256_text(
            canonical_json(
                {
                    "schema": item.get("schema", "router-lyoko.mission-event/v1"),
                    "title": item["title"],
                    "timestamp": item["timestamp"],
                    "truth_hash": item["truth_hash"],
                }
            )
        )
    if "event_hash" in item:
        return item["event_hash"]
    return None


def existing_events_by_id(log_path: Path) -> dict[str, dict[str, Any]]:
    events: dict[str, dict[str, Any]] = {}
    if not log_path.is_file():
        return events
    for line in log_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        event_id = legacy_event_id(item)
        if event_id:
            events.setdefault(event_id, item)
    return events


def render_latest(event: dict[str, Any]) -> str:
    lines = [
        "# Aelita mission memory",
        "",
        f"Classification: `{event['classification']}`",
        f"Event hash: `{event['event_hash']}`",
        f"Previous hash: `{event['previous_hash'] or 'none'}`",
        "",
        f"## {event['title']}",
        "",
        f"- Timestamp: `{event['timestamp']}`",
        f"- Truth hash: `{event['truth_hash']}`",
        f"- Next gate: `{event['summary']['next_gate']}`",
        "",
        "## Counts",
        "",
    ]
    for status, count in sorted(event["summary"]["counts"].items()):
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Ready or proven sectors", ""])
    for item in event["ready_or_proven"]:
        lines.append(f"- `{item['status']}` {item['sector']} — `{item['id']}`")
    lines.extend(["", "## Incomplete sectors", ""])
    for item in event["incomplete"]:
        lines.append(
            f"- `{item['status']}` {item['sector']} — `{item['id']}`: {item['next_discriminant']}"
        )
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- This is lab-side memory only.",
            "- No device write, flash write, bootenv write, module mutation or network reconfiguration is performed.",
            "- Do not use this memory as proof of hardware success; use the cited evidence gate.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Record a Router-Lyoko lab-side mission memory event from mission-truth.json."
    )
    parser.add_argument("--truth", type=Path, default=DEFAULT_TRUTH)
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    parser.add_argument("--latest-md", type=Path, default=DEFAULT_LATEST)
    parser.add_argument("--title", default="Router-Lyoko truth checkpoint")
    parser.add_argument(
        "--timestamp",
        default=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        help="Event timestamp. Use explicit value for reproducible tests.",
    )
    parser.add_argument("--write", action="store_true", help="Append JSONL and update latest Markdown.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        truth = load_truth(args.truth)
        previous_hash = latest_previous_hash(args.log)
        event = event_from_truth(
            truth,
            title=args.title,
            timestamp=args.timestamp,
            previous_hash=previous_hash,
        )
        if args.write:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            existing = existing_events_by_id(args.log)
            if event["event_id"] in existing:
                event = existing[event["event_id"]]
            else:
                with args.log.open("a", encoding="utf-8", newline="\n") as f:
                    f.write(json.dumps(event, sort_keys=True, ensure_ascii=False) + "\n")
            args.latest_md.parent.mkdir(parents=True, exist_ok=True)
            args.latest_md.write_text(render_latest(event), encoding="utf-8")
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps({"ok": True, "event": event}, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
