#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/rtl8192ee/trx.c"
MODULE_LOADER = ROOT / "work/mission-state/w2-2g-parity-v1/rootfs/usr/sbin/om-radio-modules"


class Rtl8192eeMgmtTxbdSplitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = TRX.read_text(encoding="utf-8")

    def test_split_is_explicit_and_target_gated(self) -> None:
        self.assertIn("module_param_named(hgw500_txbd_mgmt_split", self.source)
        self.assertIn("hgw500_txbd_mgmt_split &&", self.source)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.source)

    def test_management_header_and_body_use_separate_compact_segments(self) -> None:
        self.assertIn("header_len = ieee80211_hdrlen(frame_control);", self.source)
        self.assertIn("ieee80211_is_auth(frame_control)", self.source)
        self.assertIn("ieee80211_is_assoc_resp(frame_control)", self.source)
        self.assertIn("tx_bd_desc[2] = cpu_to_le32(header_len);", self.source)
        self.assertIn("tx_bd_desc[4] = cpu_to_le32(pkt_len - header_len);", self.source)
        self.assertIn("tx_bd_desc[5] = cpu_to_le32((u32)addr + header_len);", self.source)
        self.assertIn("OMRTLTX16 stage=mgmt-reply-txbd-split", self.source)

    def test_probe_responses_keep_the_known_visible_single_buffer_path(self) -> None:
        split_block = self.source.split("split_mgmt =", 1)[1].split(";", 1)[0]
        self.assertNotIn("ieee80211_is_probe_resp", split_block)

    def test_default_path_remains_single_buffer(self) -> None:
        self.assertIn("tx_bd_desc[2] = cpu_to_le32(pkt_len);", self.source)
        self.assertIn("tx_bd_desc[3] = cpu_to_le32((u32)addr);", self.source)

    def test_product_loader_enables_and_verifies_reply_split(self) -> None:
        loader = MODULE_LOADER.read_text(encoding="utf-8")
        self.assertIn("hgw500_txbd_mgmt_split=1", loader)
        self.assertIn("hgw500_txbd_mgmt_split=Y", loader)


if __name__ == "__main__":
    unittest.main()
