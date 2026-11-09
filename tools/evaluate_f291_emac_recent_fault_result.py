#!/usr/bin/env python3
"""Evaluate F291 recent-fault recovery runs against the F290 baseline."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "outputs/f3-certification/f290-emac-restart-context-20260903/f290-evaluation.json"


def rate_mbps(run: dict[str, object], direction: str) -> float:
    return float(run[f"controller_{direction}"]["speed_Bps"]) * 8 / 1_000_000


def parse_hex(value: object) -> int:
    return int(str(value or "0"), 16)


def evaluate(baseline: dict[str, object], runs: list[dict[str, object]]) -> dict[str, object]:
    if len(runs) != 3:
        raise ValueError("exactly three F291 summaries are required")
    baseline_candidate = baseline["candidate"]
    down = [rate_mbps(run, "download") for run in runs]
    up = [rate_mbps(run, "upload") for run in runs]
    restarts = [int(run["emac_stats_delta"]["rx_restart_total"]) for run in runs]
    stagnant = [int(run["emac_stats_delta"]["rx_restart_reason_stagnant"]) for run in runs]
    stopped = [int(run["emac_stats_delta"]["rx_restart_reason_stopped"]) for run in runs]
    missed = [int(run["emac_stats_delta"]["rx_restart_reason_missed"]) for run in runs]
    no_desc_restarts = [int(run["emac_stats_delta"]["rx_restart_reason_no_desc"]) for run in runs]
    no_desc = [int(run["emac_stats_delta"]["irq_no_rx_desc"]) for run in runs]
    sampled = [int(run["emac_stats_delta"]["dma_no_rx_desc_samples"]) for run in runs]
    context = []
    for run in runs:
        last = run["emac_stats_last"]
        restarted = int(run["emac_stats_delta"]["rx_restart_total"]) > 0
        context.append({
            "restart_observed": restarted,
            "fault_status": parse_hex(last.get("rx_restart_last_dma_status")) & 0xE0,
            "remembered_fault_status": parse_hex(last.get("last_rx_fault_status")),
            "fault_age_ms": int(last.get("rx_restart_last_fault_age_ms") or 0),
            "idle_ms": int(last.get("rx_restart_last_idle_ms") or 0),
            "head_dma_owned": bool(parse_hex(last.get("rx_restart_last_head_status")) & 0x80000000),
        })
    restarted_contexts = [item for item in context if item["restart_observed"]]
    median_down = statistics.median(down)
    median_up = statistics.median(up)
    checks = {
        "three_runs_passed_transport": all(
            run["controller_download"]["pass"] and run["controller_upload"]["pass"]
            and run.get("router_health_gate", {}).get("pass") is True
            for run in runs
        ),
        "median_download_no_regression": median_down >= float(baseline_candidate["median_download_mbps"]) * 0.95,
        "median_upload_no_regression": median_up >= float(baseline_candidate["median_upload_mbps"]) * 0.95,
        "no_latched_no_desc": max(sampled) == 0,
        "zero_stagnant_restarts": all(value == 0 for value in stagnant),
        "restart_context_complete": not restarted_contexts or all(
            item["remembered_fault_status"] & 0xE0
            and 0 < item["fault_age_ms"] <= 10_000
            and item["head_dma_owned"]
            for item in restarted_contexts
        ),
        "all_restarts_cause_attributed": all(
            total == no_desc_reason + stopped_reason + missed_reason
            for total, no_desc_reason, stopped_reason, missed_reason in zip(
                restarts, no_desc_restarts, stopped, missed
            )
        ),
        "zero_rx_alloc_failures": all(int(run["emac_stats_delta"]["rx_alloc_failures"]) == 0 for run in runs),
    }
    passed = all(checks.values())
    return {
        "schema": "openmitrastar.f291-emac-recent-fault-restart-physical-evaluation/v1",
        "status": "PASS" if passed else "FAIL",
        "decision": "KEEP_F291" if passed else "ROLL_BACK_TO_F290",
        "checks": checks,
        "baseline": {
            "median_download_mbps": baseline_candidate["median_download_mbps"],
            "median_upload_mbps": baseline_candidate["median_upload_mbps"],
        },
        "candidate": {
            "download_mbps": [round(value, 3) for value in down],
            "upload_mbps": [round(value, 3) for value in up],
            "median_download_mbps": round(median_down, 3),
            "median_upload_mbps": round(median_up, 3),
            "irq_no_rx_desc": no_desc,
            "dma_no_rx_desc_samples": sampled,
            "rx_restart_total": restarts,
            "rx_restart_reason_no_desc": no_desc_restarts,
            "rx_restart_reason_stopped": stopped,
            "rx_restart_reason_missed": missed,
            "rx_restart_reason_stagnant": stagnant,
            "restart_context": context,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--candidate-summary", type=Path, action="append", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.baseline.read_text(encoding="utf-8")),
        [json.loads(path.read_text(encoding="utf-8")) for path in args.candidate_summary],
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(rendered, encoding="ascii")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
