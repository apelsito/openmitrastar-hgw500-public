#!/usr/bin/env python3

import hashlib
import json
from pathlib import Path
import stat
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
W4 = ROOT / "work/mission-state/w4-rootfs-product/build"
W5 = ROOT / "work/mission-state/w5-product-ram-candidate/build"
F5 = ROOT / "work/mission-state/f5-autonomous-gzipinit/build"
ACTIVE = ROOT / "work/tftp/omvl/openmitrastar-linux510-f5-autonomous-gzipinit-v1.webformat.bin"
OLD_SHA = "399330afd5b59702e7492453c73f75ee1708f0d68133d5ab4e700f99bb6f1d0c"
OLD = ROOT / "work/mission-state/w5-product-ram-candidate/superseded" / OLD_SHA
RTL_SHA = "540c14deace13342e978891085e00c4cc3f085de926f4c66cce76dc28f0bc432"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProductWarmFwIntegrationTests(unittest.TestCase):
    def test_w4_manifest_pins_all64_mcs7_module(self):
        manifest = json.loads((W4 / "manifest.json").read_text(encoding="utf-8"))
        self.assertFalse(manifest["candidate_eligible"])
        self.assertFalse(manifest["flash_supported"])
        self.assertEqual(manifest["inputs"]["rtl8192ee_sha256"], RTL_SHA)
        self.assertFalse(manifest["runtime"]["rtl8192ee_warm_fw_retry"])
        self.assertFalse(manifest["runtime"]["rtl8192ee_all64_autorate_q2"])
        self.assertTrue(manifest["runtime"]["rtl8192ee_all64_mcs7_q2"])
        self.assertEqual(manifest["runtime"]["realtek_profile"], "all64-mcs7-eapol-mgntq-q2")
        self.assertEqual(manifest["runtime"]["radio2g_eapol_trace"], 0)
        self.assertEqual(manifest["runtime"]["radio2g_eapol_mgnt_queue"], 1)
        self.assertEqual(manifest["rootfs"]["sha256"], sha(W4 / manifest["rootfs"]["file"]))

    def test_f5_source_and_active_image_are_exact(self):
        w4 = json.loads((W4 / "manifest.json").read_text(encoding="utf-8"))
        f5 = json.loads((F5 / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(f5["source_rootfs"]["sha256"], w4["rootfs"]["sha256"])
        self.assertEqual(f5["source_rootfs_manifest_sha256"], sha(W4 / "manifest.json"))
        self.assertEqual(
            f5["source_rootfs_bootstrap_authorized_key_fingerprint"],
            w4["inputs"]["bootstrap_authorized_key_fingerprint"],
        )
        self.assertEqual(f5["artifacts"]["tftp_copy"]["sha256"], sha(ACTIVE))
        self.assertFalse(f5["candidate_eligible"])
        self.assertFalse(f5["flash_supported"])
        self.assertTrue(f5["reproducibility"]["initramfs_two_builds_identical"])
        self.assertTrue(f5["reproducibility"]["webformat_two_builds_identical"])

    def test_modes_and_green_bootbase_contract(self):
        f5 = json.loads((F5 / "manifest.json").read_text(encoding="utf-8"))
        contract = json.loads((F5 / "bootbase-contract.json").read_text(encoding="utf-8"))
        self.assertTrue(contract["accepted_by_contract"])
        self.assertEqual(contract["errors"], [])
        self.assertEqual(f5["artifacts"]["webformat"]["bytes"], contract["size"])
        self.assertLessEqual(f5["artifacts"]["webformat"]["bytes"], 0x007A0000)
        if shutil.which("unsquashfs"):
            with tempfile.TemporaryDirectory(prefix="om-warm-rootfs-") as directory:
                extracted = Path(directory) / "rootfs"
                subprocess.run(
                    ["unsquashfs", "-no-progress", "-d", str(extracted), str(W4 / f5["source_rootfs"]["file"])],
                    check=True, stdout=subprocess.DEVNULL,
                )
                self.assertEqual(stat.S_IMODE((extracted / "etc/inittab").stat().st_mode), 0o644)
                self.assertEqual(stat.S_IMODE((extracted / "etc/init.d/S90-ready").stat().st_mode), 0o755)
                self.assertEqual(stat.S_IMODE((extracted / "etc/shadow").stat().st_mode), 0o600)
        test_source = (ROOT / "work/mission-state/w5-product-ram-candidate/scripts/test_product_ram_candidate.py").read_text(encoding="utf-8")
        self.assertIn('qtn,recovery-led-pin = <0x09>;', test_source)
        self.assertIn('qtn,recovery-led-active-low;', test_source)
        self.assertIn('stage0 alive LED GPIO%u asserted', test_source)

    def test_w5_uncompressed_candidate_is_rejected_when_oversized(self):
        contract = json.loads((W5 / "bootbase-contract.json").read_text(encoding="utf-8"))
        self.assertFalse(contract["accepted_by_contract"])
        self.assertIn("RAS payload exceeds slot", contract["errors"][0])

    def test_399330_is_preserved_as_old_w5_supersession(self):
        supersession = json.loads((OLD / "supersession.json").read_text(encoding="utf-8"))
        old_image = OLD / "linux510-product-rootfs-ram-equivalent-v1-RAM-ONLY.bin"
        old_manifest = OLD / "original-manifest.json"
        self.assertEqual(sha(old_image), OLD_SHA)
        self.assertEqual(sha(old_manifest), supersession["superseded"]["original_manifest_sha256"])
        self.assertTrue(supersession["superseded"]["preserved"])


if __name__ == "__main__":
    unittest.main()
