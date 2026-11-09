#!/usr/bin/env python3
"""Extract evidence-backed function-name hints from Ghidra C corpora.

The script never renames symbols. It associates each anonymous function with
function-like identifiers present in diagnostic-string symbols referenced by
its own decompiled body and records whether a candidate is unique.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT = ROOT / "outputs/radio-re/decompiled/firmware"
DEFAULT_OUTPUT = DEFAULT_INPUT / "function_hints.tsv"

HEADER = re.compile(r"^ \* (?P<name>\S+) @ (?P<entry>\S+)$", re.MULTILINE)
STRING_SYMBOL = re.compile(r"\bs_([A-Za-z0-9_$]+)_ram_[0-9a-fA-F]+\b")
IDENTIFIER = re.compile(
    r"(?i)(?:qtn|ieee80211|topaz|muc|auc|scs|dfs|ralg|sscl|tqe|hbm|dsp)_[a-z0-9_]{4,}"
)


@dataclass(frozen=True)
class Hint:
    firmware: str
    entry: str
    original: str
    candidate: str
    references: int
    evidence: tuple[str, ...]


def blocks(source: str):
    matches = list(HEADER.finditer(source))
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(source)
        yield match.group("entry"), match.group("name"), source[match.end() : end]


def candidates(symbol: str) -> set[str]:
    # Ghidra uses a double underscore where punctuation separated the leading
    # function/file token from the rest of a printf-style diagnostic.
    prefix = symbol.split("__", 1)[0]
    found = {match.group(0).lower() for match in IDENTIFIER.finditer(prefix)}
    message_markers = (
        "_cannot_",
        "_can_not_",
        "_can_t_",
        "_failed_",
        "_failure_",
        "_unexpected_",
        "_invalid_",
        "_error_",
        "_exceeding_",
    )
    normalized = set()
    for value in found:
        for marker in message_markers:
            if marker in value:
                value = value.split(marker, 1)[0]
        normalized.add(value)
    return {
        value.rstrip("_")
        for value in normalized
        if 7 <= len(value) <= 80
        and not value.endswith("_c")
        and "0x" not in value
        and "_x_" not in value
        and not value.startswith(("dsp_assert", "muc_exception", "auc_exception"))
    }


def extract(path: Path) -> list[Hint]:
    source = path.read_text(encoding="utf-8", errors="replace")
    hints: list[Hint] = []
    for entry, original, body in blocks(source):
        by_candidate: dict[str, list[str]] = defaultdict(list)
        for symbol in STRING_SYMBOL.findall(body):
            for candidate in candidates(symbol):
                by_candidate[candidate].append(symbol)
        for candidate, evidence in by_candidate.items():
            hints.append(
                Hint(
                    firmware=path.name.removesuffix(".decompiled.c"),
                    entry=entry,
                    original=original,
                    candidate=candidate,
                    references=len(evidence),
                    evidence=tuple(sorted(set(evidence))),
                )
            )
    return hints


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    all_hints: list[Hint] = []
    for path in sorted(args.input.glob("*.decompiled.c")):
        all_hints.extend(extract(path))

    candidate_functions: dict[tuple[str, str], set[str]] = defaultdict(set)
    function_candidates: dict[tuple[str, str], set[str]] = defaultdict(set)
    for hint in all_hints:
        candidate_functions[(hint.firmware, hint.candidate)].add(hint.entry)
        function_candidates[(hint.firmware, hint.entry)].add(hint.candidate)

    rows = []
    for hint in all_hints:
        unique = len(candidate_functions[(hint.firmware, hint.candidate)]) == 1
        score = hint.references * 2 + (4 if unique else 0)
        if hint.candidate.startswith(("qtn_", "ieee80211_")):
            score += 2
        high_confidence = (
            unique
            and len(function_candidates[(hint.firmware, hint.entry)]) == 1
            and hint.references >= 2
            and score >= 10
        )
        rows.append((score, unique, high_confidence, hint))
    rows.sort(key=lambda row: (-row[0], row[3].firmware, row[3].entry, row[3].candidate))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t", lineterminator="\n")
        writer.writerow(
            ["firmware", "entry", "original", "candidate", "score", "unique", "high_confidence", "references", "evidence"]
        )
        for score, unique, high_confidence, hint in rows:
            writer.writerow(
                [
                    hint.firmware,
                    hint.entry,
                    hint.original,
                    hint.candidate,
                    score,
                    "yes" if unique else "no",
                    "yes" if high_confidence else "no",
                    hint.references,
                    " | ".join(hint.evidence),
                ]
            )

    unique_count = sum(unique for _, unique, _, _ in rows)
    high_count = sum(high for _, _, high, _ in rows)
    print(f"wrote {len(rows)} hints ({unique_count} unique, {high_count} high-confidence) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
