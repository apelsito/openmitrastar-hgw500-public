#!/usr/bin/env python3
"""Evaluate three physical F287 NAPI-256 runs against the F285 baseline."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "outputs/f3-certification/f285-realtek-2g-current-evaluation-20260903.json"


def rate_mbps(run: dict[str, object], direction: str) -> float:
    return float(run[f"controller_{direction}"]["speed_Bps"]) * 8 / 1_000_000


def median_counter(runs: list[dict[str, object]], name: str) -> float:
    return statistics.median(int(run["emac_stats_delta"][name]) for run in runs)


def evaluate(baseline: dict[str, object], runs: list[dict[str, object]]) -> dict[str, object]:
    if len(runs) != 3:
        raise ValueError("exactly three F287 candidate summaries are required")
    baseline_candidate = baseline["candidate"]
    base_down = float(baseline_candidate["median_download_mbps"])
    base_up = float(baseline_candidate["median_upload_mbps"])
    base_irq_no_desc = statistics.median(int(value) for value in baseline_candidate["irq_no_rx_desc"])
    base_sampled_no_desc = statistics.median(int(value) for value in baseline_candidate["dma_no_rx_desc_samples"])
    base_restarts = statistics.median(int(value) for value in baseline_candidate["rx_restart_total"])
    down = [rate_mbps(run, "download") for run in runs]
    up = [rate_mbps(run, "upload") for run in runs]
    irq_no_desc = [int(run["emac_stats_delta"]["irq_no_rx_desc"]) for run in runs]
    sampled_no_desc = [int(run["emac_stats_delta"]["dma_no_rx_desc_samples"]) for run in runs]
    restarts = [int(run["emac_stats_delta"]["rx_restart_total"]) for run in runs]
    no_desc_restarts = [int(run["emac_stats_delta"]["rx_restart_reason_no_desc"]) for run in runs]
    budget_exhaustions = [int(run["emac_stats_delta"]["napi_budget_exhaustions"]) for run in runs]
    alloc_failures = [int(run["emac_stats_delta"]["rx_alloc_failures"]) for run in runs]
    wlan_bad = [
        any(int(run["netdev_delta"]["wlan0"][key]) != 0 for key in ("rx_errs", "tx_errs", "rx_drop", "tx_drop"))
        for run in runs
    ]
    median_down = statistics.median(down)
    median_up = statistics.median(up)
    median_irq_no_desc = statistics.median(irq_no_desc)
    median_sampled_no_desc = statistics.median(sampled_no_desc)
    median_restarts = statistics.median(restarts)
    checks = {
        "three_runs_passed_transport": all(
            run["controller_download"]["pass"] and run["controller_upload"]["pass"]
            and run.get("router_health_gate", {}).get("pass") is True
            for run in runs
        ),
        "median_download_no_regression": median_down >= base_down * 0.95,
        "median_upload_no_regression": median_up >= base_up * 0.95,
        "irq_no_desc_reduced_50pct": median_irq_no_desc <= base_irq_no_desc * 0.5,
        "sampled_no_desc_reduced_50pct": median_sampled_no_desc <= base_sampled_no_desc * 0.5,
        "zero_no_desc_restarts": all(value == 0 for value in no_desc_restarts),
        "restart_median_improved": median_restarts < base_restarts,
        "zero_rx_alloc_failures": all(value == 0 for value in alloc_failures),
        "zero_wlan_errors_drops": not any(wlan_bad),
    }
    hard_checks = (
        "three_runs_passed_transport",
        "median_download_no_regression",
        "median_upload_no_regression",
        "zero_rx_alloc_failures",
        "zero_wlan_errors_drops",
    )
    improvement_checks = (
        "irq_no_desc_reduced_50pct",
        "sampled_no_desc_reduced_50pct",
        "restart_median_improved",
    )
    passed = all(checks.values())
    improved_but_incomplete = (
        all(checks[name] for name in hard_checks)
        and all(checks[name] for name in improvement_checks)
    )
    status = "PASS" if passed else "PARTIAL" if improved_but_incomplete else "FAIL"
    decision = (
        "KEEP_F287"
        if passed
        else "KEEP_F287_DIAGNOSTIC_BASELINE"
        if improved_but_incomplete
        else "ROLL_BACK_TO_F285"
    )
    return {
        "schema": "openmitrastar.f287-emac-napi256-physical-evaluation/v1",
        "status": status,
        "decision": decision,
        "checks": checks,
        "baseline": {
            "median_download_mbps": base_down,
            "median_upload_mbps": base_up,
            "median_irq_no_rx_desc": base_irq_no_desc,
            "median_dma_no_rx_desc_samples": base_sampled_no_desc,
            "median_rx_restarts": base_restarts,
        },
        "candidate": {
            "download_mbps": [round(value, 3) for value in down],
            "upload_mbps": [round(value, 3) for value in up],
            "median_download_mbps": round(median_down, 3),
            "median_upload_mbps": round(median_up, 3),
            "irq_no_rx_desc": irq_no_desc,
            "median_irq_no_rx_desc": median_irq_no_desc,
            "dma_no_rx_desc_samples": sampled_no_desc,
            "median_dma_no_rx_desc_samples": median_sampled_no_desc,
            "napi_budget_exhaustions": budget_exhaustions,
            "rx_restart_total": restarts,
            "rx_restart_reason_no_desc": no_desc_restarts,
        },
        "limitations": [
            "A PASS only accepts the NAPI-256 datapath experiment; it is not Lyoko release certification.",
            "A separate 5 GHz sanity gate and prolonged dual-radio soak remain required.",
        ],
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
    return 0 if result["status"] in {"PASS", "PARTIAL"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
