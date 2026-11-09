#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import run_qtn_w3_native_open_soak as soak


def sample(base: int, assoc: int = 1) -> dict[str, int]:
    return {
        "assoc": assoc,
        "rx_packets": base,
        "tx_packets": base,
        "rx_bytes": base * 100,
        "tx_bytes": base * 100,
        "irq8": base,
        "wlan0_rx": base,
        "wlan0_tx": base,
        "fatal": 0,
        "management": 1,
        "radio2g": 1,
        "timer_reclaim": 0,
    }


class NativeOpenSoakTests(unittest.TestCase):
    def test_pass_requires_full_progress(self):
        result = soak.evaluate([sample(100 + i) for i in range(36)], 180.1, 180)
        self.assertGreater(result["irq8_delta"], 0)
        self.assertEqual(result["association_min"], 1)

    def test_rejects_no_rx(self):
        values = [sample(100 + i) for i in range(36)]
        for current in values:
            current["rx_packets"] = 100
        with self.assertRaisesRegex(soak.SoakError, "no-progress:rx_packets"):
            soak.evaluate(values, 180.1, 180)

    def test_rejects_irq_stall(self):
        values = [sample(100 + i) for i in range(36)]
        for current in values:
            current["irq8"] = 100
        with self.assertRaisesRegex(soak.SoakError, "no-progress:irq8"):
            soak.evaluate(values, 180.1, 180)

    def test_rejects_2g_loss(self):
        values = [sample(100 + i) for i in range(36)]
        values[10]["radio2g"] = 0
        with self.assertRaisesRegex(soak.SoakError, "radio2g-lost"):
            soak.evaluate(values, 180.1, 180)

    def test_remote_contract_is_oem_parity_and_read_only(self):
        text = soak.remote_sample("192.168.1.90")
        for required in (
            "brif/eth1_emac1", "brif/wifi0", "brif/wlan0",
            "192\\.168\\.1\\.90", "w3_hbm_timer_reclaim_enable",
            "radio2g/ctrl", "all_sta", "irq8=",
        ):
            self.assertIn(required, text)
        for forbidden in ("ifconfig br0 192", "mtd", "flash_erase", "openmitrastar_rf_enable=1"):
            self.assertNotIn(forbidden, text)

    def test_dry_run(self):
        result = subprocess.run(
            [sys.executable, "-B", str(ROOT / "tools/run_qtn_w3_native_open_soak.py")],
            cwd=ROOT, text=True, capture_output=True, check=True,
        )
        self.assertIn("W3_QTN_NATIVE_OPEN_SOAK_DRY_RUN_PASS=1", result.stdout)
        self.assertIn('"host": "192.168.1.90"', result.stdout)


if __name__ == "__main__":
    unittest.main()
