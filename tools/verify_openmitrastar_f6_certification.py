#!/usr/bin/env python3
"""Fail-closed verifier for the OpenMitraStar F6 certification matrix."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MATRIX = ROOT / "docs/OPENMITRASTAR_F6_CERTIFICATION_MATRIX.json"
DOCUMENT = ROOT / "docs/OPENMITRASTAR_F6_CERTIFICATION_MATRIX.md"
ALLOWED = {"PROVEN", "PARTIAL", "PENDING", "BLOCKED"}


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_matrix(path: Path = MATRIX) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def validate_matrix(data: dict[str, Any], matrix_path: Path = MATRIX,
                    document_path: Path = DOCUMENT) -> tuple[Counter[str], list[str]]:
    errors: list[str] = []
    if data.get("schema") != "openmitrastar.f6-certification-matrix/v1":
        errors.append("schema mismatch")
    if data.get("as_of_date") != "2026-08-20":
        errors.append("certification date must be 2026-08-20")
    catalog = data.get("evidence_catalog")
    entries = data.get("entries")
    if not isinstance(catalog, dict) or not catalog:
        errors.append("evidence catalog missing")
        catalog = {}
    if not isinstance(entries, list) or not entries:
        errors.append("entries missing")
        entries = []

    for evidence_id, item in catalog.items():
        if not re.fullmatch(r"[a-z0-9_]+", evidence_id):
            errors.append(f"invalid evidence id: {evidence_id}")
            continue
        if not isinstance(item, dict):
            errors.append(f"invalid evidence item: {evidence_id}")
            continue
        path_value = item.get("path")
        expected = item.get("sha256")
        if not isinstance(path_value, str) or not path_value:
            errors.append(f"evidence path missing: {evidence_id}")
            continue
        path = ROOT / path_value
        if not path.is_file():
            errors.append(f"evidence file missing: {evidence_id}:{path_value}")
            continue
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
            errors.append(f"evidence sha invalid: {evidence_id}")
        elif digest(path) != expected:
            errors.append(f"evidence sha mismatch: {evidence_id}:{path_value}")

    ids: set[str] = set()
    counts: Counter[str] = Counter()
    for index, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(f"entry {index} is not an object")
            continue
        entry_id = entry.get("id")
        status = entry.get("status")
        if not isinstance(entry_id, str) or not re.fullmatch(r"F[0-6]-[0-9]{2}", entry_id):
            errors.append(f"invalid entry id at {index}: {entry_id}")
            continue
        if entry_id in ids:
            errors.append(f"duplicate entry id: {entry_id}")
        ids.add(entry_id)
        if status not in ALLOWED:
            errors.append(f"invalid status: {entry_id}:{status}")
            continue
        counts[status] += 1
        for field in ("phase", "system", "requirement", "proof_scope"):
            if not isinstance(entry.get(field), str) or not entry[field].strip():
                errors.append(f"missing {field}: {entry_id}")
        evidence_ids = entry.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids:
            errors.append(f"no evidence ids: {entry_id}")
        else:
            for evidence_id in evidence_ids:
                if evidence_id not in catalog:
                    errors.append(f"unknown evidence id: {entry_id}:{evidence_id}")
        missing = entry.get("missing_gate")
        blocker = entry.get("blocker")
        if status == "PROVEN":
            if missing or blocker:
                errors.append(f"PROVEN entry still has missing gate/blocker: {entry_id}")
        else:
            if not isinstance(missing, str) or not missing.strip():
                errors.append(f"incomplete entry lacks missing gate: {entry_id}")
        if status == "BLOCKED" and (not isinstance(blocker, str) or not blocker.strip()):
            errors.append(f"BLOCKED entry lacks blocker: {entry_id}")

    summary = data.get("summary", {})
    if summary.get("total") != len(entries):
        errors.append("summary total mismatch")
    for status in ALLOWED:
        if summary.get(status) != counts[status]:
            errors.append(f"summary count mismatch: {status}")

    if not document_path.is_file():
        errors.append("Markdown certification matrix missing")
    else:
        text = document_path.read_text(encoding="utf-8")
        source_hash = digest(matrix_path)
        if f"<!-- f6-source-json-sha256: {source_hash} -->" not in text:
            errors.append("Markdown source hash marker mismatch")
        if f"<!-- f6-entry-count: {len(entries)} -->" not in text:
            errors.append("Markdown entry-count marker mismatch")
        for entry in entries:
            marker = f"<!-- f6-entry: {entry['id']} status={entry['status']} -->"
            if marker not in text:
                errors.append(f"Markdown entry marker missing: {entry['id']}")
    return counts, errors


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--matrix", type=Path, default=MATRIX)
    parser.add_argument("--document", type=Path, default=DOCUMENT)
    parser.add_argument("--allow-incomplete", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    matrix_path = args.matrix if args.matrix.is_absolute() else ROOT / args.matrix
    document_path = args.document if args.document.is_absolute() else ROOT / args.document
    data = load_matrix(matrix_path)
    counts, errors = validate_matrix(data, matrix_path, document_path)
    if errors:
        for error in errors:
            print(f"F6_MATRIX_ERROR {error}", file=sys.stderr)
        return 3
    total = sum(counts.values())
    incomplete = total - counts["PROVEN"]
    result = {
        "schema": "openmitrastar.f6-verification-result/v1",
        "matrix_sha256": digest(matrix_path),
        "entries": total,
        "counts": {status: counts[status] for status in sorted(ALLOWED)},
        "complete": incomplete == 0,
    }
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(
            "F6_MATRIX_INTEGRITY_PASS "
            f"entries={total} evidence={len(data['evidence_catalog'])} "
            f"matrix_sha256={result['matrix_sha256']}"
        )
    if incomplete:
        print(
            "F6_CERTIFICATION_INCOMPLETE "
            f"PROVEN={counts['PROVEN']} PARTIAL={counts['PARTIAL']} "
            f"PENDING={counts['PENDING']} BLOCKED={counts['BLOCKED']}"
        )
        return 0 if args.allow_incomplete else 2
    print(f"F6_CERTIFICATION_PASS entries={total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
