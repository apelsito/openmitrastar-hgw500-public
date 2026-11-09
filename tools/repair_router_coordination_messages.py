"""Repair only this coordinator's three malformed Azure delegation records.

Run only while both affected tasks are unloaded. Preserve original bytes in a
private timestamped backup. Never alter router files or existing user messages.
"""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(r"/workspace/user-home\.codex")
SOURCE = "01a072b5-0632-7530-991c-674153e07bd3"
TARGETS = {
    "rollout-2026-09-05T14-21-21-01a07184-2645-7ee1-b072-7f8158f0dde4.jsonl": 2,
    "rollout-2026-09-05T17-44-15-01a0723d-e9cc-7a23-a7b0-254a8f198b72.jsonl": 1,
}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def prepare(path, expected):
    original = path.read_bytes()
    lines = original.splitlines(keepends=True)
    changes = []
    result = []
    for number, raw in enumerate(lines, 1):
        record = json.loads(raw)
        item = record.get("payload", {})
        if (record.get("type") == "response_item"
                and item.get("type") == "function_call_output"
                and not item.get("call_id")):
            assert item.get("name") == "send_message_to_thread"
            assert item.get("namespace") == "codex_app"
            text = item.get("output")
            assert isinstance(text, str)
            assert f"<source_thread_id>{SOURCE}</source_thread_id>" in text
            record["payload"] = {
                "type": "message", "role": "user",
                "content": [{"type": "input_text", "text": text}],
            }
            changes.append({"line": number, "original_id": item["id"]})
            raw = (json.dumps(record, ensure_ascii=False) + "\n").encode("utf-8")
        result.append(raw)
    assert len(changes) == expected, (path.name, len(changes), expected)
    repaired = b"".join(result)
    for raw in repaired.splitlines():
        r = json.loads(raw)
        p = r.get("payload", {})
        assert not (r.get("type") == "response_item"
                    and p.get("type") == "function_call_output"
                    and not p.get("call_id"))
    return original, repaired, changes


def main():
    prepared = []
    for name, count in TARGETS.items():
        path = BASE / "archived_sessions" / name
        prepared.append((path, *prepare(path, count)))
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = BASE / "repair-backups" / (stamp + "-router-delegation-call-id")
    backup.mkdir(parents=True, exist_ok=False)
    report = {"backup_directory": str(backup), "source_thread": SOURCE, "files": []}
    for path, original, repaired, changes in prepared:
        saved = backup / path.name
        saved.write_bytes(original)
        assert digest(saved.read_bytes()) == digest(original)
        assert path.read_bytes() == original, "Concurrent task write; abort repair"
        temporary = path.with_suffix(".jsonl.coordination-repair-tmp")
        with temporary.open("xb") as stream:
            stream.write(repaired)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        assert path.read_bytes() == repaired
        report["files"].append({
            "path": str(path), "before_sha256": digest(original),
            "after_sha256": digest(repaired), "changes": changes,
        })
    (backup / "repair-report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
