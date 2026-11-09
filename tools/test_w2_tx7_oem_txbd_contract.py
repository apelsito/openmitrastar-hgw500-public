#!/usr/bin/env python3

import hashlib
import json
import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
OEM_BASE = (
    ROOT
    / "work/sources/rtl8198c-rtk-ref/rtk_openwrt_sdk/target/linux/realtek/files/drivers/net/wireless/rtl8192cd"
)
LINUX = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi"
TX1 = ROOT / "outputs/kernel-port/realtek-loop/w2-tx1-publish-barrier-RAM-ONLY-NO-FLASH"
TX5 = ROOT / "outputs/kernel-port/realtek-loop/w2-tx5-beacon-tasklet-poll-desc-clear-RAM-ONLY-NO-FLASH"
TX7 = ROOT / "outputs/kernel-port/realtek-loop/w2-tx7-hybrid32-rxmode-RAM-ONLY-NO-FLASH"
TX7_BUILD = ROOT / "work/mission-state/w2-2g-parity-tx7-hybrid32-v1/build/manifest.json"
TX7_SOAK = ROOT / "outputs/uart-live/w2-tx7-autoreconnect-soak-20260822.log.json"
TX7_GATE = ROOT / "outputs/uart-live/w2-tx7-autoreconnect-soak-20260822.gate-result.json"


def read(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Tx7OemTxbdContractTests(unittest.TestCase):
    def test_oem_selects_four_8_byte_segments(self):
        cfg = read(OEM_BASE / "WlanHAL/HalCfg.h")
        txh = read(OEM_BASE / "WlanHAL/RTL88XX/Hal88XXTxDesc.h")
        self.assertIn("#define TXBD_SEG_32_64_SEL      0", cfg)
        for queue in ("VOQ", "VIQ", "BEQ", "BKQ", "MGQ"):
            self.assertIn(f"#define TX_{queue}_TXBD_MODE_SEL", cfg)
        self.assertIn("TXBD_ELEMENT\tTXBD_ELE[TXBD_ELE_NUM]", txh)
        self.assertIn("u4Byte         PsbLen          :15", txh)
        self.assertIn("u4Byte         Rsvd_31         :1", txh)

    def test_oem_clears_global_width_bit(self):
        gen = read(OEM_BASE / "WlanHAL/RTL88XX/Hal88XXGen.c")
        self.assertIn("RXBDReg = (RXBDReg & ~BIT_SYS_32_64) | (TXBD_SEG_32_64_SEL << 15);", gen)
        self.assertIn("HAL_RTL_W16(REG_RX_RXBD_NUM, RXBDReg);", gen)

    def test_oem_commits_psblen_then_host_wp_not_own(self):
        txc = read(OEM_BASE / "WlanHAL/RTL88XX/Hal88XXTxDesc.c")
        self.assertIn("TXBD_DW0_PSLEN_MSK", txc)
        self.assertIn("TxPktFinalIO88XX_WRITE, PSBLen", txc)
        self.assertIn("TxPktFinalIO88XX_CHECK, 0", txc)
        self.assertIn("HAL_RTL_W16(cur_q->reg_rwptr_idx, cur_q->host_idx);", txc)

    def test_linux_tx7_data_layout_and_endian_match_oem(self):
        trx = read(LINUX / "rtl8192ee/trx.c")
        self.assertIn("memset(tx_bd_desc, 0, 32);", trx)
        self.assertIn("set_tx_buff_desc_psb(tx_bd_desc, psblen);", trx)
        self.assertIn("set_tx_buff_desc_own(tx_bd_desc, 0);", trx)
        self.assertIn("tx_bd_desc[1] = cpu_to_le32((u32)desc_dma_addr);", trx)
        self.assertIn("tx_bd_desc[2] = cpu_to_le32(pkt_len);", trx)
        self.assertIn("tx_bd_desc[3] = cpu_to_le32((u32)addr);", trx)

    def test_linux_rp_wp_and_reclaim_match_oem_boundary(self):
        trx = read(LINUX / "rtl8192ee/trx.c")
        self.assertIn("cur_tx_rp = (u16)((qidx >> 16) & 0x0fff);", trx)
        self.assertIn("hw_write_point = (u16)(qidx & 0x0fff);", trx)
        self.assertIn("index == HW RP is not", trx)
        self.assertIn("rtl_write_word(rtlpriv, desc_address, ring->cur_tx_wp);", trx)

    def test_tx1_tx5_and_tx7_isolate_the_width_mismatch(self):
        tx1 = json.loads(read(TX1 / "manifest.json"))
        tx5 = json.loads(read(TX5 / "manifest.json"))
        tx7 = json.loads(read(TX7 / "manifest.json"))
        self.assertNotIn("hgw500_txbd_compact32", tx1["experiments"])
        self.assertIn("hgw500_txbd_compact32", tx5["experiments"])
        self.assertNotIn("hardware_width_bit", tx5["experiments"]["hgw500_txbd_compact32"])
        exp = tx7["experiments"]["hgw500_txbd_compact32"]
        self.assertEqual(exp["hardware_width_bit"], 15)
        self.assertEqual(exp["hardware_width_bit_value"], 0)
        self.assertTrue(exp["hybrid_layout"])
        self.assertEqual(exp["compact_queues"], ["BK", "BE", "VI", "VO"])
        self.assertEqual(exp["preserved_64_byte_queues"], ["BEACON", "TXCMD", "MGNT", "HIGH", "HCCA"])

    def test_tx7_still_requires_a_real_client_before_tx8(self):
        build = json.loads(read(TX7_BUILD))
        soak = json.loads(read(TX7_SOAK))
        gate = json.loads(read(TX7_GATE))
        image = ROOT / build["artifacts"]["tftp_copy"]["file"]
        if not image.is_file():
            image = ROOT / "work/tftp/omvl" / build["artifacts"]["tftp_copy"]["file"]
        self.assertEqual(build["classification"], "RAM-ONLY-W2-2G-PARITY-TX7-HYBRID32-NO-FLASH")
        self.assertFalse(build["flash_supported"])
        self.assertEqual(soak["duration_observed_seconds"], 602.593)
        self.assertFalse(soak["association_observed"])
        self.assertFalse(soak["authorization_observed"])
        self.assertEqual(soak["be_events_observed"], 0)
        self.assertEqual(soak["fatal_markers_during_run"], 0)
        self.assertEqual(gate["status"], "NO_CLIENT")
        self.assertEqual(gate["failures"], ["association_missing"])
        self.assertEqual(sha256(image), build["artifacts"]["tftp_copy"]["sha256"])


if __name__ == "__main__":
    unittest.main()
