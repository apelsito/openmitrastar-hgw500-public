#!/usr/bin/env python3
from __future__ import annotations

import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PATCH = ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-rx-unaligned-header-topaz.patch"
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"


class Rtl8192eeRxUnalignedHeaderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.patch = PATCH.read_text(encoding="utf-8")
        cls.trx = TRX.read_text(encoding="utf-8")
        cls.pci = PCI.read_text(encoding="utf-8")

    def test_faulting_frame_control_load_becomes_unaligned_safe(self) -> None:
        self.assertIn("#include <asm/unaligned.h>", self.trx)
        self.assertIn("get_unaligned_le16((const u8 *)hdr)", self.trx)
        safe = self.trx[self.trx.index("if (unlikely(of_machine_is_compatible"):
                        self.trx.index("if (status->crc)")]
        self.assertIn("frame_control = hdr->frame_control;", safe)
        self.assertLess(safe.index("get_unaligned_le16"), safe.index("frame_control = hdr->frame_control;"))

    def test_robust_management_semantics_are_preserved(self) -> None:
        for token in (
            "ieee80211_is_disassoc(frame_control)",
            "ieee80211_is_deauth(frame_control)",
            "ieee80211_is_action(frame_control)",
            "ieee80211_has_protected(frame_control)",
            "WLAN_CATEGORY_PUBLIC",
            "WLAN_CATEGORY_HT",
            "WLAN_CATEGORY_WNM_UNPROTECTED",
            "WLAN_CATEGORY_SELF_PROTECTED",
            "WLAN_CATEGORY_UNPROT_DMG",
            "WLAN_CATEGORY_VHT",
            "WLAN_CATEGORY_VENDOR_SPECIFIC",
        ):
            self.assertIn(token, self.trx)

    def test_signal_translation_uses_aligned_header_copy_on_hgw(self) -> None:
        marker = "OMRTLRXALIGN stage=signal-safe target=hgw500"
        self.assertIn(marker, self.trx)
        start = self.trx.index("static void _rtl92ee_translate_rx_signal_stuff")
        end = self.trx.index("static void _rtl92ee_insert_emcontent")
        body = self.trx[start:end]
        for token in (
            "struct ieee80211_hdr local_hdr;",
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            "((unsigned long)tmp_buf & 1)",
            "min_t(size_t, pstatus->length,",
            "memset(&local_hdr, 0, sizeof(local_hdr));",
            "memcpy(&local_hdr, tmp_buf, copy_len);",
            "hdr = &local_hdr;",
            "ieee80211_is_data_qos(fc)",
            "(struct ieee80211_qos_hdr *)hdr",
        ):
            self.assertIn(token, body)
        self.assertLess(body.index("hdr = &local_hdr;"), body.index("fc = hdr->frame_control;"))
        self.assertNotIn("ieee80211_is_data_qos(hdr->frame_control)", body)
        self.assertNotIn("(struct ieee80211_qos_hdr *)tmp_buf", body)

    def test_frame_is_re_aligned_before_later_header_parsing(self) -> None:
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.pci)
        self.assertIn("((unsigned long)skb->data & 1)", self.pci)
        self.assertIn("skb_push(skb, 1);", self.pci)
        self.assertIn("memmove(skb->data, skb->data + 1, frame_len);", self.pci)
        self.assertIn("skb_trim(skb, frame_len);", self.pci)
        self.assertIn("OMRTLRXALIGN stage=frame-realigned", self.pci)

    def test_hgw_target_gate_wraps_both_unaligned_paths(self) -> None:
        self.assertRegex(
            self.trx,
            r'(?s)of_machine_is_compatible\("mitrastar,hgw-500bna-qcv2"\).*?'
            r'\(\(unsigned long\)hdr & 1\).*?get_unaligned_le16',
        )
        self.assertRegex(
            self.pci,
            r'(?s)of_machine_is_compatible\("mitrastar,hgw-500bna-qcv2"\).*?'
            r'\(\(unsigned long\)skb->data & 1\).*?skb_push\(skb, 1\)',
        )

    def test_patch_does_not_touch_quantenna_or_persistence(self) -> None:
        headers = re.findall(r"^(?:---|\+\+\+) ([^\n]+)$", self.patch, re.MULTILINE)
        self.assertEqual(
            [
                "a/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c",
                "b/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c",
                "a/drivers/net/wireless/realtek/rtlwifi/pci.c",
                "b/drivers/net/wireless/realtek/rtlwifi/pci.c",
            ],
            headers,
        )
        for forbidden in ("qdrv", "switch_tqe", "mtd", "flash", "bootenv"):
            self.assertNotIn(forbidden, self.patch.lower())


if __name__ == "__main__":
    unittest.main(verbosity=2)
