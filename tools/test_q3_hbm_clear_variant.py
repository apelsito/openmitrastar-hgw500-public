#!/usr/bin/env python3
import hashlib
import json
import os
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANE = Path(os.environ.get(
    "OM_Q3_LANE", ROOT / "work/mission-state/q3-maintenance-hbm-clear-v1"
))
STAGE = Path(os.environ.get(
    "OM_Q3_STAGE_A", "/home/user/openmitrastar-build/q3-maintenance-hbm-clear-v1/rootfs-a"
))
TFTP = Path(os.environ.get(
    "OM_Q3_TFTP_PATH",
    ROOT / "work/tftp/omvl/linux510-q3-maintenance-hbm-clear-v1-RAM-TEST-NO-FLASH.bin",
))
CANONICAL = ROOT / "work/tftp/omvl/linux510-q3-maintenance-v1-RAM-TEST-NO-FLASH.bin"
EXPECTED_CANONICAL = "f07223cf562ae5cd078d18ec9448e87688fe922b4b49d6cc21b9075ed3253477"
EXPECTED_HBM = "f3b8b78ffda138c5c8287c923086c51cd896e51539ff7a17caa394c0bc6cebb8"
MODULE = STAGE / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/hbm.ko"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Q3HbmClearVariantTest(unittest.TestCase):
    def test_canonical_maintenance_image_is_untouched(self):
        self.assertEqual(EXPECTED_CANONICAL, sha(CANONICAL))

    def test_instrumented_hbm_is_exactly_embedded(self):
        self.assertEqual(EXPECTED_HBM, sha(MODULE))
        manifest = json.loads((LANE / "build/manifest.json").read_text())
        override = manifest["ram_only_overrides"]["hbm_clear_probe"]
        self.assertEqual(EXPECTED_HBM, override["sha256"])
        self.assertEqual(EXPECTED_HBM, override["embedded_sha256"])
        self.assertFalse(override["flash_actions"])

        sums = (STAGE / "usr/share/openmitrastar/radio5g/artifacts.sha256").read_text()
        self.assertIn(
            EXPECTED_HBM + " /lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/hbm.ko",
            sums,
        )
        runtime = (STAGE / "usr/share/openmitrastar/radio5g/runtime.env").read_text()
        self.assertIn("Q3_HBM_SHA256=" + EXPECTED_HBM, runtime)

    def test_ram_layout_is_disjoint_from_hbm_and_kernel(self):
        manifest = json.loads((LANE / "build/manifest.json").read_text())
        layout = manifest["ram_layout"]
        self.assertEqual("0x87000000", layout["staging"]["start"])
        self.assertTrue(layout["staging_in_ddr"])
        self.assertTrue(layout["safe_offline"])
        self.assertEqual("0x8063c000", layout["hbm_reserved"]["start"])
        self.assertEqual("0x8490c400", layout["hbm_reserved"]["end"])
        self.assertTrue(all(layout["non_overlap"].values()))

    def test_variant_is_reproducible_and_tftp_bound(self):
        manifest = json.loads((LANE / "build/manifest.json").read_text())
        for value in manifest["reproducibility"].values():
            self.assertTrue(value)
        self.assertEqual(sha(TFTP), manifest["artifacts"]["tftp_copy"]["sha256"])
        self.assertEqual(TFTP.read_bytes(), (LANE / "build" / manifest["artifacts"]["webformat"]["file"]).read_bytes())

    def test_runner_passes_safe_load_address(self):
        runner = (ROOT / "tools/run_q3_maintenance_hbm_clear_v1.ps1").read_text()
        self.assertIn("$loadAddress = '0x87000000'", runner)
        self.assertIn("'-LoadAddress', $loadAddress", runner)
        self.assertIn("staging_vs_hbm", runner)

    def test_manual_radio_prerequisites_run_at_boot_without_rf(self):
        s53 = STAGE / "etc/init.d/S53-qtn-calibration"
        s54 = STAGE / "etc/init.d/S54-qtn-mac"
        s55 = STAGE / "etc/init.d/S55-radio5-ap"
        self.assertEqual(
            "23f9a6e661fcc67d8b62444b06164bb27d30167bdfbb0d679dc0f168d87bd404",
            sha(s53),
        )
        self.assertEqual(
            "cd3cd913ec763e1a0ce58f9b40d990931deac82118226ead57b0fe8a9588715d",
            sha(s54),
        )
        self.assertNotIn("q3-radio5-autostart", s53.read_text())
        self.assertNotIn("q3-radio5-autostart", s54.read_text())
        self.assertIn("exec /usr/sbin/om-qtn-cal-readonly", s53.read_text())
        self.assertIn("exec /usr/sbin/om-qtn-mac-prepare", s54.read_text())
        self.assertIn("hardware-gate-closed", s55.read_text())


if __name__ == "__main__":
    unittest.main(verbosity=2)
