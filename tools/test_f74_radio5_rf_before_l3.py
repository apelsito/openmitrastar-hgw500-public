import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402


BUILD = ROOT / "work/mission-state/q3-persistent-composite-f74-5g-rf-before-l3/build"
BASE = "openmitrastar-linux510-q3-persistent-f74-5g-rf-before-l3-LZMA-OFFLINE-NO-FLASH"


class F74Radio5RfBeforeL3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (BUILD / "manifest.json").is_file():
            raise unittest.SkipTest("F74 has not been built yet")
        cls.manifest = json.loads((BUILD / "manifest.json").read_text(encoding="ascii"))
        cls.result = json.loads((BUILD / "build-result.json").read_text(encoding="ascii"))
        raw = (BUILD / f"{BASE}.decompressed.bin").read_bytes()
        cls.cpio_start, cls.entries, cls.remainder = f71.parse_first_cpio(raw)
        cls.start_entry = next(e for e in cls.entries if e.name == "usr/sbin/om-radio5-start")
        cls.start_text = cls.start_entry.data.decode("ascii")

    def test_fixed_offset_contract(self):
        patch = self.manifest["patch"]
        self.assertEqual("F74_FIXED_OFFSET_FROM_F73_RADIO5_START_ORDER_ONLY", self.manifest["classification"])
        self.assertEqual(0, patch["delta_bytes"])
        self.assertEqual(15692768, patch["raw_bytes"])
        self.assertEqual(8192, patch["cpio_start"])
        self.assertEqual(12046444, patch["cpio_end"])
        self.assertEqual(
            "abdce4c0c6d6debbf2d25395f7137a343b91cdeeecd82e27cfa987ac70dd4b17",
            patch["remainder_sha256"],
        )

    def test_rf_open_precedes_wifi0_l3_up(self):
        rf_index = self.start_text.index("printf '1\\n' >\"$rf\" || refuse rf-open")
        l3_index = self.start_text.index(
            "ifconfig wifi0 192.168.77.1 netmask 255.255.255.0 up || refuse wifi0-l3-config"
        )
        hostapd_index = self.start_text.index('/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &')
        self.assertLess(rf_index, l3_index)
        self.assertLess(l3_index, hostapd_index)
        self.assertEqual(
            "open qdrv RF before ifconfig wifi0 192.168.77.1 ... up",
            self.manifest["patch"]["fix"],
        )

    def test_scope_does_not_change_modules_or_topology(self):
        scope = self.manifest["change_scope"]
        self.assertEqual("unchanged from F73", scope["qdrv"])
        self.assertEqual("unchanged from F73", scope["radio2g_modules"])
        self.assertEqual("unchanged from F73", scope["radio5_modules"])
        self.assertEqual("unchanged from F73", scope["queues_dma_rates_rings"])
        self.assertEqual("unchanged from F73", scope["bridge_topology"])
        self.assertFalse(self.manifest["security"]["flash"])
        self.assertFalse(self.result["flash"])

    def test_build_result_passes_bootbase_contract(self):
        self.assertEqual("PASS", self.result["status"])
        self.assertTrue(self.manifest["slot"]["fits"])
        self.assertEqual("PASS", self.manifest["bootbase_contract"]["result"])
        self.assertTrue(self.manifest["bootbase_contract"]["candidate_accepted"])


if __name__ == "__main__":
    unittest.main()
