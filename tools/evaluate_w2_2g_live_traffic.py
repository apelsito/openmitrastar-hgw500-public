#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def classify(data: dict) -> tuple[str, list[str]]:
    failures: list[str] = []

    if data.get("schema") != "openmitrastar.2g-live-traffic/v1":
        failures.append("invalid_schema")
    if data.get("producer") != "tools/monitor_2g_live_traffic.py":
        failures.append("invalid_producer")
    if int(data.get("samples_observed", 0)) < 3:
        failures.append("insufficient_samples")
    if data.get("phase_capture_complete") is not True:
        failures.append("phase_capture_incomplete")
    if int(data.get("observed_span_seconds", 0)) < int(data.get("minimum_observed_span_seconds", 1)):
        failures.append("duration_not_met")
    if data.get("mutations") is not False or data.get("flash") is not False:
        failures.append("unsafe_capture_contract")
    raw_log = Path(str(data.get("raw_log", "")))
    expected_raw_sha = str(data.get("raw_log_sha256", ""))
    if not expected_raw_sha:
        failures.append("raw_log_digest_missing")
    elif not raw_log.is_file():
        failures.append("raw_log_missing")
    elif hashlib.sha256(raw_log.read_bytes()).hexdigest() != expected_raw_sha:
        failures.append("raw_log_digest_mismatch")

    if data.get("complete") is not True:
        failures.append("capture_incomplete")
    if data.get("connection_error"):
        failures.append("connection_error")
    if data.get("ap_enabled_all_samples") is not True:
        failures.append("ap_not_enabled_all_samples")
    if data.get("carrier_all_samples") is not True:
        failures.append("carrier_not_present_all_samples")
    if data.get("ssh_alive_all_samples") is not True:
        failures.append("ssh_not_alive_all_samples")
    if int(data.get("fatal_markers_during_run", 1)) != 0:
        failures.append("fatal_markers")
    if int(data.get("rx_errors_delta", 1)) != 0:
        failures.append("wifi_rx_errors")
    if int(data.get("tx_errors_delta", 1)) != 0:
        failures.append("wifi_tx_errors")
    if int(data.get("irq20_delta", 0)) <= 0:
        failures.append("irq20_no_progress")
    if int(data.get("irq28_delta", 0)) <= 0:
        failures.append("irq28_no_progress")

    associated = data.get("association_observed") is True or int(data.get("max_associations", 0)) > 0
    authorized = data.get("authorization_observed") is True or int(data.get("max_authorized", 0)) > 0
    be_queue = int(data.get("be_queue_run_max", 0))
    be_events = int(data.get("be_events_observed", 0))
    wifi_rx_bytes = int(data.get("wifi_rx_bytes_during_increase", data.get("wifi_rx_bytes_delta", 0)))
    wifi_tx_bytes = int(data.get("wifi_tx_bytes_during_increase", data.get("wifi_tx_bytes_delta", 0)))
    sta_failed = int(data.get("station_tx_failed_increase", max(int(data.get("station_tx_failed_delta", 0)), 0)))
    be_close_events = int(data.get("be_close_events_observed", 0))
    be_doorbell_events = int(data.get("be_doorbell_events_observed", 0))
    be_hw_rp_progress = data.get("be_hw_rp_progress") is True
    be_hw_wp_progress = data.get("be_hw_wp_progress") is True
    be_telemetry_present = (
        be_events > 0 or be_close_events > 0 or be_doorbell_events > 0
        or be_hw_rp_progress or be_hw_wp_progress
    )

    if not associated:
        return "NO_CLIENT", sorted(set(failures + ["association_missing"]))
    if not authorized:
        return "NO_AUTH", sorted(set(failures + ["authorization_missing"]))
    if sta_failed != 0:
        failures.append("station_tx_failed")
    if be_queue >= 384:
        failures.append("be_queue_high")
    if wifi_tx_bytes <= 0:
        failures.append("wifi_downlink_bytes_missing")
    elif wifi_tx_bytes < 65_536:
        failures.append("wifi_downlink_traffic_insufficient")
    if wifi_rx_bytes <= 0:
        failures.append("wifi_uplink_bytes_missing")
    elif wifi_rx_bytes < 65_536:
        failures.append("wifi_uplink_traffic_insufficient")

    if (
        ("wifi_downlink_bytes_missing" in failures or "wifi_downlink_traffic_insufficient" in failures)
        and ("be_queue_high" in failures or (be_hw_wp_progress and not be_hw_rp_progress))
    ):
        return "BE_STALL", sorted(set(failures))
    if failures:
        return "FAIL", sorted(set(failures))
    return "TELEMETRY_PASS_TRAFFIC_OBSERVED", []


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("summary", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    data = json.loads(args.summary.read_text(encoding="utf-8"))
    status, failures = classify(data)
    be_telemetry_present = (
        int(data.get("be_events_observed", 0)) > 0
        or int(data.get("be_close_events_observed", 0)) > 0
        or int(data.get("be_doorbell_events_observed", 0)) > 0
        or data.get("be_hw_rp_progress") is True
        or data.get("be_hw_wp_progress") is True
    )
    result = {
        "schema": "openmitrastar.w2-2g-live-traffic-evaluation/v1",
        "status": status,
        "pass": status == "TELEMETRY_PASS_TRAFFIC_OBSERVED",
        "failures": failures,
        "input": str(args.summary),
        "thresholds": {
            "be_queue_run_max_exclusive": 384,
            "fatal_markers_during_run": 0,
            "rx_errors_delta": 0,
            "tx_errors_delta": 0,
            "station_tx_failed_delta": 0,
            "irq20_delta_min": 1,
            "irq28_delta_min": 1,
            "requires_association": True,
            "requires_authorization": True,
            "requires_bidirectional_wifi_bytes": True,
            "bidirectional_wifi_bytes_during_min": 65_536,
            "speedtest_required_for_product_pass": True,
            "raw_log_sha256_required": True,
            "producer": "tools/monitor_2g_live_traffic.py",
        },
        "observed": {
            "complete": data.get("complete"),
            "connection_error": data.get("connection_error"),
            "association_observed": data.get("association_observed"),
            "authorization_observed": data.get("authorization_observed"),
            "max_associations": data.get("max_associations"),
            "max_authorized": data.get("max_authorized"),
            "be_queue_run_max": data.get("be_queue_run_max"),
            "be_events_observed": data.get("be_events_observed"),
            "be_close_events_observed": data.get("be_close_events_observed"),
            "be_doorbell_events_observed": data.get("be_doorbell_events_observed"),
            "be_telemetry_present": be_telemetry_present,
            "be_hw_rp_progress": data.get("be_hw_rp_progress"),
            "be_hw_wp_progress": data.get("be_hw_wp_progress"),
            "be_last_indices": data.get("be_last_indices"),
            "wifi_rx_bytes_delta": data.get("wifi_rx_bytes_delta"),
            "wifi_tx_bytes_delta": data.get("wifi_tx_bytes_delta"),
            "wifi_rx_bytes_during_increase": data.get("wifi_rx_bytes_during_increase"),
            "wifi_tx_bytes_during_increase": data.get("wifi_tx_bytes_during_increase"),
            "wifi_rx_mbps_peak_during": data.get("wifi_rx_mbps_peak_during"),
            "wifi_tx_mbps_peak_during": data.get("wifi_tx_mbps_peak_during"),
            "irq20_delta": data.get("irq20_delta"),
            "irq28_delta": data.get("irq28_delta"),
            "fatal_markers_during_run": data.get("fatal_markers_during_run"),
            "ssh_alive_all_samples": data.get("ssh_alive_all_samples"),
            "station_tx_failed_increase": data.get("station_tx_failed_increase"),
        },
        "mutations": False,
        "flash": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
