from __future__ import annotations

import evaluate_f299_emac_hw_demand_early_restart_result as evaluator


def baseline() -> dict:
    return {"candidate": {"median_download_mbps": 29.258, "median_upload_mbps": 14.410}}


def run(
    *,
    early: int = 0,
    trigger_pokes: int = 0,
    streak: int = 0,
    mac_delta: int = 0,
    download_Bps: int = 3_700_000,
    upload_Bps: int = 1_850_000,
    transfer_bytes: int = 32 * 1024 * 1024,
    health: bool = True,
    alloc_failures: int = 0,
    fatal_before: int = 0,
    fatal_after: int = 0,
    read_failures: int = 0,
) -> dict:
    return {
        "controller_download": {
            "pass": True,
            "bytes": transfer_bytes,
            "speed_Bps": download_Bps,
        },
        "controller_upload": {
            "pass": True,
            "bytes": transfer_bytes,
            "speed_Bps": upload_Bps,
        },
        "router_health_gate": {"pass": health},
        "fatal_count_before": fatal_before,
        "fatal_count_after": fatal_after,
        "emac_stats_delta": {
            "rx_alloc_failures": alloc_failures,
            "mac_rx_read_failures": read_failures,
            "rx_restart_total": early,
            "rx_restart_reason_hw_demand": early,
        },
        "emac_stats_last": {
            "rx_restart_last_trigger_pokes": trigger_pokes,
            "rx_restart_last_mac_rx_progress_streak": streak,
            "rx_restart_last_mac_rx_delta": mac_delta,
            "mac_rx_progress_observations": streak,
            "mac_rx_frames_valid": 1 if early else 0,
        },
    }


def test_pass_requires_proven_early_restart() -> None:
    result = evaluator.evaluate(
        baseline(),
        [run(), run(early=1, trigger_pokes=4, streak=4, mac_delta=1), run()],
    )
    assert result["status"] == "PASS"
    assert result["decision"] == "KEEP_F299_AND_RUN_5G_SANITY"
    assert result["checks"]["every_early_restart_has_required_proof"] is True


def test_no_early_branch_is_partial() -> None:
    result = evaluator.evaluate(baseline(), [run(), run(), run()])
    assert result["status"] == "PARTIAL"
    assert result["gates"]["early_restart"] == "NOT_OBSERVED"


def test_early_reason_without_sub16_trigger_is_fail() -> None:
    result = evaluator.evaluate(
        baseline(),
        [run(), run(early=1, trigger_pokes=16, streak=4, mac_delta=1), run()],
    )
    assert result["status"] == "FAIL"
    assert result["checks"]["every_early_restart_has_required_proof"] is False


def test_early_reason_without_mac_ingress_is_fail() -> None:
    result = evaluator.evaluate(
        baseline(),
        [run(), run(early=1, trigger_pokes=4, streak=3, mac_delta=0), run()],
    )
    assert result["status"] == "FAIL"


def test_performance_regression_is_fail() -> None:
    result = evaluator.evaluate(
        baseline(),
        [
            run(download_Bps=3_000_000),
            run(early=1, trigger_pokes=4, streak=4, mac_delta=1, download_Bps=3_000_000),
            run(download_Bps=3_000_000),
        ],
    )
    assert result["status"] == "FAIL"
    assert result["gates"]["performance"] == "FAIL"


def test_transfer_size_health_alloc_fatal_and_counter_reads_are_mandatory() -> None:
    cases = (
        run(transfer_bytes=1024),
        run(health=False),
        run(alloc_failures=1),
        run(fatal_after=1),
        run(read_failures=1),
    )
    for bad in cases:
        result = evaluator.evaluate(
            baseline(),
            [bad, run(early=1, trigger_pokes=4, streak=4, mac_delta=1), run()],
        )
        assert result["status"] == "FAIL"


def test_missing_fatal_or_telemetry_fields_fail_closed() -> None:
    missing_fatal = run()
    del missing_fatal["fatal_count_after"]
    missing_telemetry = run()
    del missing_telemetry["emac_stats_last"]["rx_restart_last_trigger_pokes"]
    for bad in (missing_fatal, missing_telemetry):
        result = evaluator.evaluate(
            baseline(),
            [bad, run(early=1, trigger_pokes=4, streak=4, mac_delta=1), run()],
        )
        assert result["status"] == "FAIL"
