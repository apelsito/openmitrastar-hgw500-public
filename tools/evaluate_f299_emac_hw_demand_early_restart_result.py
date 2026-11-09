#!/usr/bin/env python3
"""Evaluate the F299 demand-gated early RX restart against F290."""
from __future__ import annotations

import argparse
import json
import statistics
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_BASELINE = ROOT / "outputs/f3-certification/f290-emac-restart-context-20260903/f290-evaluation.json"
TRANSFER_BYTES = 32 * 1024 * 1024
FALLBACK_POKES = 16
MIN_DEMAND_STREAK = 4


def number(mapping: dict[str, object], key: str) -> int:
    return int(mapping.get(key) or 0)


def rate_mbps(run: dict[str, object], direction: str) -> float:
    transfer = run.get(f"controller_{direction}")
    if not isinstance(transfer, dict):
        return 0.0
    return float(transfer.get("speed_Bps") or 0) * 8 / 1_000_000


def transfer_passed(run: dict[str, object], direction: str) -> bool:
    transfer = run.get(f"controller_{direction}")
    return (
        isinstance(transfer, dict)
        and transfer.get("pass") is True
        and number(transfer, "bytes") == TRANSFER_BYTES
    )


def early_restart_context(run: dict[str, object]) -> dict[str, object]:
    delta = run.get("emac_stats_delta") or {}
    last = run.get("emac_stats_last") or {}
    early_count = number(delta, "rx_restart_reason_hw_demand")
    trigger_pokes = number(last, "rx_restart_last_trigger_pokes")
    progress_streak = number(last, "rx_restart_last_mac_rx_progress_streak")
    mac_delta = number(last, "rx_restart_last_mac_rx_delta")
    progress_observations = number(last, "mac_rx_progress_observations")
    mac_valid = number(last, "mac_rx_frames_valid") == 1
    mac_ingress = mac_valid and progress_streak >= MIN_DEMAND_STREAK and mac_delta > 0
    proof = (
        early_count > 0
        and number(delta, "rx_restart_total") >= early_count
        and 0 < trigger_pokes < FALLBACK_POKES
        and mac_ingress
    )
    return {
        "early_restart_count": early_count,
        "restart_total": number(delta, "rx_restart_total"),
        "reason_hw_demand": early_count > 0,
        "trigger_pokes": trigger_pokes,
        "trigger_before_fallback": 0 < trigger_pokes < FALLBACK_POKES,
        "mac_rx_frames_valid": mac_valid,
        "mac_rx_delta": mac_delta,
        "mac_rx_progress_observations": progress_observations,
        "mac_rx_progress_streak": progress_streak,
        "mac_ingress": mac_ingress,
        "proof": proof,
    }


def evaluate(baseline: dict[str, object], runs: list[dict[str, object]]) -> dict[str, object]:
    if len(runs) != 3:
        raise ValueError("exactly three F299 summaries are required")

    baseline_candidate = baseline["candidate"]
    downloads = [rate_mbps(run, "download") for run in runs]
    uploads = [rate_mbps(run, "upload") for run in runs]
    median_download = statistics.median(downloads)
    median_upload = statistics.median(uploads)
    contexts = [early_restart_context(run) for run in runs]

    def telemetry_contract_present(run: dict[str, object]) -> bool:
        delta = run.get("emac_stats_delta")
        last = run.get("emac_stats_last")
        return (
            isinstance(delta, dict)
            and isinstance(last, dict)
            and all(
                key in delta
                for key in (
                    "rx_alloc_failures",
                    "mac_rx_read_failures",
                    "rx_restart_total",
                    "rx_restart_reason_hw_demand",
                )
            )
            and all(
                key in last
                for key in (
                    "rx_restart_last_trigger_pokes",
                    "rx_restart_last_mac_rx_progress_streak",
                    "rx_restart_last_mac_rx_delta",
                    "mac_rx_frames_valid",
                )
            )
        )

    transport_checks = {
        "three_32mib_downloads_passed": all(transfer_passed(run, "download") for run in runs),
        "three_32mib_uploads_passed": all(transfer_passed(run, "upload") for run in runs),
        "three_router_health_gates_passed": all(
            (run.get("router_health_gate") or {}).get("pass") is True for run in runs
        ),
    }
    safety_checks = {
        "telemetry_contract_present": all(telemetry_contract_present(run) for run in runs),
        "zero_rx_alloc_failures": all(
            "rx_alloc_failures" in (run.get("emac_stats_delta") or {})
            and number(run.get("emac_stats_delta") or {}, "rx_alloc_failures") == 0
            for run in runs
        ),
        "zero_fatal_markers": all(
            "fatal_count_before" in run
            and "fatal_count_after" in run
            and number(run, "fatal_count_before") == 0
            and number(run, "fatal_count_after") == 0
            for run in runs
        ),
        "hardware_counter_reads_clean": all(
            "mac_rx_read_failures" in (run.get("emac_stats_delta") or {})
            and number(run.get("emac_stats_delta") or {}, "mac_rx_read_failures") == 0
            for run in runs
        ),
    }
    performance_checks = {
        "median_download_at_least_95pct_f290": (
            median_download >= float(baseline_candidate["median_download_mbps"]) * 0.95
        ),
        "median_upload_at_least_95pct_f290": (
            median_upload >= float(baseline_candidate["median_upload_mbps"]) * 0.95
        ),
    }
    early_observed = any(context["reason_hw_demand"] for context in contexts)
    early_proof_valid = all(
        not context["reason_hw_demand"] or context["proof"] for context in contexts
    )
    experiment_checks = {
        "early_restart_observed": early_observed,
        "every_early_restart_has_required_proof": early_proof_valid,
    }

    transport_passed = all(transport_checks.values())
    safety_passed = all(safety_checks.values())
    performance_passed = all(performance_checks.values())

    if not transport_passed or not safety_passed or not performance_passed or not early_proof_valid:
        status = "FAIL"
        decision = "ROLLBACK_F299_TO_F292"
    elif not early_observed:
        status = "PARTIAL"
        decision = "ROLLBACK_F299_NO_EARLY_BRANCH_OBSERVED"
    else:
        status = "PASS"
        decision = "KEEP_F299_AND_RUN_5G_SANITY"

    return {
        "schema": "openmitrastar.f299-emac-hw-demand-early-restart-physical-evaluation/v1",
        "status": status,
        "decision": decision,
        "gates": {
            "transport": "PASS" if transport_passed else "FAIL",
            "safety": "PASS" if safety_passed else "FAIL",
            "performance": "PASS" if performance_passed else "FAIL",
            "early_restart": (
                "PASS" if early_observed and early_proof_valid else
                "NOT_OBSERVED" if not early_observed else "FAIL"
            ),
        },
        "checks": {
            **transport_checks,
            **safety_checks,
            **performance_checks,
            **experiment_checks,
        },
        "baseline": {
            "median_download_mbps": baseline_candidate["median_download_mbps"],
            "median_upload_mbps": baseline_candidate["median_upload_mbps"],
            "minimum_download_mbps": round(float(baseline_candidate["median_download_mbps"]) * 0.95, 3),
            "minimum_upload_mbps": round(float(baseline_candidate["median_upload_mbps"]) * 0.95, 3),
        },
        "candidate": {
            "download_mbps": [round(value, 3) for value in downloads],
            "upload_mbps": [round(value, 3) for value in uploads],
            "median_download_mbps": round(median_download, 3),
            "median_upload_mbps": round(median_upload, 3),
            "early_restart_context": contexts,
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
