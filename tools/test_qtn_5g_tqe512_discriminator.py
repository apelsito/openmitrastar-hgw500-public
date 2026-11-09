#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_qtn_w3_tx7_client_traffic.py"
START = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-radio5-start"
EVIDENCE = ROOT / "outputs/kernel-port/quantenna-5g-aelita-one-shot-20260823/windows-manual-5g-20260823-153709.json"

spec = importlib.util.spec_from_file_location("qtn_tqe512_runner", RUNNER)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Qtn5gTqe512DiscriminatorTests(unittest.TestCase):
    def test_live_failure_is_post_association_pre_dhcp(self) -> None:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8-sig"))
        self.assertTrue(evidence["test"]["connected"])
        self.assertFalse(evidence["test"]["dhcp"])
        self.assertIsNone(evidence["test"]["ipv4"]["ipv4"])
        self.assertTrue(evidence["restore"]["connected"])
        self.assertEqual(
            "Connected to 5 GHz without non-APIPA IPv4",
            evidence["execution_error"],
        )

    def test_only_runtime_discriminator_is_tqe_ring_512(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("Q3_RADIO5_TQE_RING_ENTRIES=512", source)
        self.assertIn('OM_RADIO5_TQE512_FEATURE="$gate/tqe512.feature"', source)
        self.assertIn('tqe_ring=512 isolated_l3=192.168.77.1/24', source)
        self.assertIn('w3_rx_ring_entries)" = 512', source)
        for name, (_, expected) in module.SAFE_MODULES.items():
            self.assertIn(expected, source, name)

    def test_staged_start_relaxes_only_256_guard_to_256_or_512(self) -> None:
        original = START.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        staged = module.SAFE_START[0].read_text(encoding="utf-8")
        self.assertIn('[ "$tqe_ring_entries" = 256 ] || refuse beacon-lifetime-requires-tqe256', original)
        self.assertIn('case "$tqe_ring_entries" in 256|512)', staged)
        self.assertIn("beacon-lifetime-requires-tqe256", staged)
        self.assertIn("OM_RADIO5_STOP", runner)

    def test_failure_rollback_is_wifi0_and_overlay_only(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("om-radio5-stop tx7-client-gate-timeout", source)
        self.assertIn("rm -rf {SAFE_OVERLAY}", source)
        self.assertIn("eth0_2g=preserved", source)
        for forbidden in ("rmmod rtl8192ee", "ifconfig wlan0 down", "brctl delif br0 wlan0"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
