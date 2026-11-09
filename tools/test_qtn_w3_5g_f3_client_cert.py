#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_qtn_w3_5g_f3_client_cert.py"


class Qtn5gF3ClientCertTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        sys.path.insert(0, str(ROOT / "tools"))
        spec = importlib.util.spec_from_file_location("qtn5g_f3", SCRIPT)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)
        cls.text = SCRIPT.read_text(encoding="utf-8")
        cls.gate = cls.module.values(cls.module.APPROVED)
        cls.module.verify_gate(cls.gate)

    def sample(self, index: int) -> dict[str, int | str]:
        return {
            "assoc": 1,
            "rx_bytes": 1000 + index * 100,
            "tx_bytes": 2000 + index * 120,
            "rx_packets": 10 + index,
            "tx_packets": 20 + index,
            "hostapd": 1,
            "irq8": 100 + index,
            "irq9": 7,
            "irq10": 3,
            "fatal": 0,
            "watchdog": 1,
            "qdrv": 1,
            "rf": 1,
            "bridge": 1,
            "channel": 36,
            "bw": 80,
            "region": "es",
            "ssh_sessions": 2,
        }

    def test_target_surface_is_observation_only(self) -> None:
        forbidden = (
            r"call_qcsapi[^\n]*\bset_",
            r"brctl\s+(?:addif|delif)",
            r"ifconfig\s+wifi0\s+(?:up|down)",
            r"ip\s+link\s+set",
            r">\s*[\"']?/sys/module/qdrv",
            r"\b(?:flash_erase|nandwrite|mtd_debug|flashcp|saveenv)\b",
        )
        for pattern in forbidden:
            self.assertNotRegex(self.text, re.compile(pattern, re.IGNORECASE))
        self.assertIn("client_monitor.sample(host)", self.text)

    def test_valid_ten_minute_soak_passes(self) -> None:
        samples = [self.sample(index) for index in range(58)]
        result = self.module.evaluate_soak(samples, 600.1, self.gate)
        self.assertEqual(result["samples"], 58)
        self.assertGreater(result["rx_bytes_delta"], 0)
        self.assertGreater(result["tx_bytes_delta"], 0)
        self.assertGreater(result["irq8_delta"], 0)
        self.assertEqual(result["irq9_delta"], 0)

    def test_association_is_required_for_every_sample(self) -> None:
        samples = [self.sample(index) for index in range(58)]
        samples[20]["assoc"] = 0
        with self.assertRaisesRegex(self.module.CertificationError, "association-lost"):
            self.module.evaluate_soak(samples, 600.1, self.gate)

    def test_all_four_counters_must_progress_and_never_regress(self) -> None:
        for counter in self.module.COUNTERS:
            samples = [self.sample(index) for index in range(58)]
            for sample in samples:
                sample[counter] = 100
            with self.assertRaisesRegex(self.module.CertificationError, f"no-progress:{counter}"):
                self.module.evaluate_soak(samples, 600.1, self.gate)
        samples = [self.sample(index) for index in range(58)]
        samples[30]["rx_packets"] = 0
        with self.assertRaisesRegex(self.module.CertificationError, "counter-regressed:rx_packets"):
            self.module.evaluate_soak(samples, 600.1, self.gate)

    def test_irq_contract_requires_all_and_progress_only_on_irq8(self) -> None:
        samples = [self.sample(index) for index in range(58)]
        for sample in samples:
            sample["irq8"] = 100
        with self.assertRaisesRegex(self.module.CertificationError, "no-progress:irq8"):
            self.module.evaluate_soak(samples, 600.1, self.gate)
        samples = [self.sample(index) for index in range(58)]
        samples[15]["irq9"] = 0
        with self.assertRaisesRegex(self.module.CertificationError, "counter-regressed:irq9"):
            self.module.evaluate_soak(samples, 600.1, self.gate)

    def test_fatal_watchdog_and_management_fail_closed(self) -> None:
        samples = [self.sample(index) for index in range(58)]
        samples[5]["fatal"] = 1
        with self.assertRaisesRegex(self.module.CertificationError, "muc-or-kernel-fatal"):
            self.module.evaluate_soak(samples, 600.1, self.gate)
        self.assertIn("management SSH/sample failed during soak", self.text)
        self.assertIn('"W3_SSH_FAILURES_MAX": "0"', self.text)

    def test_short_soak_or_sparse_sampling_fails(self) -> None:
        samples = [self.sample(index) for index in range(58)]
        with self.assertRaisesRegex(self.module.CertificationError, "soak-too-short"):
            self.module.evaluate_soak(samples, 599.9, self.gate)
        with self.assertRaisesRegex(self.module.CertificationError, "insufficient-ssh-samples"):
            self.module.evaluate_soak(samples[:57], 600.1, self.gate)

    def test_internet_speedtest_and_dfs_are_explicitly_out_of_scope(self) -> None:
        for marker in (
            "internet=UNVERIFIED",
            "speedtest=UNVERIFIED",
            "dfs=UNVERIFIED",
            "F3_FULL=0",
        ):
            self.assertIn(marker, self.text)
        self.assertNotRegex(self.text, re.compile(r"\b(?:speedtest|iperf3?)\s+", re.IGNORECASE))

    def test_exact_control_plane_marker_required(self) -> None:
        marker = self.module.CONTROL_PASS
        self.assertTrue(self.module.exact_marker(marker, marker))
        self.assertFalse(self.module.exact_marker("PREFIX" + marker + "SUFFIX", marker))

    def test_dry_run(self) -> None:
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=ROOT, text=True,
            capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("W3_QTN_5G_F3_CLIENT_CERT_DRY_RUN_PASS=1", result.stdout)
        self.assertIn("'internet': 'UNVERIFIED'", result.stdout)


if __name__ == "__main__":
    unittest.main()
