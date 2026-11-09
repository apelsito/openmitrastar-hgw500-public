#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_f5_foundation_ram_equivalence.py"
SPEC = importlib.util.spec_from_file_location("f5_foundation_ram_equivalence", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def good_sample(index: int) -> dict[str, object]:
    base = 100 + index * 10
    return {
        "local_ping": True,
        "ssh_primary": True,
        "ssh_fresh": True,
        "http80_cgi_executed": True,
        "http8080_closed": True,
        "boot_degraded": 1,
        "minihttpd_alive": 1,
        "wlan0_closed": 1,
        "wifi0_closed": 1,
        "radio2g_refused_no_psk": 1,
        "hostapd_absent": 1,
        "br0_absent": 1,
        "only_radio_degraded": 1,
        "uptime_s": base,
        "eth0_rx_bytes": base * 100,
        "eth0_rx_packets": base,
        "eth0_rx_errors": 0,
        "eth0_tx_bytes": base * 80,
        "eth0_tx_packets": base,
        "eth0_tx_errors": 0,
        "irq20": base,
    }


class F5FoundationRamEquivalenceTests(unittest.TestCase):
    def test_default_dry_run_is_local_only_and_pinned(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OM_F5_FOUNDATION_RAM_EQ_DRY_RUN_PASS=1", proc.stdout)
        self.assertIn(MODULE.EXPECTED_SHA256, proc.stdout)
        self.assertIn('"hardware_actions": false', proc.stdout)
        self.assertIn('"ssh_operations_per_sample": 2', proc.stdout)

    def test_good_management_only_soak_passes(self) -> None:
        summary, failures = MODULE.evaluate_samples(
            [good_sample(0), good_sample(1), good_sample(2)], 180.1, 180
        )
        self.assertTrue(summary["pass"])
        self.assertEqual([], failures)

    def test_duration_below_180_fails(self) -> None:
        _, failures = MODULE.evaluate_samples([good_sample(0), good_sample(1)], 179.9, 180)
        self.assertIn("duration_short", failures)

    def test_either_ssh_operation_failure_fails(self) -> None:
        samples = [good_sample(0), good_sample(1)]
        samples[1]["ssh_fresh"] = False
        _, failures = MODULE.evaluate_samples(samples, 180.1, 180)
        self.assertIn("ssh_fresh_failure", failures)

    def test_cgi_source_or_open_8080_fails(self) -> None:
        samples = [good_sample(0), good_sample(1)]
        samples[1]["http80_cgi_executed"] = False
        samples[1]["http8080_closed"] = False
        _, failures = MODULE.evaluate_samples(samples, 180.1, 180)
        self.assertIn("http80_cgi_not_executed", failures)
        self.assertIn("diagnostic_port_8080_open", failures)

    def test_radio_or_bridge_escape_fails(self) -> None:
        samples = [good_sample(0), good_sample(1)]
        samples[1]["hostapd_absent"] = 0
        samples[1]["br0_absent"] = 0
        _, failures = MODULE.evaluate_samples(samples, 180.1, 180)
        self.assertIn("hostapd_running", failures)
        self.assertIn("br0_present", failures)

    def test_eth0_or_irq_freeze_fails(self) -> None:
        samples = [good_sample(0), good_sample(1)]
        samples[1]["eth0_rx_packets"] = samples[0]["eth0_rx_packets"]
        samples[1]["irq20"] = samples[0]["irq20"]
        _, failures = MODULE.evaluate_samples(samples, 180.1, 180)
        self.assertIn("eth0_rx_packets_no_progress", failures)
        self.assertIn("irq20_no_progress", failures)

    def test_uart_gate_requires_exact_recovery_and_boot_markers(self) -> None:
        good = "\n".join(
            [
                "topaz>",
                "TFTP from server 192.168.1.43",
                f"Filename '{MODULE.RAM_BOOT_NAME}'.",
                f"Bytes transferred = {MODULE.EXPECTED_BYTES} (0x676000)",
                "bootm 0x83000000",
                "Linux version 5.10.260-openmitrastar-radiohw",
                "OMNETWORK_READY profile=oem-videobridge interface=eth0 ipv4=192.168.1.90",
                "OMSSH_READY port=22 auth=ed25519-key-only forwarding=disabled",
                "OMPRODUCT_READY state=degraded schema=1",
                "OMINIT_SERVICE_END name=S50-radio-ap rc=1",
            ]
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "uart.log"
            path.write_text(good, encoding="utf-8")
            passed, markers = MODULE.uart_gate(path)
            self.assertTrue(passed, markers)
            path.write_text(good + "\nKernel panic - not syncing", encoding="utf-8")
            passed, markers = MODULE.uart_gate(path)
            self.assertFalse(passed)
            self.assertFalse(markers["fatal_absent"])

    def test_hash_bearing_evidence_is_pass_only(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "evidence.log"
            path.write_text("evidence\n", encoding="utf-8")
            self.assertEqual([], MODULE.evidence_entries("FAIL", [path]))
            entries = MODULE.evidence_entries("PASS", [path])
            self.assertEqual(1, len(entries))
            self.assertEqual(MODULE.sha256(path), entries[0]["sha256"])


if __name__ == "__main__":
    unittest.main()
