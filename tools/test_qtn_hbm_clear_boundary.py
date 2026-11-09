#!/usr/bin/env python3
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HBM = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/hbm.c"


class HbmClearBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HBM.read_text(encoding="utf-8")

    def test_chunked_clear_is_target_profile_only(self):
        helper = self.source.index("static int omhbm_poison_range")
        profile = self.source.rfind("#ifdef OPENMITRASTAR_QDRV_V89_PAIR", 0, helper)
        profile_end = self.source.index("#endif", helper)
        self.assertGreaterEqual(profile, 0)
        self.assertGreater(profile_end, helper)
        self.assertIn("OMHBM_CLEAR_CHUNK_BYTES", self.source[profile:profile_end])

    def test_each_payload_and_metadata_range_is_named(self):
        init = self.source.index("static int topaz_hbm_init_payload_pools")
        block = self.source[init:init + 5000]
        for name, base, total in (
            ("emac-rx", "TOPAZ_HBM_BUF_EMAC_RX_BASE", "TOPAZ_HBM_BUF_EMAC_RX_TOTAL"),
            ("wmac-rx", "TOPAZ_HBM_BUF_WMAC_RX_BASE", "TOPAZ_HBM_BUF_WMAC_RX_TOTAL"),
            ("metadata", "TOPAZ_HBM_BUF_META_BASE", "TOPAZ_HBM_BUF_META_TOTAL"),
        ):
            self.assertRegex(
                block,
                re.compile(
                    rf'omhbm_poison_range\("{name}".*?{base}.*?{total}\)',
                    re.S,
                ),
            )

    def test_linux_boundary_and_overflow_fail_closed(self):
        helper = self.source.index("static int omhbm_poison_range")
        block = self.source[helper:helper + 3500]
        self.assertIn("RUBY_DRAM_BEGIN + CONFIG_ARC_KERNEL_MEM_BASE", block)
        self.assertIn("end < start", block)
        self.assertIn("end > linux_start", block)
        self.assertIn("return -ERANGE", block)
        self.assertIn("OMHBM stage=clear-refused", block)
        self.assertIn("BUILD_BUG_ON(TOPAZ_HBM_BUF_END > CONFIG_ARC_KERNEL_MEM_BASE)", self.source)

    def test_markers_distinguish_memset_from_cache_flush(self):
        for marker in (
            "OMHBM stage=clear-begin",
            "OMHBM stage=clear-chunk-begin",
            "OMHBM stage=clear-chunk-memset-done",
            "OMHBM stage=clear-chunk-cache-done",
            "OMHBM stage=clear-done",
        ):
            self.assertIn(marker, self.source)

    def test_cache_irq_off_window_is_bounded_and_scheduler_gets_a_gap(self):
        helper = self.source.index("static int omhbm_poison_range")
        block = self.source[helper:helper + 3500]
        self.assertIn("(4U * 1024U * 1024U)", self.source)
        self.assertIn("flush_and_inv_dcache_sizerange_safe(addr, len)", block)
        self.assertIn("cond_resched()", block)
        self.assertLess(
            block.index("flush_and_inv_dcache_sizerange_safe(addr, len)"),
            block.index("cond_resched()"),
        )


if __name__ == "__main__":
    unittest.main()
