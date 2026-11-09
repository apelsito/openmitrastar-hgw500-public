#!/usr/bin/env python3
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class QdrvV89BeaconWireLayoutTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.header = (ROOT / "work/sources/Quantenna-GPL/drivers/include/shared/qtn/beacon_ioctl.h").read_text(
            encoding="utf-8"
        )
        cls.desc = (ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_beacon_desc.c").read_text(
            encoding="utf-8"
        )
        cls.wlan = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c").read_text(encoding="utf-8")

    def test_shared_ie_layout_matches_oem_v89_wire_abi(self) -> None:
        expected = (
            "dma_addr_t\tbuf",
            "uint8_t *\tlhost_buf",
            "uint32_t\tsize",
            "uint32_t\tnext_muc_addr",
            "beacon_shared_ie_t *next",
        )
        positions = [self.header.index(token) for token in expected]
        self.assertEqual(positions, sorted(positions))

    def test_compile_time_offsets_pin_wire_prefix(self) -> None:
        for marker in (
            "sizeof(struct beacon_shared_ie_t) != 20",
            "offsetof(struct beacon_shared_ie_t, buf) != 0",
            "offsetof(struct beacon_shared_ie_t, lhost_buf) != 4",
            "offsetof(struct beacon_shared_ie_t, size) != 8",
            "offsetof(struct beacon_shared_ie_t, next_muc_addr) != 12",
            "offsetof(struct beacon_shared_ie_t, next) != 16",
        ):
            self.assertIn(marker, self.desc)

    def test_qdrv_logs_v89_wire_encoder_path(self) -> None:
        self.assertIn("OMQDRVBC stage=v89-wire-pass", self.wlan)
        self.assertIn("OMQDRVBC stage=v89-wire-fail", self.wlan)
        self.assertIn("bc_args->bc_ie_head = v89_wire ? beacon_head_wire", self.wlan)


if __name__ == "__main__":
    unittest.main(verbosity=2)
