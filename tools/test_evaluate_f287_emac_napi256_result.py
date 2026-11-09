from __future__ import annotations

import evaluate_f287_emac_napi256_result as evaluator


def run(down: float, up: float, irq: int, sampled: int, restarts: int) -> dict:
    return {
        "controller_download": {"pass": True, "speed_Bps": down * 1_000_000 / 8},
        "controller_upload": {"pass": True, "speed_Bps": up * 1_000_000 / 8},
        "router_health_gate": {"pass": True},
        "emac_stats_delta": {
            "irq_no_rx_desc": irq,
            "dma_no_rx_desc_samples": sampled,
            "napi_budget_exhaustions": 2,
            "rx_restart_total": restarts,
            "rx_restart_reason_no_desc": restarts,
            "rx_alloc_failures": 0,
        },
        "netdev_delta": {"wlan0": {"rx_errs": 0, "tx_errs": 0, "rx_drop": 0, "tx_drop": 0}},
    }


def baseline() -> dict:
    return {
        "candidate": {
            "median_download_mbps": 14.681,
            "median_upload_mbps": 14.265,
            "irq_no_rx_desc": [26, 20, 43],
            "dma_no_rx_desc_samples": [300, 308, 307],
            "rx_restart_total": [1, 1, 1],
        }
    }


def test_accepts_lower_starvation_without_throughput_regression() -> None:
    result = evaluator.evaluate(baseline(), [run(15, 14, 4, 40, 0), run(15, 15, 5, 50, 0), run(14.5, 14.5, 6, 45, 0)])
    assert result["status"] == "PASS"
    assert result["decision"] == "KEEP_F287"


def test_rejects_persistent_restart() -> None:
    result = evaluator.evaluate(baseline(), [run(15, 15, 4, 40, 0), run(15, 15, 5, 50, 1), run(15, 15, 6, 45, 0)])
    assert result["status"] == "PARTIAL"
    assert result["decision"] == "KEEP_F287_DIAGNOSTIC_BASELINE"
    assert result["checks"]["zero_no_desc_restarts"] is False


def test_rejects_throughput_regression() -> None:
    result = evaluator.evaluate(baseline(), [run(5, 5, 4, 40, 0), run(5, 5, 5, 50, 0), run(5, 5, 6, 45, 0)])
    assert result["status"] == "FAIL"
    assert result["decision"] == "ROLL_BACK_TO_F285"
