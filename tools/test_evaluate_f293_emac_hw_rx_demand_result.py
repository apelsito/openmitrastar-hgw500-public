from __future__ import annotations

import evaluate_f293_emac_hw_rx_demand_result as evaluator


def run(
    *,
    restart: int,
    progress_age: int = 0,
    missed: int = 0,
    read_failures: int = 0,
    mac_rx_valid: int = 1,
    mac_rx_samples: int = 20,
    download_Bps: int = 3_700_000,
) -> dict:
    return {
        "controller_download": {"pass": True, "speed_Bps": download_Bps},
        "controller_upload": {"pass": True, "speed_Bps": 1_850_000},
        "router_health_gate": {"pass": True},
        "emac_stats_delta": {
            "rx_restart_total": restart,
            "rx_alloc_failures": 0,
        },
        "emac_stats_last": {
            "mac_rx_frames_valid": mac_rx_valid,
            "mac_rx_samples": mac_rx_samples,
            "mac_rx_read_failures": read_failures,
            "mac_rx_progress_observations": 5,
            "rx_restart_last_mac_rx_frames": 4000 if restart else 0,
            "rx_restart_last_mac_rx_delta": 2 if restart else 0,
            "rx_restart_last_mac_rx_progress_age_ms": progress_age,
            "rx_restart_last_dma_missed_frames": missed,
            "rx_restart_last_dma_missed_frames_total": missed,
        },
    }


def baseline() -> dict:
    return {"candidate": {"median_download_mbps": 29.258, "median_upload_mbps": 14.410}}


def test_selects_demand_gate_when_restart_has_hardware_ingress() -> None:
    result = evaluator.evaluate(
        baseline(),
        [run(restart=1, progress_age=6150), run(restart=0), run(restart=0)],
    )
    assert result["status"] == "PASS"
    assert result["decision"] == "DESIGN_TRAFFIC_DEMAND_GATED_RECOVERY_EXPERIMENT"


def test_accepts_exact_sample_age_zero_as_hardware_ingress() -> None:
    result = evaluator.evaluate(
        baseline(),
        [run(restart=0, mac_rx_valid=0, mac_rx_samples=0), run(restart=1, progress_age=0), run(restart=0)],
    )
    assert result["status"] == "PASS"
    assert result["candidate"]["restart_context"][1]["hardware_ingress_near_restart"] is True
    assert result["checks"]["restart_counter_available"] is True


def test_no_stall_run_does_not_require_hardware_counter_samples() -> None:
    result = evaluator.evaluate(
        baseline(),
        [
            run(restart=0, mac_rx_valid=0, mac_rx_samples=0),
            run(restart=1, progress_age=0),
            run(restart=0, mac_rx_valid=0, mac_rx_samples=0),
        ],
    )
    assert result["status"] == "PASS"
    assert result["gates"]["telemetry"] == "PASS"


def test_performance_regression_is_partial_but_keeps_diagnostic_result() -> None:
    result = evaluator.evaluate(
        baseline(),
        [
            run(restart=0, mac_rx_valid=0, mac_rx_samples=0, download_Bps=3_300_000),
            run(restart=1, progress_age=0, download_Bps=1_750_000),
            run(restart=0, download_Bps=3_266_625),
        ],
    )
    assert result["status"] == "PARTIAL"
    assert result["gates"] == {"transport": "PASS", "telemetry": "PASS", "performance": "FAIL"}
    assert result["decision"] == "BUILD_F299_DEMAND_ACCELERATION_KEEP_F290_FALLBACK"


def test_keeps_telemetry_when_no_restart_is_observed() -> None:
    result = evaluator.evaluate(baseline(), [run(restart=0), run(restart=0), run(restart=0)])
    assert result["status"] == "PASS"
    assert result["decision"] == "KEEP_F293_TELEMETRY_BASELINE_AND_EXTEND_SOAK"


def test_rejects_counter_read_failures() -> None:
    result = evaluator.evaluate(
        baseline(),
        [run(restart=0, read_failures=1), run(restart=0), run(restart=0)],
    )
    assert result["status"] == "FAIL"
    assert result["checks"]["hardware_counter_reads_clean"] is False
