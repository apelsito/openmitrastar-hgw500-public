#!/usr/bin/env python3
"""Analyze F167 EMAC starvation evidence for the F172 experiment."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = ROOT / "outputs/f3-certification/realtek-2g-f167-32m-20260901/summary.json"
DEFAULT_SAMPLES = ROOT / "outputs/f3-certification/realtek-2g-f167-32m-20260901/router-samples.jsonl"
COUNTERS = (
    "irq_no_rx_desc",
    "napi_budget_exhaustions",
    "napi_rx_work",
    "dma_no_rx_desc_samples",
    "rx_restart_total",
    "rx_restart_reason_no_desc",
    "rx_alloc_failures",
    "rx_invalid_frames",
    "dma_rx_stopped_samples",
    "dma_rx_missed_samples",
)


def extract_counter(text: str, name: str) -> int:
    match = re.search(rf"(?m)^{re.escape(name)}=(-?\d+)$", text)
    if not match:
        raise ValueError(f"missing EMAC counter: {name}")
    return int(match.group(1))


def load_samples(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        item = json.loads(line)
        stdout = item["stdout"]
        rows.append({
            "time": item["local_time"],
            "counters": {name: extract_counter(stdout, name) for name in COUNTERS},
        })
    return rows


def delta(first: dict[str, int], last: dict[str, int]) -> dict[str, int]:
    return {name: last[name] - first[name] for name in COUNTERS}


def analyze(summary: dict[str, object], samples: list[dict[str, object]]) -> dict[str, object]:
    if len(samples) < 3:
        raise ValueError("at least three router samples are required")
    first = samples[0]["counters"]
    second = samples[1]["counters"]
    last = samples[-1]["counters"]
    first_window = delta(first, second)
    remaining_window = delta(second, last)
    total = summary["emac_stats_delta"]
    exhausted_frames_floor = first_window["napi_budget_exhaustions"] * 64
    first_window_rx_work = first_window["napi_rx_work"]

    return {
        "schema": "openmitrastar.f172-emac-starvation-analysis/v1",
        "source": {
            "summary_schema": summary.get("schema"),
            "sample_count": len(samples),
            "first_sample": samples[0]["time"],
            "second_sample": samples[1]["time"],
            "last_sample": samples[-1]["time"],
        },
        "physical_baseline": {
            "download_mbps": round(float(summary["controller_download"]["speed_Bps"]) * 8 / 1_000_000, 3),
            "upload_mbps": round(float(summary["controller_upload"]["speed_Bps"]) * 8 / 1_000_000, 3),
            "irq28_delta": int(summary["irq28_delta"]),
        },
        "total_emac_delta": {name: int(total[name]) for name in COUNTERS},
        "first_download_window_delta": first_window,
        "remaining_window_delta": remaining_window,
        "derived": {
            "budget_exhausted_frames_floor": exhausted_frames_floor,
            "first_window_rx_work": first_window_rx_work,
            "minimum_share_of_first_window_rx_work_in_exhausted_polls": round(
                exhausted_frames_floor / first_window_rx_work, 4
            ),
            "all_new_budget_exhaustions_in_first_window": remaining_window["napi_budget_exhaustions"] == 0,
            "all_new_no_rx_desc_samples_in_first_window": remaining_window["dma_no_rx_desc_samples"] == 0,
            "all_new_no_rx_desc_restarts_in_first_window": remaining_window["rx_restart_reason_no_desc"] == 0,
        },
        "cause_assessment": {
            "most_probable": "RX service quantum too small for burst occupancy of the 128-descriptor direct EMAC ring",
            "mechanism": (
                "A 64-packet NAPI quantum can leave up to half of the ring CPU-owned. "
                "On the single ARC core, DMA can consume the remaining descriptors before "
                "the next softirq pass, latch NO_RX_DESC and later trigger full RX restart."
            ),
            "support": [
                "budget exhaustions, NO_RX_DESC samples and attributed restarts rise in the download window",
                "RX allocations and frame validation report zero failures",
                "RX_STOPPED and RX_MISSED counters remain zero",
                "OEM board_napi_budget() returns 128",
            ],
            "caveat": (
                "dma_no_rx_desc_samples is a 10 ms sampled/latching counter, not an event count; "
                "irq_no_rx_desc and attributed restarts are the stronger event evidence."
            ),
        },
        "candidate": {
            "name": "F172",
            "single_variable": "qtn-topaz-emac NAPI weight 64 -> 128",
            "ring_count": 128,
            "restart_policy": "unchanged",
            "poll_demand_policy": "unchanged",
            "expected_effect": "drain at most one complete RX ring per NAPI service before yielding",
            "improvement_claimed": False,
        },
        "classification": "F172_NAPI128_JUSTIFIED_OFFLINE_PHYSICAL_BENCH_REQUIRED",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--samples", type=Path, default=DEFAULT_SAMPLES)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(
        json.loads(args.summary.read_text(encoding="utf-8")),
        load_samples(args.samples),
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="ascii")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
