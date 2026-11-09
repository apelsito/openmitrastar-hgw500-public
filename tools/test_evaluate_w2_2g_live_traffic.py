#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "evaluate_w2_2g_live_traffic.py"


class EvaluateW2LiveTrafficTests(unittest.TestCase):
    def run_gate(self, summary: dict) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "monitor.log"
            raw.write_text("OM2G test fixture\n", encoding="utf-8")
            summary.setdefault("schema", "openmitrastar.2g-live-traffic/v1")
            summary.setdefault("producer", "tools/monitor_2g_live_traffic.py")
            summary.setdefault("samples_observed", 3)
            summary.setdefault("phase_capture_complete", True)
            summary.setdefault("observed_span_seconds", 10)
            summary.setdefault("minimum_observed_span_seconds", 9)
            summary.setdefault("mutations", False)
            summary.setdefault("flash", False)
            summary.setdefault("raw_log", str(raw))
            summary.setdefault("raw_log_sha256", hashlib.sha256(raw.read_bytes()).hexdigest())
            path = Path(tmp) / "summary.json"
            path.write_text(json.dumps(summary), encoding="utf-8")
            return subprocess.run(
                [sys.executable, str(TOOL), str(path)],
                text=True,
                capture_output=True,
                check=False,
            )

    @staticmethod
    def base() -> dict:
        return {
            "complete": True,
            "connection_error": None,
            "ap_enabled_all_samples": True,
            "carrier_all_samples": True,
            "ssh_alive_all_samples": True,
            "fatal_markers_during_run": 0,
            "rx_errors_delta": 0,
            "tx_errors_delta": 0,
            "irq20_delta": 10,
            "irq28_delta": 20,
            "association_observed": True,
            "authorization_observed": True,
            "max_associations": 1,
            "max_authorized": 1,
            "station_tx_failed_delta": 0,
            "station_tx_failed_increase": 0,
            "be_queue_run_max": 12,
            "be_events_observed": 3,
            "be_close_events_observed": 1,
            "be_doorbell_events_observed": 3,
            "be_hw_rp_progress": True,
            "be_hw_wp_progress": True,
            "wifi_rx_bytes_delta": 100_000,
            "wifi_tx_bytes_delta": 100_000,
            "wifi_rx_bytes_during_increase": 100_000,
            "wifi_tx_bytes_during_increase": 100_000,
        }

    def test_forged_summary_without_raw_log_digest_is_rejected(self) -> None:
        summary = self.base()
        summary["raw_log_sha256"] = ""
        proc = self.run_gate(summary)
        self.assertNotEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertIn("raw_log_digest_missing", result["failures"])

    def test_wrong_schema_is_rejected(self) -> None:
        summary = self.base()
        summary["schema"] = "openmitrastar.2g-live-traffic/v0"
        proc = self.run_gate(summary)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("invalid_schema", json.loads(proc.stdout)["failures"])

    def test_no_client_is_not_a_pass_even_when_capture_completed(self) -> None:
        summary = self.base()
        summary.update(
            association_observed=False,
            authorization_observed=False,
            max_associations=0,
            max_authorized=0,
            be_events_observed=0,
            wifi_rx_bytes_delta=0,
            wifi_tx_bytes_delta=194_007,
        )
        proc = self.run_gate(summary)
        self.assertNotEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "NO_CLIENT")
        self.assertIn("association_missing", result["failures"])

    def test_no_authorization_is_separate_from_no_client(self) -> None:
        summary = self.base()
        summary.update(authorization_observed=False, max_authorized=0)
        proc = self.run_gate(summary)
        self.assertNotEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "NO_AUTH")
        self.assertIn("authorization_missing", result["failures"])

    def test_be_stall_is_called_out_when_queue_fills_without_downlink_bytes(self) -> None:
        summary = self.base()
        summary.update(
            be_queue_run_max=511,
            wifi_tx_bytes_delta=0,
            wifi_tx_bytes_during_increase=0,
        )
        proc = self.run_gate(summary)
        self.assertNotEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "BE_STALL")
        self.assertIn("be_queue_high", result["failures"])
        self.assertIn("wifi_downlink_bytes_missing", result["failures"])

    def test_bidirectional_telemetry_pass_does_not_claim_speedtest_product_pass(self) -> None:
        proc = self.run_gate(self.base())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "TELEMETRY_PASS_TRAFFIC_OBSERVED")
        self.assertTrue(result["pass"])
        self.assertTrue(result["thresholds"]["speedtest_required_for_product_pass"])

    def test_healthy_traffic_without_bounded_be_logs_is_not_a_false_negative(self) -> None:
        summary = self.base()
        summary.update(
            be_events_observed=0,
            be_close_events_observed=0,
            be_doorbell_events_observed=0,
            be_hw_rp_progress=False,
            be_hw_wp_progress=False,
        )
        proc = self.run_gate(summary)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "TELEMETRY_PASS_TRAFFIC_OBSERVED")
        self.assertFalse(result["observed"]["be_telemetry_present"])

    def test_published_be_without_rp_progress_and_no_downlink_is_stall(self) -> None:
        summary = self.base()
        summary.update(
            be_queue_run_max=20,
            be_hw_wp_progress=True,
            be_hw_rp_progress=False,
            wifi_tx_bytes_delta=0,
            wifi_tx_bytes_during_increase=0,
        )
        proc = self.run_gate(summary)
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual(json.loads(proc.stdout)["status"], "BE_STALL")

    def test_published_be_without_rp_progress_and_tiny_downlink_is_stall(self) -> None:
        summary = self.base()
        summary.update(
            be_queue_run_max=20,
            be_doorbell_events_observed=22,
            be_hw_wp_progress=True,
            be_hw_rp_progress=False,
            wifi_tx_bytes_delta=52_955,
            wifi_tx_bytes_during_increase=40_854,
        )
        proc = self.run_gate(summary)
        self.assertNotEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "BE_STALL")
        self.assertTrue(result["observed"]["be_telemetry_present"])

    def test_station_counter_reset_is_not_a_failure_when_increase_is_zero(self) -> None:
        summary = self.base()
        summary.update(station_tx_failed_delta=-7, station_tx_failed_increase=0)
        proc = self.run_gate(summary)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_association_handshake_bytes_are_not_mislabeled_as_data_traffic(self) -> None:
        summary = self.base()
        summary.update(
            wifi_rx_bytes_during_increase=4_096,
            wifi_tx_bytes_during_increase=8_192,
        )
        proc = self.run_gate(summary)
        self.assertNotEqual(proc.returncode, 0)
        result = json.loads(proc.stdout)
        self.assertEqual(result["status"], "FAIL")
        self.assertIn("wifi_uplink_traffic_insufficient", result["failures"])
        self.assertIn("wifi_downlink_traffic_insufficient", result["failures"])


if __name__ == "__main__":
    unittest.main()
