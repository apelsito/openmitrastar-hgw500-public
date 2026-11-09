#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_openmitrastar_ram_equivalence.py"
SPEC = importlib.util.spec_from_file_location("ram_equivalence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def good_sample(index: int) -> dict[str, object]:
    base = 100 + index * 10
    return {
        "local_ping": True,
        "ssh_primary": True,
        "ssh_fresh": True,
        "hostapd_enabled": 1,
        "bridge_eth0": 1,
        "bridge_wlan0": 1,
        "station_count": 1,
        "wifi_client_ping": 1,
        "boot_ready": 1,
        "minihttpd_alive": 1,
        "cgi_executed": True,
        "uptime_s": base,
        "br0_rx_packets": base,
        "br0_tx_packets": base,
        "wlan0_rx_packets": base,
        "wlan0_tx_packets": base,
        "irq20": base,
        "irq28": base,
        "br0_rx_errors": 0,
        "br0_tx_errors": 0,
        "wlan0_rx_errors": 0,
        "wlan0_tx_errors": 0,
    }


class RamEquivalenceTests(unittest.TestCase):
    def test_dry_run_binds_exact_candidate_and_has_no_hardware_action(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OM_RAM_EQUIVALENCE_DRY_RUN_PASS=1", proc.stdout)
        self.assertIn(MODULE.EXPECTED_SHA256, proc.stdout)

    def test_good_soak_passes(self) -> None:
        summary, failures = MODULE.evaluate_samples(
            [good_sample(0), good_sample(1), good_sample(2)], 600.1, 600
        )
        self.assertTrue(summary["pass"])
        self.assertEqual(failures, [])

    def test_management_freeze_fails(self) -> None:
        samples = [good_sample(0), good_sample(1), good_sample(2)]
        samples[1]["ssh_fresh"] = False
        _, failures = MODULE.evaluate_samples(samples, 600.1, 600)
        self.assertIn("fresh_ssh_failure", failures)

    def test_bridge_freeze_fails(self) -> None:
        samples = [good_sample(0), good_sample(1), good_sample(2)]
        samples[1]["bridge_wlan0"] = 0
        samples[2]["br0_rx_packets"] = samples[1]["br0_rx_packets"]
        _, failures = MODULE.evaluate_samples(samples, 600.1, 600)
        self.assertIn("bridge_membership_lost", failures)
        self.assertIn("br0_rx_packets_frozen", failures)

    def test_radio_freeze_or_missing_client_fails(self) -> None:
        samples = [good_sample(0), good_sample(1), good_sample(2)]
        samples[1]["station_count"] = 0
        samples[2]["wlan0_tx_packets"] = samples[1]["wlan0_tx_packets"]
        _, failures = MODULE.evaluate_samples(samples, 600.1, 600)
        self.assertIn("wifi_client_not_associated", failures)
        self.assertIn("wlan0_tx_packets_frozen", failures)

    def test_cgi_source_serving_cannot_pass(self) -> None:
        samples = [good_sample(0), good_sample(1)]
        samples[1]["cgi_executed"] = False
        _, failures = MODULE.evaluate_samples(samples, 600.1, 600)
        self.assertIn("cgi_not_executed", failures)


if __name__ == "__main__":
    unittest.main()
