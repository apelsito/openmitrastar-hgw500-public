#!/usr/bin/env python3

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "work/mission-state/q3-persistent-composite-f66-2g-queue-guard/build"
MANIFEST = BUILD / "manifest.json"
REPORT = BUILD / "f66-fixed-size-patch-report.json"
CONTRACT = BUILD / "bootbase-contract.json"
WEB = BUILD / "openmitrastar-linux510-q3-persistent-f66-2g-autorate-reclaim-LZMA-OFFLINE-NO-FLASH.webformat.bin"
COMPACT_LOADER = BUILD / "om-radio-modules.fixedsize"
OLD_LOADER = ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-radio-modules"
TFTP_COPY = ROOT / "work/tftp/omvl/openmitrastar-linux510-q3-persistent-f66-2g-autorate-reclaim-LZMA-OFFLINE-NO-FLASH.webformat.bin"


class F66FixedSizeFromF65Tests(unittest.TestCase):
    def test_artifacts_exist_and_fit_linux_live(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
        self.assertEqual(manifest["schema"], "openmitrastar.q3-persistent-composite-f66/v1")
        self.assertEqual(manifest["classification"], "F66_FIXED_SIZE_FROM_F65_2G_AUTORATE_RECLAIM")
        self.assertTrue(WEB.is_file())
        self.assertLessEqual(WEB.stat().st_size, 7_995_392)
        self.assertTrue(manifest["slot"]["fits"])
        self.assertEqual(manifest["artifacts"]["webformat"]["bytes"], WEB.stat().st_size)
        self.assertTrue(TFTP_COPY.is_file())
        self.assertEqual(TFTP_COPY.read_bytes(), WEB.read_bytes())

    def test_bootbase_contract_accepts_candidate(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(manifest["bootbase_contract"]["result"], "PASS")
        self.assertTrue(manifest["bootbase_contract"]["candidate_accepted"])
        self.assertEqual(contract["result"], "PASS")
        self.assertTrue(contract["candidate"]["accepted_by_contract"])

    def test_fixed_size_loader_patch_is_padded_and_contains_queue_guard(self) -> None:
        report = json.loads(REPORT.read_text(encoding="ascii"))
        compact = COMPACT_LOADER.read_text(encoding="utf-8")
        self.assertLessEqual(report["compact_loader_size"], report["old_loader_size"])
        self.assertEqual(report["old_loader_size"], OLD_LOADER.stat().st_size)
        self.assertEqual(report["padding_bytes"], report["old_loader_size"] - report["compact_loader_size"])
        for needle in (
            "hgw500_tx_queue_guard=N",
            "hgw500_tx_reclaim_poll=1",
            "hgw500_tx_reclaim_poll=Y",
            "profile=all64-autorate-eapol-mgntq-reclaim",
            "hgw500_force_data_mcs7=0",
            "hgw500_force_data_mcs7=N",
            "hgw500_txbd_be_data_split=1",
        ):
            self.assertIn(needle, compact)
        self.assertNotIn("hgw500_tx_queue_guard=1", compact)
        self.assertNotIn("hgw500_tx_queue_guard=Y", compact)
        self.assertNotIn("hgw500_force_data_mcs7=1", compact)
        self.assertNotIn("hgw500_force_data_mcs7=Y", compact)

    def test_no_hardware_scope(self) -> None:
        report = json.loads(REPORT.read_text(encoding="ascii"))
        manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
        self.assertFalse(report["hardware_actions"])
        self.assertFalse(report["flash_supported"])
        self.assertFalse(manifest["security"]["touches_router"])
        self.assertFalse(manifest["security"]["opens_uart"])
        self.assertFalse(manifest["security"]["flash"])


if __name__ == "__main__":
    unittest.main()
