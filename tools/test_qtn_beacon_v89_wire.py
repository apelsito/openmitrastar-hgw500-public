#!/usr/bin/env python3
from pathlib import Path
import subprocess
import unittest


ROOT = Path(__file__).resolve().parents[1]
QDRV = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"
DESC = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_beacon_desc.c"
HEADER = ROOT / "work/linux510-radio-port/quantenna/wlan/openmitrastar_beacon_preflight.h"
SHARED = ROOT / "work/sources/Quantenna-GPL/drivers/include/shared/qtn/beacon_ioctl.h"
COMM = ROOT / "work/sources/Quantenna-GPL/include/qtn/lhost_muc_comm.h"
SDK_COMM = ROOT / "work/sources/qtna_bbic4_sdk-research/include/qtn/lhost_muc_comm.h"
OEM_SHARED = ROOT / "outputs/handoffs/openmitrastar-private-quantenna5g-20260818-104227/src/oem-gpl/drivers/include/shared/qtn/beacon_ioctl.h"
DMA = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_dma_wire.h"
HOSTLINK = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_hostlink.c"
BUILDER = ROOT / "tools/build_q3_dual_radio_autostart_overlay.py"
COMPAT = ROOT / "work/linux510-radio-port/quantenna/qdrv/compat/include/asm/hardware.h"
MUC = ROOT / "outputs/radio-re/decompiled/firmware/qtn_driver.qtn_ruby.0.bin.named.decompiled.c"
WLAN89 = ROOT / "outputs/radio-re/decompiled/full/wlan.ko.decompiled.c"
START = ROOT / "work/mission-state/q3-dual-radio-autostart/rootfs/usr/sbin/om-radio5-start"
BOARD_PROBE = ROOT / "tools/qtn_board_radio_probe_remote.sh"


class BeaconV89WireTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.qdrv = QDRV.read_text(encoding="utf-8")
        cls.desc = DESC.read_text(encoding="utf-8")
        cls.header = HEADER.read_text(encoding="utf-8")
        cls.shared = SHARED.read_text(encoding="utf-8")
        cls.comm = COMM.read_text(encoding="utf-8")
        cls.sdk_shared = subprocess.check_output(
            ["git", "-C", str(ROOT / "work/sources/qtna_bbic4_sdk-research"),
             "show", "HEAD:drivers/include/shared/qtn/beacon_ioctl.h"],
            text=True,
        )
        cls.sdk_comm = SDK_COMM.read_text(encoding="utf-8")
        cls.oem_shared = OEM_SHARED.read_text(encoding="utf-8")
        cls.dma = DMA.read_text(encoding="utf-8")
        cls.hostlink = HOSTLINK.read_text(encoding="utf-8")
        cls.builder = BUILDER.read_text(encoding="utf-8")
        cls.compat = COMPAT.read_text(encoding="utf-8")
        cls.muc = MUC.read_text(encoding="utf-8")
        cls.wlan89 = WLAN89.read_text(encoding="utf-8")
        cls.start = START.read_text(encoding="utf-8")
        cls.board_probe = BOARD_PROBE.read_text(encoding="utf-8")

    def test_reverse_engineered_v89_layout_is_pinned(self) -> None:
        expected = ("dma_addr_t\tbuf", "uint8_t *\tlhost_buf", "uint32_t\tsize", "uint32_t\tnext_muc_addr", "beacon_shared_ie_t *next")
        positions = [self.shared.index(token) for token in expected]
        self.assertEqual(positions, sorted(positions))
        for token in expected:
            self.assertIn(token, self.oem_shared)
        # wlan v89 producer writes size at word 2 and next MuC address at word 3.
        self.assertIn("param_1[2] = param_3 & 0xff", self.wlan89)
        self.assertIn("*(uint *)(uVar3 + 0xc) = uVar2", self.wlan89)
        # MuC consumer reads size from word 2 and advances through word 3.
        self.assertIn("iVar2 = param_2[2]", self.muc)
        self.assertIn("param_2 = (undefined4 *)param_2[3]", self.muc)

    def test_low_wire_translation_reuses_proven_dma_helper(self) -> None:
        encode_start = self.desc.index("int om_ieee80211_beacon_prepare_v89_wire")
        encode_end = self.desc.index("EXPORT_SYMBOL(om_ieee80211_beacon_prepare_v89_wire)", encode_start)
        encode = self.desc[encode_start:encode_end]
        self.assertGreaterEqual(encode.count("qdrv_dma_handle_to_wire"), 3)
        self.assertIn("ie->buf = (dma_addr_t)buf_wire", encode)
        self.assertIn("ie->next_muc_addr = next_wire", encode)
        self.assertNotIn("ie->lhost_buf =", encode)
        self.assertNotIn("ie->size =", encode)
        self.assertNotIn("ie->next =", encode)
        self.assertIn("wire >= RUBY_MAX_DRAM_SIZE", self.dma)
        self.assertIn("virt_to_phys(ptr)", self.compat)

    def test_v89_beacon_args_and_arena_match_muc_abi(self) -> None:
        self.assertIn("#define BEACON_PARAM_SIZE\t\t1000", self.sdk_shared)
        self.assertIn("bc_ie_buf_start", self.sdk_comm)
        self.assertIn("#ifdef OPENMITRASTAR_QDRV_V89_PAIR", self.shared)
        self.assertIn("#define BEACON_PARAM_SIZE\t\t1000", self.shared)
        self.assertIn("bc_ie_buf_start", self.comm)
        self.assertIn("sizeof(struct qtn_beacon_args) != 64", self.qdrv)
        self.assertIn("offsetof(struct qtn_beacon_args, bc_ie_head) != 0x38", self.qdrv)
        self.assertIn("offsetof(struct qtn_beacon_args, bc_ie_buf_start) != 0x3c", self.qdrv)
        self.assertIn("bc_args->bc_ie_buf_start = v89_wire ? beacon_buf_start_wire", self.qdrv)
        self.assertIn("BEACON_PARAM_SIZE, &beacon_buf_start_wire", self.qdrv)
        self.assertIn("arena_wire=%#x arena_bytes=%u", self.qdrv)
        # The paired MuC reads the descriptor head and arena base at +0x38/+0x3c.
        self.assertIn("uVar3 = *(undefined4 *)(iVar9 + 0x38)", self.muc)
        self.assertIn("uVar5 = *(undefined4 *)(iVar9 + 0x3c)", self.muc)

    def test_gate_is_off_by_default_and_hgw_specific(self) -> None:
        self.assertIn("static bool openmitrastar_beacon_v89_wire_enable;", self.qdrv)
        self.assertNotIn("openmitrastar_beacon_v89_wire_enable = true", self.qdrv)
        gate = self.qdrv[self.qdrv.index("qdrv_openmitrastar_beacon_v89_wire_enabled"):]
        self.assertIn("READ_ONCE(openmitrastar_beacon_v89_wire_enable)", gate)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', gate)
        self.assertIn("openmitrastar_beacon_v89_wire_enable=1", self.start)
        self.assertIn("beacon-v89-wire-readback", self.start)
        self.assertIn('b"openmitrastar_beacon_v89_wire_enable" not in BEACON_LIFETIME_QDRV.read_bytes()', self.builder)
        self.assertIn("beacon lifetime qdrv is stale", self.builder)

    def test_host_preflight_then_encode_then_flush_barrier_then_ioctl(self) -> None:
        start = self.qdrv.index("static int qdrv_wlan_80211_beacon_update_run")
        end = self.qdrv.index("static void qdrv_wlan_beacon_work", start)
        path = self.qdrv[start:end]
        host_preflight = path.index("om_ieee80211_beacon_preflight(vap->param")
        encode = path.index("om_ieee80211_beacon_prepare_v89_wire")
        flush_desc = path.index("ieee80211_beacon_flush_param", encode)
        flush_skb = path.index("flush_dcache_range", flush_desc)
        barrier = path.index("dma_wmb()", flush_skb)
        publish = path.index("ioctl->ioctl_command = IOCTL_DEV_BEACON_START", barrier)
        self.assertLess(host_preflight, encode)
        self.assertLess(encode, flush_desc)
        self.assertLess(flush_desc, flush_skb)
        self.assertLess(flush_skb, barrier)
        self.assertLess(barrier, publish)
        self.assertIn("bc_args->bc_ie_head = v89_wire ? beacon_head_wire", path)

    def test_mailbox_publish_has_final_dma_and_cpu_barriers(self) -> None:
        start = self.hostlink.index("published_ioctl =")
        end = self.hostlink.index('desc = "waiting for MuC dequeue"', start)
        publish = self.hostlink[start:end]
        self.assertLess(publish.index("dma_wmb()"), publish.index("WRITE_ONCE(*mbox, published_ioctl)"))
        self.assertLess(publish.index("WRITE_ONCE(*mbox, published_ioctl)"), publish.index("\n\twmb();"))
        self.assertLess(publish.index("\n\twmb();"), publish.index("qdrv_mac_interrupt_muc"))

    def test_diagnostics_expose_cpu_phys_and_wire_without_secrets(self) -> None:
        marker = self.qdrv[self.qdrv.index('OMQDRVBC stage=v89-wire-pass'):]
        for token in (
            "head_cpu=%px", "head_phys=%#lx", "head_wire=%#x",
            "buf_cpu=%px", "buf_phys=%#lx", "buf_wire=%#x",
            "next_cpu=%px", "next_phys=%#lx", "next_wire=%#x",
        ):
            self.assertIn(token, marker)

    def test_lifetime_profile_restores_only_oem_radio_board_values(self) -> None:
        for token in (
            "wifi_hw=7 rfic=4 calstate=3",
            "ext_lna_gain=12 ext_lna_bypass_gain=-5",
            "tx_power_cal=0 min_tx_power=7 max_tx_power=21",
            "board-radio-readback-$parameter",
            "Current RFIC Chip ID --[[:space:]]*4",
            "bb_init: FEM 0x7",
            "unsupported-fem",
        ):
            self.assertIn(token, self.start)
        preflight = self.start[self.start.index("Q3_RADIO5_BEACON_PREFLIGHT=1"):self.start.index("beacon_lifetime_value=")]
        self.assertNotIn("board_radio_oem_profile=1", preflight)
        lifetime = self.start[self.start.index("Q3_RADIO5_BEACON_LIFETIME=1"):self.start.index("psk=")]
        self.assertIn("board_radio_oem_profile=1", lifetime)

    def test_board_radio_probe_is_read_only(self) -> None:
        for token in ("wifi_hw", "rfic", "calstate", "get_rfchipid", "get_rfchip_verid", "Current RFIC Chip ID"):
            self.assertIn(token, self.board_probe)
        for forbidden in (">/sys", "tee /sys", "iwpriv-qtn wifi0 mode", "iwconfig-qtn wifi0 channel"):
            self.assertNotIn(forbidden, self.board_probe)


if __name__ == "__main__":
    unittest.main(verbosity=2)
