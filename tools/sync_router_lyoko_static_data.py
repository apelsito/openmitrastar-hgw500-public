#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
LYOKO = ROOT / "work" / "mission-state" / "router-lyoko-v0"
WEB = LYOKO / "rootfs" / "var" / "www"
DATA = WEB / "lyoko-data"
MANIFEST = LYOKO / "manifest.json"
SHA256SUMS = LYOKO / "SHA256SUMS"

STATIC_SOURCES = {
    "mission-truth.json": LYOKO / "mission-truth.json",
    "sector-map.json": LYOKO / "sector-map.json",
    "event-taxonomy.json": LYOKO / "event-taxonomy.json",
    "evidence-bindings.json": LYOKO / "evidence-bindings.json",
    "telemetry-contract.json": LYOKO / "telemetry-contract.json",
    "safe-mode.json": LYOKO / "safe-mode.json",
    "goal-audit.json": ROOT / "work" / "mission-state" / "ROUTER_LYOKO_GOAL_AUDIT_20260822.json",
    "GOAL_AUDIT.md": ROOT / "work" / "mission-state" / "ROUTER_LYOKO_GOAL_AUDIT_20260822.md",
    "aelita-mission-log.jsonl": LYOKO / "memory" / "aelita-mission-log.jsonl",
    "aelita-memory.json": LYOKO / "memory" / "aelita-memory.json",
    "aelita-dialogue.json": LYOKO / "memory" / "aelita-dialogue.json",
    "LATEST_MISSION.md": LYOKO / "memory" / "LATEST_MISSION.md",
    "AELITA_REENTRY_CHECKPOINT_20260822.md": ROOT / "work" / "mission-state" / "AELITA_REENTRY_CHECKPOINT_20260822.md",
    "control-policy.json": LYOKO / "control" / "control-policy.json",
    "REALTEK_TX_TAXONOMY.md": LYOKO / "REALTEK_TX_TAXONOMY.md",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def normalize_json_file(src: Path) -> bytes:
    payload = json.loads(src.read_text(encoding="utf-8"))
    return (json.dumps(payload, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def normalize_jsonl_file(src: Path) -> bytes:
    lines: list[str] = []
    for raw in src.read_text(encoding="utf-8").splitlines():
        if not raw.strip():
            continue
        payload = json.loads(raw)
        lines.append(json.dumps(payload, sort_keys=True, ensure_ascii=False))
    return ("\n".join(lines) + ("\n" if lines else "")).encode("utf-8")


def read_text_file(src: Path) -> bytes:
    return src.read_text(encoding="utf-8").encode("utf-8")


def data_kind(name: str, src: Path) -> bytes:
    if name.endswith(".json"):
        return normalize_json_file(src)
    if name.endswith(".jsonl"):
        return normalize_jsonl_file(src)
    return read_text_file(src)


def build_index(generated: dict[str, bytes]) -> bytes:
    index: dict[str, Any] = {
        "schema": "router-lyoko.static-data/v1",
        "classification": "STATIC-READONLY-RAM-OVERLAY-NO-FLASH",
        "files": {},
        "safety": {
            "device_write": False,
            "flash_write": False,
            "bootenv_write": False,
            "network_reconfigure": False,
            "module_mutation": False,
        },
        "note": "Static lab-side truth/memory snapshot for the Router-Lyoko dashboard. It is not proof of current hardware state.",
    }
    for name, data in sorted(generated.items()):
        index["files"][name] = {"bytes": len(data), "sha256": sha256_bytes(data)}
    return (json.dumps(index, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def generate_static_data() -> dict[str, bytes]:
    generated: dict[str, bytes] = {}
    for name, src in STATIC_SOURCES.items():
        if not src.is_file():
            raise FileNotFoundError(f"missing source {src}")
        generated[name] = data_kind(name, src)
    generated["index.json"] = build_index(generated)
    return generated


def rel_path(raw: str) -> Path:
    rel = Path(*raw.split("/"))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe relative path: {raw}")
    return rel


def find_static_drift(
    generated: dict[str, bytes],
    data_dir: Path = DATA,
    manifest_path: Path = MANIFEST,
    sha256sums_path: Path = SHA256SUMS,
) -> list[dict[str, Any]]:
    mismatches: list[dict[str, Any]] = []

    for name, expected in sorted(generated.items()):
        target = data_dir / name
        rel = f"rootfs/var/www/lyoko-data/{name}"
        if not target.is_file():
            mismatches.append(
                {
                    "kind": "missing_served_file",
                    "file": name,
                    "expected_bytes": len(expected),
                    "expected_sha256": sha256_bytes(expected),
                }
            )
            continue
        actual = target.read_bytes()
        if actual != expected:
            mismatches.append(
                {
                    "kind": "served_file_drift",
                    "file": name,
                    "rel": rel,
                    "expected_bytes": len(expected),
                    "actual_bytes": len(actual),
                    "expected_sha256": sha256_bytes(expected),
                    "actual_sha256": sha256_bytes(actual),
                }
            )

    manifest: dict[str, Any] | None = None
    if not manifest_path.is_file():
        mismatches.append({"kind": "missing_manifest", "path": str(manifest_path)})
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        files = manifest.get("files", {})
        for name, expected in sorted(generated.items()):
            rel = f"rootfs/var/www/lyoko-data/{name}"
            meta = files.get(rel)
            expected_meta = {"bytes": len(expected), "sha256": sha256_bytes(expected)}
            if meta != expected_meta:
                mismatches.append(
                    {
                        "kind": "manifest_drift",
                        "file": name,
                        "rel": rel,
                        "expected": expected_meta,
                        "actual": meta,
                    }
                )

    if not sha256sums_path.is_file():
        mismatches.append({"kind": "missing_sha256sums", "path": str(sha256sums_path)})
    elif manifest is not None:
        expected_lines = []
        for rel, meta in manifest.get("files", {}).items():
            expected_lines.append(f"{meta['sha256']}  {rel}")
        expected_text = "\n".join(expected_lines) + "\n"
        actual_text = sha256sums_path.read_text(encoding="utf-8")
        if actual_text != expected_text:
            mismatches.append(
                {
                    "kind": "sha256sums_drift",
                    "path": str(sha256sums_path),
                    "expected_sha256": sha256_bytes(expected_text.encode("utf-8")),
                    "actual_sha256": sha256_bytes(actual_text.encode("utf-8")),
                }
            )

    return mismatches


def update_manifest(generated: dict[str, bytes]) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    files = manifest.setdefault("files", {})
    for name, data in sorted(generated.items()):
        rel = f"rootfs/var/www/lyoko-data/{name}"
        files[rel] = {"bytes": len(data), "sha256": sha256_bytes(data)}

    for rel in list(files):
        path = LYOKO / Path(*rel.split("/"))
        if not path.is_file():
            raise RuntimeError(f"manifest entry has no file: {rel}")
        data = path.read_bytes()
        files[rel] = {"bytes": len(data), "sha256": sha256_bytes(data)}

    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    ordered_lines = []
    for rel, meta in files.items():
        ordered_lines.append(f"{meta['sha256']}  {rel}")
    SHA256SUMS.write_text("\n".join(ordered_lines) + "\n", encoding="utf-8")


def main(argv: list[str]) -> int:
    dry_run = "--dry-run" in argv
    check = "--check" in argv
    unknown = [arg for arg in argv if arg not in {"--dry-run", "--check"}]
    if unknown:
        print(json.dumps({"ok": False, "error": f"unknown arguments: {unknown}"}, indent=2), file=sys.stderr)
        return 2
    try:
        generated = generate_static_data()
    except FileNotFoundError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1

    report = {
        "ok": True,
        "dry_run": dry_run,
        "check": check,
        "classification": "STATIC-READONLY-RAM-OVERLAY-NO-FLASH",
        "files": {
            f"rootfs/var/www/lyoko-data/{name}": {
                "bytes": len(data),
                "sha256": sha256_bytes(data),
            }
            for name, data in sorted(generated.items())
        },
    }

    if check:
        mismatches = find_static_drift(generated)
        report["ok"] = not mismatches
        report["mismatches"] = mismatches
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return 0 if not mismatches else 1

    if not dry_run:
        DATA.mkdir(parents=True, exist_ok=True)
        for name, data in generated.items():
            (DATA / name).write_bytes(data)
        update_manifest(generated)

    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
