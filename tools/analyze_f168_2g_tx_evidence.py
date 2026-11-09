#!/usr/bin/env python3
"""Classify F167/F168 2.4 GHz throughput and optional RTL TX traces."""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SUMMARY = ROOT / "outputs/f3-certification/realtek-2g-f167-32m-20260901/summary.json"


def mbps(speed_bps: float) -> float:
    return speed_bps * 8.0 / 1_000_000.0


def parse_trace(text: str) -> dict[str, object]:
    tx_desc = [line for line in text.splitlines() if "OMRTLRA stage=tx-desc" in line]
    tx_close = [line for line in text.splitlines() if "OMRTLTXCLOSE" in line]
    be = [line for line in text.splitlines() if "OMRTLBE" in line]
    no_progress = [
        line for line in text.splitlines()
        if "OMRTL stage=tx-complete" in line and "progressed=0" in line
    ]
    ampdu = sum("ampdu=1" in line for line in tx_desc)
    rates = sorted({int(value) for value in re.findall(r"hw_rate=(\d+)", "\n".join(tx_desc))})
    queued = [int(value) for value in re.findall(r"queued=(\d+)", "\n".join(tx_close + be + no_progress))]
    return {
        "tx_desc_samples": len(tx_desc),
        "tx_desc_ampdu_samples": ampdu,
        "tx_desc_non_ampdu_samples": len(tx_desc) - ampdu,
        "tx_desc_hw_rates": rates,
        "tx_close_not_closed_samples": len(tx_close),
        "be_summary_samples": len(be),
        "tx_complete_no_progress_samples": len(no_progress),
        "max_observed_queue": max(queued) if queued else None,
    }


def analyze(summary: dict[str, object], trace_text: str = "") -> dict[str, object]:
    download = summary["controller_download"]
    upload = summary["controller_upload"]
    netdev = summary["netdev_delta"]
    emac = summary["emac_stats_delta"]
    station = summary["last_station"]
    down_mbps = mbps(float(download["speed_Bps"]))
    up_mbps = mbps(float(upload["speed_Bps"]))
    phy_mbps = float(summary["last_station_rate_class"]["tx_phy_mbps"])
    trace = parse_trace(trace_text)

    wlan = netdev["wlan0"]
    eth = netdev["eth0"]
    down_path_progress = int(eth["rx_bytes"]) > 32 * 1024 * 1024 and int(wlan["tx_bytes"]) > 32 * 1024 * 1024
    up_path_progress = int(wlan["rx_bytes"]) > 32 * 1024 * 1024 and int(eth["tx_bytes"]) > 32 * 1024 * 1024
    no_wlan_errors = all(int(wlan[key]) == 0 for key in ("rx_errs", "tx_errs", "rx_drop", "tx_drop"))
    emac_restarts = int(emac["rx_restart_total"])
    return {
        "schema": "openmitrastar.f168-2g-tx-analysis/v1",
        "source_schema": summary.get("schema"),
        "throughput": {
            "download_mbps": round(down_mbps, 3),
            "upload_mbps": round(up_mbps, 3),
            "upload_over_download_ratio": round(up_mbps / down_mbps, 3),
            "reported_tx_phy_mbps": phy_mbps,
            "download_payload_over_reported_phy": round(down_mbps / phy_mbps, 4),
        },
        "direction_mapping": {
            "controller_download": "eth0 RX -> br0 -> wlan0 TX -> client",
            "controller_upload": "client -> wlan0 RX -> br0 -> eth0 TX",
            "rtl_rx_is_primary_download_path": False,
        },
        "observations": {
            "down_path_byte_progress": down_path_progress,
            "up_path_byte_progress": up_path_progress,
            "wlan0_new_errors_or_drops": not no_wlan_errors,
            "irq28_delta": int(summary["irq28_delta"]),
            "emac_rx_restarts": emac_restarts,
            "emac_rx_restart_no_desc": int(emac["rx_restart_reason_no_desc"]),
            "emac_napi_budget_exhaustions": int(emac["napi_budget_exhaustions"]),
            "station_tx_bitrate": station["tx_bitrate"],
            "station_tx_retries": station["tx_retries"],
            "station_tx_failed": station["tx_failed"],
        },
        "driver_audit": {
            "rtl_rx_bottleneck_supported": False,
            "realtek_tx_bottleneck_proven": False,
            "realtek_tx_instrumentation_required": True,
            "fabricated_ack_policy_means_zero_retries_is_not_rf_proof": True,
            "reported_mcs15_conflicts_with_f167_forced_mcs7_loader_and_requires_descriptor_trace": True,
            "emac_interference_observed": emac_restarts > 0,
        },
        "trace": trace,
        "classification": "DOWNLINK_LOW_TX_PATH_UNRESOLVED_EMAC_RESTARTS_OBSERVED",
        "next_discriminator": (
            "Repeat the same 32 MiB download with F168 diagnostics and compare "
            "AMPDU descriptor samples, HW/SW RP-WP closure, BE queue depth and "
            "EMAC restart timestamps."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--summary", type=Path, default=DEFAULT_SUMMARY)
    parser.add_argument("--trace-log", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    summary = json.loads(args.summary.read_text(encoding="utf-8"))
    trace_text = args.trace_log.read_text(encoding="utf-8", errors="replace") if args.trace_log else ""
    result = analyze(summary, trace_text)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="ascii")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
