#!/usr/bin/env python3
"""Create a conservatively renamed firmware decompilation export.

Only rows explicitly marked high_confidence=yes are applied. The original
Ghidra export remains untouched and the replacement count is recorded.
"""
from __future__ import annotations

import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS = ROOT / "outputs/radio-re/decompiled/firmware"
HINTS = CORPUS / "function_hints.tsv"
SOURCE = CORPUS / "qtn_driver.qtn_ruby.0.bin.decompiled.c"
OUTPUT = CORPUS / "qtn_driver.qtn_ruby.0.bin.named.decompiled.c"
REPORT = CORPUS / "applied_function_hints.tsv"


def main() -> int:
    with HINTS.open(encoding="utf-8", newline="") as handle:
        rows = [row for row in csv.DictReader(handle, delimiter="\t") if row["high_confidence"] == "yes"]
    assert len(rows) == 9, f"expected 9 high-confidence hints, got {len(rows)}"
    originals = [row["original"] for row in rows]
    candidates = [row["candidate"] for row in rows]
    assert len(set(originals)) == len(rows), "high-confidence source names must be unique"
    assert len(set(candidates)) == len(rows), "high-confidence candidate names must be unique"

    text = SOURCE.read_text(encoding="utf-8")
    applied: list[dict[str, str | int]] = []
    for row in rows:
        pattern = re.compile(rf"\b{re.escape(row['original'])}\b")
        text, count = pattern.subn(row["candidate"], text)
        assert count > 0, f"source function not present: {row['original']}"
        applied.append({**row, "replacement_count": count})

    OUTPUT.write_text(text, encoding="utf-8", newline="\n")
    fields = list(rows[0]) + ["replacement_count"]
    with REPORT.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(applied)
    print(f"applied {len(applied)} high-confidence names to {OUTPUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
