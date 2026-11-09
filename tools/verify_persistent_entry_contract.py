#!/usr/bin/env python3
"""Verify that a persistent candidate preserves the proven post-CPIO entry code.

The HGW Bootbase handoff uses a fixed entry address.  If the initramfs CPIO grows
and shifts the post-CPIO payload while the entry address stays constant, the
router can hang immediately after "Transferring control to Linux" with no kernel
log.  This check catches that class before flash.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402


ENTRY_OFFSET = 0xB7E000
ENTRY_SAMPLE_BYTES = 256


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-raw", required=True, type=Path)
    parser.add_argument("--candidate-raw", required=True, type=Path)
    parser.add_argument("--entry-offset", default=hex(ENTRY_OFFSET))
    parser.add_argument("--sample-bytes", default=ENTRY_SAMPLE_BYTES, type=int)
    parser.add_argument("--json-out", type=Path)
    return parser.parse_args()


def int_auto(value: str) -> int:
    return int(value, 0)


def cpio_layout(raw: bytes) -> dict[str, object]:
    start, _entries, remainder = f71.parse_first_cpio(raw)
    return {
        "raw_bytes": len(raw),
        "cpio_start": start,
        "cpio_end": len(raw) - len(remainder),
        "remainder_bytes": len(remainder),
        "remainder_sha256": f71.sha256(remainder),
    }


def build_payload(base_raw: Path, candidate_raw: Path, entry_offset: int = ENTRY_OFFSET, sample_bytes: int = ENTRY_SAMPLE_BYTES) -> dict[str, object]:
    base = base_raw.read_bytes()
    candidate = candidate_raw.read_bytes()
    base_layout = cpio_layout(base)
    candidate_layout = cpio_layout(candidate)
    base_sample = base[entry_offset:entry_offset + sample_bytes]
    candidate_sample = candidate[entry_offset:entry_offset + sample_bytes]
    checks = {
        "raw_bytes_match": base_layout["raw_bytes"] == candidate_layout["raw_bytes"],
        "cpio_start_match": base_layout["cpio_start"] == candidate_layout["cpio_start"],
        "cpio_end_match": base_layout["cpio_end"] == candidate_layout["cpio_end"],
        "remainder_sha256_match": base_layout["remainder_sha256"] == candidate_layout["remainder_sha256"],
        "entry_sample_match": base_sample == candidate_sample,
        "entry_sample_nonzero": any(candidate_sample),
    }
    return {
        "schema": "openmitrastar.persistent-entry-contract/v1",
        "result": "PASS" if all(checks.values()) else "FAIL",
        "entry_offset": hex(entry_offset),
        "sample_bytes": sample_bytes,
        "base_raw": str(base_raw),
        "candidate_raw": str(candidate_raw),
        "base": base_layout,
        "candidate": candidate_layout,
        "checks": checks,
        "base_entry_sample_hex": base_sample[:16].hex(" "),
        "candidate_entry_sample_hex": candidate_sample[:16].hex(" "),
    }


def main_from_paths(base_raw: Path, candidate_raw: Path, json_out: Path, entry_offset: int = ENTRY_OFFSET, sample_bytes: int = ENTRY_SAMPLE_BYTES) -> int:
    payload = build_payload(base_raw, candidate_raw, entry_offset, sample_bytes)
    json_out.parent.mkdir(parents=True, exist_ok=True)
    json_out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="ascii")
    return 0 if payload["result"] == "PASS" else 1


def main() -> int:
    args = parse_args()
    offset = int_auto(str(args.entry_offset))
    payload = build_payload(args.base_raw, args.candidate_raw, offset, int(args.sample_bytes))
    text = json.dumps(payload, indent=2, sort_keys=True)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(text + "\n", encoding="ascii")
    print(text)
    return 0 if payload["result"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
