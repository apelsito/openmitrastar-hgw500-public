from __future__ import annotations

import evaluate_f290_emac_restart_context_result as evaluator


def run(restart: int, fault_status: str = "00000020", age: int = 6150) -> dict:
    return {
        "controller_download": {"pass": True, "speed_Bps": 3_500_000},
        "controller_upload": {"pass": True, "speed_Bps": 1_850_000},
        "router_health_gate": {"pass": True},
        "emac_stats_delta": {
            "irq_no_rx_desc": 1 if restart else 0,
            "dma_no_rx_desc_samples": 0,
            "rx_restart_total": restart,
            "rx_restart_reason_no_desc": 0,
            "rx_restart_reason_stagnant": restart,
            "rx_alloc_failures": 0,
        },
        "emac_stats_last": {
            "rx_restart_last_dma_status": "00550002" if restart else "00000000",
            "last_rx_fault_status": fault_status if restart else "00000000",
            "rx_restart_last_fault_age_ms": age if restart else 0,
            "rx_restart_last_idle_ms": 6150 if restart else 0,
            "rx_restart_last_head_status": "80000000" if restart else "00000000",
        },
    }


def baseline() -> dict:
    return {"candidate": {"median_download_mbps": 25.442, "median_upload_mbps": 14.910}}


def test_accepts_causally_attributed_restart() -> None:
    result = evaluator.evaluate(baseline(), [run(1), run(0), run(0)])
    assert result["status"] == "PASS"
    assert result["decision"] == "BUILD_F291_RECENT_FAULT_WINDOW"


def test_rejects_restart_without_recent_fault() -> None:
    result = evaluator.evaluate(baseline(), [run(1, "00000000", 0), run(0), run(0)])
    assert result["status"] == "FAIL"
    assert result["checks"]["all_restarts_follow_recent_fault"] is False
