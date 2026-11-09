#!/usr/bin/env python3
"""Evaluate three physical F223 runs against the accepted F219/F222 baseline."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "outputs/f3-certification/f219-realtek-2g-napi128-evaluation.json"


def rate_mbps(run: dict[str, object], direction: str) -> float:
    return float(run[f"controller_{direction}"]["speed_Bps"]) * 8 / 1_000_000


def evaluate(baseline: dict[str, object], runs: list[dict[str, object]]) -> dict[str, object]:
    if len(runs) != 3:
        raise ValueError("exactly three F223 candidate summaries are required")
    base_down = float(baseline["candidate"]["median_download_mbps"])
    base_up = float(baseline["candidate"]["median_upload_mbps"])
    down = [rate_mbps(run, "download") for run in runs]
    up = [rate_mbps(run, "upload") for run in runs]
    irq_no_desc = [int(run["emac_stats_delta"]["irq_no_rx_desc"]) for run in runs]
    sampled_no_desc = [int(run["emac_stats_delta"]["dma_no_rx_desc_samples"]) for run in runs]
    restarts = [int(run["emac_stats_delta"]["rx_restart_total"]) for run in runs]
    no_desc_restarts = [int(run["emac_stats_delta"]["rx_restart_reason_no_desc"]) for run in runs]
    alloc_failures = [int(run["emac_stats_delta"]["rx_alloc_failures"]) for run in runs]
    wlan_bad = [
        any(int(run["netdev_delta"]["wlan0"][key]) != 0 for key in ("rx_errs", "tx_errs", "rx_drop", "tx_drop"))
        for run in runs
    ]
    median_down = statistics.median(down)
    median_up = statistics.median(up)
    checks = {
        "three_runs_passed_transport": all(
            run["controller_download"]["pass"] and run["controller_upload"]["pass"] for run in runs
        ),
        "zero_rx_restarts": all(value == 0 for value in restarts),
        "zero_no_desc_restarts": all(value == 0 for value in no_desc_restarts),
        "irq_no_desc_near_zero": max(irq_no_desc) <= 1,
        "sampled_no_desc_near_zero": max(sampled_no_desc) <= 10,
        "zero_rx_alloc_failures": all(value == 0 for value in alloc_failures),
        "zero_wlan_errors_drops": not any(wlan_bad),
        "median_download_no_regression": median_down >= base_down * 0.95,
        "median_upload_no_regression": median_up >= base_up * 0.95,
    }
    passed = all(checks.values())
    return {
        "schema": "openmitrastar.f223-rxring256-physical-evaluation/v1",
        "status": "PASS" if passed else "FAIL",
        "decision": "GO_TO_DUAL_RADIO_SOAK" if passed else "NO_GO_RETAIN_F222",
        "checks": checks,
        "baseline": {"median_download_mbps": base_down, "median_upload_mbps": base_up},
        "candidate": {
            "download_mbps": [round(value, 3) for value in down],
            "upload_mbps": [round(value, 3) for value in up],
            "median_download_mbps": round(median_down, 3),
            "median_upload_mbps": round(median_up, 3),
            "irq_no_rx_desc": irq_no_desc,
            "dma_no_rx_desc_samples": sampled_no_desc,
            "rx_restart_total": restarts,
            "rx_restart_reason_no_desc": no_desc_restarts,
        },
        "limitations": [
            "PASS permits a separate simultaneous dual-radio soak; it is not release PASS",
            "F223 claims improvement only if descriptor starvation disappears without throughput regression",
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
