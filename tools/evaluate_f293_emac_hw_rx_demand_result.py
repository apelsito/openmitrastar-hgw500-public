#!/usr/bin/env python3
"""Evaluate F293 hardware RX-demand telemetry against the F290 baseline."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "outputs/f3-certification/f290-emac-restart-context-20260903/f290-evaluation.json"
U32_MAX = 0xFFFFFFFF


def rate_mbps(run: dict[str, object], direction: str) -> float:
    return float(run[f"controller_{direction}"]["speed_Bps"]) * 8 / 1_000_000


def number(mapping: dict[str, object], key: str) -> int:
    return int(mapping.get(key) or 0)


def evaluate(baseline: dict[str, object], runs: list[dict[str, object]]) -> dict[str, object]:
    if len(runs) != 3:
        raise ValueError("exactly three F293 summaries are required")

    baseline_candidate = baseline["candidate"]
    down = [rate_mbps(run, "download") for run in runs]
    up = [rate_mbps(run, "upload") for run in runs]
    median_down = statistics.median(down)
    median_up = statistics.median(up)
    contexts: list[dict[str, object]] = []

    for run in runs:
        delta = run["emac_stats_delta"]
        last = run["emac_stats_last"]
        restarted = number(delta, "rx_restart_total") > 0
        progress_age = number(last, "rx_restart_last_mac_rx_progress_age_ms")
        missed_total = number(last, "rx_restart_last_dma_missed_frames_total")
        mac_rx_valid = number(last, "mac_rx_frames_valid") == 1
        restart_mac_rx_delta = number(last, "rx_restart_last_mac_rx_delta")
        progress_observations = number(last, "mac_rx_progress_observations")
        progress_age_valid = progress_age < U32_MAX
        contexts.append({
            "restart_observed": restarted,
            "mac_rx_frames_valid": mac_rx_valid,
            "mac_rx_samples": number(last, "mac_rx_samples"),
            "mac_rx_read_failures": number(last, "mac_rx_read_failures"),
            "mac_rx_progress_observations": progress_observations,
            "restart_mac_rx_frames": number(last, "rx_restart_last_mac_rx_frames"),
            "restart_mac_rx_delta": restart_mac_rx_delta,
            "restart_mac_rx_progress_age_ms": progress_age,
            "restart_dma_missed_frames": number(last, "rx_restart_last_dma_missed_frames"),
            "restart_dma_missed_frames_total": missed_total,
            "hardware_ingress_near_restart": restarted and (
                (
                    mac_rx_valid
                    and progress_age_valid
                    and (restart_mac_rx_delta > 0 or progress_observations > 0)
                )
                or missed_total > 0
            ),
        })

    restart_contexts = [item for item in contexts if item["restart_observed"]]
    transport_checks = {
        "three_runs_passed_transport": all(
            run["controller_download"]["pass"]
            and run["controller_upload"]["pass"]
            and run.get("router_health_gate", {}).get("pass") is True
            for run in runs
        ),
        "zero_rx_alloc_failures": all(number(run["emac_stats_delta"], "rx_alloc_failures") == 0 for run in runs),
    }
    performance_checks = {
        "median_download_no_regression": median_down >= float(baseline_candidate["median_download_mbps"]) * 0.95,
        "median_upload_no_regression": median_up >= float(baseline_candidate["median_upload_mbps"]) * 0.95,
    }
    telemetry_checks = {
        # F293 samples the hardware counters only from the stall-poke path.
        # Healthy runs with no restart therefore have no sampling obligation.
        "restart_counter_available": all(item["mac_rx_frames_valid"] for item in restart_contexts),
        "restart_counter_sampled": all(item["mac_rx_samples"] > 0 for item in restart_contexts),
        "hardware_counter_reads_clean": all(item["mac_rx_read_failures"] == 0 for item in contexts),
    }
    checks = {**transport_checks, **performance_checks, **telemetry_checks}
    transport_passed = all(transport_checks.values())
    performance_passed = all(performance_checks.values())
    telemetry_passed = all(telemetry_checks.values())

    if not transport_passed or not telemetry_passed:
        status = "FAIL"
        decision = "RETAIN_F292_AND_REVIEW_F293_TELEMETRY"
    elif not performance_passed and any(item["hardware_ingress_near_restart"] for item in restart_contexts):
        status = "PARTIAL"
        decision = "BUILD_F299_DEMAND_ACCELERATION_KEEP_F290_FALLBACK"
    elif not performance_passed:
        status = "PARTIAL"
        decision = "RETAIN_F292_AND_EXTEND_F293_OBSERVATION"
    elif not restart_contexts:
        status = "PASS"
        decision = "KEEP_F293_TELEMETRY_BASELINE_AND_EXTEND_SOAK"
    elif any(item["hardware_ingress_near_restart"] for item in restart_contexts):
        status = "PASS"
        decision = "DESIGN_TRAFFIC_DEMAND_GATED_RECOVERY_EXPERIMENT"
    else:
        status = "PASS"
        decision = "KEEP_F293_AND_OBSERVE_NO_DEMAND_RESTART"

    return {
        "schema": "openmitrastar.f293-emac-hw-rx-demand-physical-evaluation/v2",
        "status": status,
        "decision": decision,
        "checks": checks,
        "gates": {
            "transport": "PASS" if transport_passed else "FAIL",
            "telemetry": "PASS" if telemetry_passed else "FAIL",
            "performance": "PASS" if performance_passed else "FAIL",
        },
        "baseline": {
            "median_download_mbps": baseline_candidate["median_download_mbps"],
            "median_upload_mbps": baseline_candidate["median_upload_mbps"],
        },
        "candidate": {
            "download_mbps": [round(value, 3) for value in down],
            "upload_mbps": [round(value, 3) for value in up],
            "median_download_mbps": round(median_down, 3),
            "median_upload_mbps": round(median_up, 3),
            "restart_context": contexts,
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
    if result["status"] == "PASS":
        return 0
    if result["status"] == "PARTIAL":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
