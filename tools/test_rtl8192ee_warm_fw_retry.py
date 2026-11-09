#!/usr/bin/env python3

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
FW = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/fw.c"
APPLY = ROOT / "tools/apply_topaz_linux_510_overlay.sh"
SIBLING = ROOT / "outputs/handoffs/openmitrastar-2g4-private-20260818-063600/src/linux-5.10/drivers/net/wireless/realtek/rtlwifi"
ANALYSIS = ROOT / "outputs/kernel-port/rtl8192ee-warm-fw-retry/OFFLINE_ANALYSIS.md"
BUNDLE_MANIFEST = ROOT / "outputs/kernel-port/realtek-loop/warm-fw-retry-RAM-ONLY-NO-FLASH/manifest.json"


class WarmFirmwareRetryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fw = FW.read_text(encoding="utf-8")
        cls.apply = APPLY.read_text(encoding="utf-8")

    def test_exact_board_gate_and_local_driver_scope(self):
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.fw)
        self.assertIn('#include <linux/of.h>', self.fw)
        self.assertIn('drivers/net/wireless/realtek/rtlwifi/rtl8192ee/fw.c', self.apply)

    def test_retry_is_one_shot_and_checksum_only(self):
        public = self.fw[self.fw.index("int rtl92ee_download_fw"):self.fw.index("static bool _rtl92ee_check_fw_read_last_h2c")]
        self.assertEqual(public.count("_rtl92ee_download_fw_once("), 2)
        self.assertIn("if (err && mitrastar_retry && checksum_timeout)", public)
        self.assertIn("checksum_timeout = false", public)
        self.assertNotRegex(public, r"\b(?:for|while)\s*\(")
        self.assertIn("reason=checksum-timeout attempt=1", public)

    def test_wintini_timeout_does_not_set_checksum_retry_flag(self):
        free = self.fw[self.fw.index("static int _rtl92ee_fw_free_to_go"):self.fw.index("static int _rtl92ee_download_fw_once")]
        self.assertEqual(free.count("*checksum_timeout = true"), 1)
        checksum_failure = free.index("chksum report fail")
        set_flag = free.index("*checksum_timeout = true")
        ready_failure = free.index("Polling FW ready fail")
        self.assertLess(checksum_failure, set_flag)
        self.assertLess(set_flag, ready_failure)

    def test_cleanup_uses_existing_8051_reset_and_full_fwdl_clear(self):
        cleanup = self.fw[self.fw.index("static void _rtl92ee_mitrastar_fw_cleanup"):self.fw.index("static void _rtl92ee_write_fw")]
        self.assertIn("_rtl92ee_enable_fw_download(hw, false)", cleanup)
        self.assertEqual(cleanup.count("rtl_write_dword(rtlpriv, REG_MCUFWDL, 0)"), 2)
        self.assertIn("rtl92ee_firmware_selfreset(hw)", cleanup)
        self.assertLess(cleanup.index("_rtl92ee_enable_fw_download"), cleanup.index("rtl92ee_firmware_selfreset"))
        self.assertIn("rtlhal->fw_ready = false", cleanup)
        self.assertIn("rtlhal->last_hmeboxnum = 0", cleanup)

    def test_snapshot_is_bounded_and_contains_relevant_registers(self):
        for marker in ("REG_MCUFWDL", "REG_SYS_FUNC_EN", "REG_RSV_CTRL", "REG_CR", "REG_HMETFR"):
            self.assertIn(marker, self.fw)
        self.assertEqual(self.fw.count("OMRTL92 stage=fw-warm-snapshot"), 1)
        self.assertIn('"cleanup-before"', self.fw)
        self.assertIn('"cleanup-after"', self.fw)

    def test_sibling_evidence_supports_missing_cleanup(self):
        rtl88 = (SIBLING / "rtl8188ee/fw.c").read_text(encoding="utf-8")
        rtl8723 = (SIBLING / "rtl8723com/fw_common.c").read_text(encoding="utf-8")
        for source in (rtl88, rtl8723):
            self.assertIn("REG_SYS_FUNC_EN + 1", source)
            self.assertIn("REG_MCUFWDL + 1, 0x00", source)
        self.assertIn("0x00070600", ANALYSIS.read_text(encoding="utf-8"))

    def test_incremental_bundle_records_the_gate(self):
        import json
        manifest = json.loads(BUNDLE_MANIFEST.read_text(encoding="utf-8"))
        self.assertFalse(manifest["candidate_eligible"])
        self.assertFalse(manifest["safety"]["flash_supported"])
        self.assertEqual(manifest["static_gates"]["mitrastar_warm_fw_retry"], "PASS")


if __name__ == "__main__":
    unittest.main()
