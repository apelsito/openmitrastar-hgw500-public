#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TAG = "q3-maintenance-hbm-clear-tqe-dma-v1"
RELEASE = "5.10.260-openmitrastar-radiohw"
LANE = Path(os.environ.get("OM_Q3_LANE", ROOT / "work/mission-state" / TAG))
STAGE = Path(os.environ.get("OM_Q3_STAGE_A", f"/home/user/openmitrastar-build/{TAG}/rootfs-a"))
TFTP = Path(os.environ.get(
    "OM_Q3_TFTP_PATH",
    ROOT / "work/tftp/omvl/linux510-q3-maintenance-hbm-clear-tqe-dma-v1-RAM-TEST-NO-FLASH.bin",
))
CANONICAL = ROOT / "work/tftp/omvl/linux510-q3-maintenance-hbm-clear-v1-RAM-TEST-NO-FLASH.bin"
EXPECTED_CANONICAL = "e67dbc54ee3887ac4e72bd5a5d7ed673b029586b65e2729865a5c450fe1ad932"
EXPECTED_HBM = "f3b8b78ffda138c5c8287c923086c51cd896e51539ff7a17caa394c0bc6cebb8"
EXPECTED_SWITCH_TQE = "368c347eac8fdf895cc4ec37c394a0a97b4c0297f892a506bf5986a21e532c74"
RADIO = STAGE / f"lib/modules/{RELEASE}/openmitrastar/radio5g"
OBJDUMP = ROOT / "work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-objdump"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Q3HbmClearSwitchTqeDmaVariantTest(unittest.TestCase):
    def test_parent_hbm_clear_image_is_untouched(self):
        self.assertEqual(EXPECTED_CANONICAL, sha(CANONICAL))

    def test_both_overrides_are_exactly_embedded_and_indexed(self):
        self.assertEqual(EXPECTED_HBM, sha(RADIO / "hbm.ko"))
        self.assertEqual(EXPECTED_SWITCH_TQE, sha(RADIO / "switch_tqe.ko"))

        manifest = json.loads((LANE / "build/manifest.json").read_text())
        overrides = manifest["ram_only_overrides"]
        self.assertEqual(EXPECTED_HBM, overrides["hbm_clear_probe"]["embedded_sha256"])
        switch = overrides["switch_tqe_dma_cache_fix"]
        self.assertEqual(EXPECTED_SWITCH_TQE, switch["embedded_sha256"])
        self.assertFalse(switch["dma_map_page_attrs_in_tqe_rx_pkt_drop"])
        self.assertEqual("dma_cache_inv", switch["replacement"])
        self.assertFalse(switch["flash_actions"])

        sums = (STAGE / "usr/share/openmitrastar/radio5g/artifacts.sha256").read_text()
        self.assertIn(EXPECTED_HBM + f" /lib/modules/{RELEASE}/openmitrastar/radio5g/hbm.ko", sums)
        self.assertIn(EXPECTED_SWITCH_TQE + f" /lib/modules/{RELEASE}/openmitrastar/radio5g/switch_tqe.ko", sums)
        runtime = (STAGE / "usr/share/openmitrastar/radio5g/runtime.env").read_text()
        self.assertIn("Q3_HBM_SHA256=" + EXPECTED_HBM, runtime)
        self.assertIn("Q3_SWITCH_TQE_SHA256=" + EXPECTED_SWITCH_TQE, runtime)
        direct = (STAGE / "usr/share/openmitrastar/radio5g/direct-symbols-module-manifest.tsv").read_text()
        self.assertIn("platform/topaz/switch_tqe.ko\t" + EXPECTED_SWITCH_TQE + "\t34808\t", direct)

    def test_tqe_drop_uses_arc_cache_maintenance_not_dma_map(self):
        disasm = subprocess.check_output([str(OBJDUMP), "-dr", str(RADIO / "switch_tqe.ko")], text=True)
        start = disasm.index("<tqe_rx_pkt_drop>:")
        end = disasm.index("\n\n", start)
        drop = disasm[start:end]
        self.assertIn("dma_cache_inv", drop)
        self.assertNotIn("dma_map_page_attrs", drop)

    def test_manual_radio_prerequisites_are_ready_without_rf_autostart(self):
        s53 = STAGE / "etc/init.d/S53-qtn-calibration"
        s54 = STAGE / "etc/init.d/S54-qtn-mac"
        s55 = STAGE / "etc/init.d/S55-radio5-ap"
        self.assertEqual("23f9a6e661fcc67d8b62444b06164bb27d30167bdfbb0d679dc0f168d87bd404", sha(s53))
        self.assertEqual("cd3cd913ec763e1a0ce58f9b40d990931deac82118226ead57b0fe8a9588715d", sha(s54))
        self.assertNotIn("q3-radio5-autostart", s53.read_text())
        self.assertNotIn("q3-radio5-autostart", s54.read_text())
        self.assertIn("exec /usr/sbin/om-qtn-cal-readonly", s53.read_text())
        self.assertIn("exec /usr/sbin/om-qtn-mac-prepare", s54.read_text())
        self.assertIn("hardware-gate-closed", s55.read_text())

    def test_reproducible_and_tftp_bound(self):
        manifest = json.loads((LANE / "build/manifest.json").read_text())
        self.assertTrue(all(manifest["reproducibility"].values()))
        self.assertEqual(sha(TFTP), manifest["artifacts"]["tftp_copy"]["sha256"])
        web = LANE / "build" / manifest["artifacts"]["webformat"]["file"]
        self.assertEqual(TFTP.read_bytes(), web.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
