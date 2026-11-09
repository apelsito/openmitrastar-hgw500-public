#!/usr/bin/env python3
"""Evaluate three physical F172 2.4 GHz runs against the F167 baseline."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "outputs/f3-certification/realtek-2g-f167-32m-20260901/summary.json"


def rate_mbps(run: dict[str, object], direction: str) -> float:
    return float(run[f"controller_{direction}"]["speed_Bps"]) * 8 / 1_000_000


def evaluate(baseline: dict[str, object], candidates: list[dict[str, object]]) -> dict[str, object]:
    if len(candidates) != 3:
        raise ValueError("exactly three F172 candidate summaries are required")

    base_down = rate_mbps(baseline, "download")
    base_up = rate_mbps(baseline, "upload")
    downs = [rate_mbps(run, "download") for run in candidates]
    ups = [rate_mbps(run, "upload") for run in candidates]
    irq_no_desc = [int(run["emac_stats_delta"]["irq_no_rx_desc"]) for run in candidates]
    sampled_no_desc = [int(run["emac_stats_delta"]["dma_no_rx_desc_samples"]) for run in candidates]
    budget_exhaustions = [int(run["emac_stats_delta"]["napi_budget_exhaustions"]) for run in candidates]
    restarts = [int(run["emac_stats_delta"]["rx_restart_total"]) for run in candidates]
    restart_no_desc = [int(run["emac_stats_delta"]["rx_restart_reason_no_desc"]) for run in candidates]
    alloc_failures = [int(run["emac_stats_delta"]["rx_alloc_failures"]) for run in candidates]
    wlan_bad = [
        any(int(run["netdev_delta"]["wlan0"][key]) != 0 for key in ("rx_errs", "tx_errs", "rx_drop", "tx_drop"))
        for run in candidates
    ]

    median_down = statistics.median(downs)
    median_up = statistics.median(ups)
    median_irq_no_desc = statistics.median(irq_no_desc)
    checks = {
        "three_runs_passed_transport": all(
            run["controller_download"]["pass"] and run["controller_upload"]["pass"]
            for run in candidates
        ),
        "zero_rx_restarts": all(value == 0 for value in restarts),
        "zero_no_desc_restarts": all(value == 0 for value in restart_no_desc),
        "irq_no_desc_reduced_90pct": median_irq_no_desc <= 1.5,
        "zero_rx_alloc_failures": all(value == 0 for value in alloc_failures),
        "zero_wlan_errors_drops": not any(wlan_bad),
        "median_download_gain_15pct": median_down >= base_down * 1.15,
        "median_upload_within_5pct": median_up >= base_up * 0.95,
    }
    return {
        "schema": "openmitrastar.f172-physical-result-evaluation/v1",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "decision": "GO_TO_DUAL_RADIO_SOAK" if all(checks.values()) else "NO_GO_RETAIN_F170_OR_ACCEPTED_F171",
        "checks": checks,
        "baseline": {
            "download_mbps": round(base_down, 3),
            "upload_mbps": round(base_up, 3),
            "irq_no_rx_desc": int(baseline["emac_stats_delta"]["irq_no_rx_desc"]),
            "napi_budget_exhaustions": int(baseline["emac_stats_delta"]["napi_budget_exhaustions"]),
            "rx_restart_total": int(baseline["emac_stats_delta"]["rx_restart_total"]),
        },
        "candidate": {
            "download_mbps": [round(value, 3) for value in downs],
            "upload_mbps": [round(value, 3) for value in ups],
            "median_download_mbps": round(median_down, 3),
            "median_upload_mbps": round(median_up, 3),
            "irq_no_rx_desc": irq_no_desc,
            "dma_no_rx_desc_samples": sampled_no_desc,
            "napi_budget_exhaustions": budget_exhaustions,
            "rx_restart_total": restarts,
            "rx_restart_reason_no_desc": restart_no_desc,
        },
        "limitations": [
            "PASS permits the separate simultaneous dual-radio soak; it is not release PASS",
            "dma_no_rx_desc_samples is reported but not used as the primary event gate",
            "physical improvement is not claimed until this evaluator consumes real F172 runs",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser()
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
