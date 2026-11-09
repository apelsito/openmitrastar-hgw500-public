#!/usr/bin/env python3
from pathlib import Path
import hashlib
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "work/mission-state/q3-maintenance-hbm-clear-tqe-dma-emac-aneg-v1/build"
IMAGE = ROOT / "work/tftp/omvl/linux510-q3-maintenance-hbm-clear-tqe-dma-emac-aneg-v1-RAM-TEST-NO-FLASH.bin"
MANIFEST = LANE / "manifest.json"
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
HEADER = ROOT / "work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Q3DualPhyVariantTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_artifact_is_ram_only_and_not_flash_eligible(self):
        self.assertTrue(IMAGE.is_file())
        self.assertFalse(self.manifest["candidate_eligible"])
        self.assertFalse(self.manifest["flash_supported"])
        self.assertEqual(self.manifest["runtime_gates"]["flash"],
                         "forbidden-until-new-Q3-hardware-gates")

    def test_manifest_pins_exact_emac_sources(self):
        contract = self.manifest["ram_only_overrides"]["emac_dual_phy_autoneg"]
        self.assertEqual(contract["driver_embedded_sha256"], sha(DRIVER))
        self.assertEqual(contract["header_embedded_sha256"], sha(HEADER))
        self.assertEqual(contract["ports"],
                         ["emac1/irq20/phy3", "emac0/irq19/phy1"])

    def test_tftp_copy_is_exact_published_webformat(self):
        artifact = self.manifest["artifacts"]["webformat"]
        self.assertEqual(artifact["sha256"], sha(IMAGE))
        self.assertEqual(artifact["bytes"], IMAGE.stat().st_size)
        self.assertEqual(self.manifest["artifacts"]["tftp_copy"]["sha256"],
                         sha(IMAGE))

    def test_reproducible_and_ram_layout_safe(self):
        reproducibility = self.manifest["reproducibility"]
        self.assertTrue(all(reproducibility.values()))
        layout = self.manifest["ram_layout"]
        self.assertTrue(layout["safe_offline"])
        self.assertTrue(all(layout["non_overlap"].values()))


if __name__ == "__main__":
    unittest.main(verbosity=2)
