#!/usr/bin/env python3
"""Qualify TFTP -> YMODEM handoff from one explicit, pre-erase failure only.

This module reads/writes host evidence. It has no serial, network or flash API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

SCHEMA = "openmitrastar.flash-attempt-handoff/v1"
ABORT = "OMLYOKO_TFTP_PRE_ERASE_ABORT=1"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def marker(attempt_id: str, candidate: str, current_crc: str) -> str:
    if not re.fullmatch(r"[0-9a-f]{32}", attempt_id): raise ValueError("invalid attempt identity")
    if not re.fullmatch(r"[0-9a-f]{64}", candidate): raise ValueError("invalid candidate identity")
    if not re.fullmatch(r"[0-9a-f]{8}", current_crc): raise ValueError("invalid expected current CRC")
    return f"{ABORT} attempt_id={attempt_id} candidate={candidate} current_live_crc={current_crc}"


def classify(*, attempt_id: str, candidate: str, current_crc: str, transport: str,
             returncode: int, backend: bytes, uart: bytes | None) -> dict:
    expected = marker(attempt_id, candidate, current_crc)
    text = backend.decode("utf-8", errors="replace")
    trace = (uart or b"").decode("utf-8", errors="replace")
    forbidden = re.search(r"spi_flash\s+(?:erase|write)\b|MTD4_BOOTBASE_READBACK_PASS=1|MTD4_FLASH_AND_READBACK_PASS=1", text + "\n" + trace, re.I)
    allowed = (type(returncode) is int and returncode != 0 and transport == "tftp"
               and bool(uart) and text.splitlines().count(expected) == 1 and not forbidden)
    return {"schema": SCHEMA, "attempt_id": attempt_id, "candidate_sha256": candidate,
            "expected_current_live_crc32": current_crc, "transport": transport, "backend_returncode": returncode,
            "backend_log_sha256": digest(backend), "uart_log_sha256": digest(uart) if uart is not None else None,
            "fallback_allowed": bool(allowed), "status": "PRE_ERASE_TFTP_ABORT" if allowed else "NO_AUTOMATIC_HANDOFF"}


def record_attempt(directory: Path, *, attempt_id: str, candidate: str, current_crc: str,
                   transport: str, returncode: int) -> dict:
    backend = (directory / "backend.log").read_bytes()
    uart_path = directory / "bootbase-flash-uart.log"
    result = classify(attempt_id=attempt_id, candidate=candidate, current_crc=current_crc,
                      transport=transport, returncode=returncode, backend=backend,
                      uart=uart_path.read_bytes() if uart_path.is_file() else None)
    target = directory / "attempt-result.json"
    with target.open("x", encoding="ascii") as output:
        output.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def verify_attempt(directory: Path, *, attempt_id: str, candidate: str, current_crc: str) -> dict:
    # Fixed basenames: never follow paths supplied by an evidence document.
    paths = [directory / name for name in ("attempt-result.json", "backend.log", "bootbase-flash-uart.log")]
    if any(path.is_symlink() or not path.is_file() for path in paths): raise ValueError("handoff evidence missing or indirect")
    stored = json.loads(paths[0].read_text(encoding="ascii"))
    recomputed = classify(attempt_id=attempt_id, candidate=candidate, current_crc=current_crc,
                          transport=stored.get("transport"), returncode=stored.get("backend_returncode"),
                          backend=paths[1].read_bytes(), uart=paths[2].read_bytes())
    if stored != recomputed or recomputed["fallback_allowed"] is not True:
        raise ValueError("automatic handoff refused: unknown, mismatched or post-erase outcome")
    return recomputed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", required=True, type=Path)
    parser.add_argument("--attempt-id", required=True)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--current-live-crc32", required=True)
    args = parser.parse_args()
    try:
        result = verify_attempt(args.verify, attempt_id=args.attempt_id, candidate=args.candidate_sha256, current_crc=args.current_live_crc32)
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(json.dumps({"status": "REFUSED", "reason": str(error)})); return 1
    print(json.dumps({"status": "PASS_PRE_ERASE_HANDOFF", "attempt_id": result["attempt_id"]})); return 0


if __name__ == "__main__": raise SystemExit(main())
