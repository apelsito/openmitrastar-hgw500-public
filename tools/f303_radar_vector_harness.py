#!/usr/bin/env python3
"""Offline harness for F303 OEM radar acquisition and dispatch vectors.

This tool deliberately does not implement DFS pulse classification. It models
only data normalization and control-flow decisions that are directly evidenced
by the preserved OEM radar.ko and Quantenna headers.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


PULSE_MASK = 0x07FFFFFF
TAG_BIT = 0x08000000
FIFO_DEPTH = 256
MAX_PULSES_PER_ZC_POLL = 18


def parse_u32(value: Any, field: str) -> int:
    if isinstance(value, str):
        value = int(value, 0)
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer or 0x-prefixed string")
    if not 0 <= value <= 0xFFFFFFFF:
        raise ValueError(f"{field} must fit in uint32")
    return value


def decode_fifo_pairs(mem_h_words: list[Any], mem_l_words: list[Any]) -> list[dict[str, Any]]:
    if len(mem_h_words) != len(mem_l_words):
        raise ValueError("mem_h_words and mem_l_words must have equal length")
    if len(mem_h_words) > FIFO_DEPTH:
        raise ValueError(f"a vector cannot exceed the {FIFO_DEPTH}-entry FIFO")

    pulses: list[dict[str, Any]] = []
    previous_start: int | None = None
    for index, (raw_h, raw_l) in enumerate(zip(mem_h_words, mem_l_words)):
        mem_h = parse_u32(raw_h, f"mem_h_words[{index}]")
        mem_l = parse_u32(raw_l, f"mem_l_words[{index}]")
        start = mem_h & PULSE_MASK
        stop = mem_l & PULSE_MASK
        width = (stop - start) & PULSE_MASK
        pri = None if previous_start is None else (start - previous_start) & PULSE_MASK
        pulses.append(
            {
                "index": index,
                "start": start,
                "stop": stop,
                "width": width,
                "pri": pri,
                "tag_bit": bool(mem_l & TAG_BIT),
                "mem_h_meta_31_27": (mem_h >> 27) & 0x1F,
                "mem_l_meta_31_27": (mem_l >> 27) & 0x1F,
            }
        )
        previous_start = start
    return pulses


def model_dispatch(oracle: dict[str, Any]) -> dict[str, Any]:
    """Model the evidenced dispatcher while treating classifiers as oracles."""

    poll_lsr_hit = bool(oracle.get("poll_lsr_hit", False))
    itlv_enabled = bool(oracle.get("itlv_enabled", False))
    itlv_hit = bool(oracle.get("itlv_hit", False))
    ssr_bounds_hit = bool(oracle.get("ssr_bounds_hit", False))
    lsr_enabled = bool(oracle.get("lsr_enabled", False))
    lsr_hit = bool(oracle.get("lsr_hit", False))
    reject_input = bool(
        oracle.get("post_filter_reject_input", oracle.get("check_radar_rejected", False))
    )
    noreject_override = bool(oracle.get("noreject_override", False))
    callback_registered = bool(oracle.get("callback_registered", True))

    classes: list[str] = []
    if poll_lsr_hit:
        classes.append("lsr_poll")

    if itlv_enabled:
        if itlv_hit:
            classes.append("itlv")
    elif ssr_bounds_hit:
        classes.append("ssr")

    if lsr_enabled and lsr_hit:
        classes.append("lsr")

    candidate = bool(classes)
    suppressed = reject_input and not noreject_override
    callback_fired = candidate and not suppressed and callback_registered
    return {
        "classifier_inputs_are_oracles": True,
        "classes": classes,
        "candidate": candidate,
        "post_filter_reject_input": reject_input,
        "noreject_override": noreject_override,
        "suppressed": suppressed,
        "callback_registered": callback_registered,
        "mark_radar_callback_fired": callback_fired,
    }


def validate_zero_crossings(polls: list[dict[str, Any]], pulse_count: int) -> dict[str, int]:
    rows = 0
    samples = 0
    for poll_index, poll in enumerate(polls):
        if not isinstance(poll, dict):
            raise ValueError(f"zero_crossing_polls[{poll_index}] must be an object")
        entries = poll.get("pulses", [])
        if not isinstance(entries, list):
            raise ValueError(f"zero_crossing_polls[{poll_index}].pulses must be a list")
        if len(entries) > MAX_PULSES_PER_ZC_POLL:
            raise ValueError(
                f"zero-crossing poll {poll_index} exceeds the evidenced "
                f"{MAX_PULSES_PER_ZC_POLL}-pulse cap"
            )
        for row_index, row in enumerate(entries):
            if not isinstance(row, list):
                raise ValueError(
                    f"zero_crossing_polls[{poll_index}].pulses[{row_index}] must be a list"
                )
            for sample_index, sample in enumerate(row):
                parsed = parse_u32(
                    sample,
                    f"zero_crossing_polls[{poll_index}].pulses[{row_index}][{sample_index}]",
                )
                if parsed > 0xFF:
                    raise ValueError("zero-crossing samples must fit in uint8")
            rows += 1
            samples += len(row)
    if rows > pulse_count and pulse_count != 0:
        raise ValueError("zero-crossing rows cannot exceed decoded pulse count")
    return {"polls": len(polls), "pulse_rows": rows, "samples": samples}


def run_vector(vector: dict[str, Any]) -> dict[str, Any]:
    if vector.get("schema") != "openmitrastar.f303-radar-vector/v1":
        raise ValueError("unsupported or missing schema")
    fifo = vector.get("fifo", {})
    if not isinstance(fifo, dict):
        raise ValueError("fifo must be an object")
    pulses = decode_fifo_pairs(fifo.get("mem_h_words", []), fifo.get("mem_l_words", []))
    zc_summary = validate_zero_crossings(vector.get("zero_crossing_polls", []), len(pulses))
    dispatch = model_dispatch(vector.get("oracle", {}))

    expected = vector.get("expected", {})
    mismatches: list[str] = []
    if "pulse_count" in expected and expected["pulse_count"] != len(pulses):
        mismatches.append("pulse_count")
    if "mark_radar_callback_fired" in expected:
        if bool(expected["mark_radar_callback_fired"]) != dispatch["mark_radar_callback_fired"]:
            mismatches.append("mark_radar_callback_fired")
    if "classes" in expected and expected["classes"] != dispatch["classes"]:
        mismatches.append("classes")

    return {
        "schema": "openmitrastar.f303-radar-vector-result/v1",
        "name": vector.get("name", "unnamed"),
        "source": vector.get("source", "unknown"),
        "classification_algorithm": "NOT_IMPLEMENTED",
        "pulse_count": len(pulses),
        "pulses": pulses,
        "zero_crossings": zc_summary,
        "dispatch": dispatch,
        "expectations": {"mismatches": mismatches, "pass": not mismatches},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("vector", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    result = run_vector(json.loads(args.vector.read_text(encoding="utf-8")))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0 if result["expectations"]["pass"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
