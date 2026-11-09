#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/platform/ruby/board_compat.c"
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-direct-compact-tqe256-sramgate-20260820"


class BoardCompatSramGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_requested_parameter_is_not_the_active_backend(self) -> None:
        self.assertIn("static bool allow_dram_sram_fallback;", self.source)
        self.assertIn("static bool dram_sram_fallback_active;", self.source)
        alloc = self.source[self.source.index("void *heap_sram_alloc") : self.source.index("EXPORT_SYMBOL(heap_sram_alloc)")]
        free = self.source[self.source.index("void heap_sram_free") : self.source.index("EXPORT_SYMBOL(heap_sram_free)")]
        self.assertIn("if (!dram_sram_fallback_active)", alloc)
        self.assertIn("if (dram_sram_fallback_active)", free)

    def test_target_gate_precedes_no_probe_fast_path(self) -> None:
        init = self.source[self.source.index("static int __init board_compat_init") :]
        target = init.index('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")')
        activation = init.index("dram_sram_fallback_active =")
        no_probe = init.index("if (probe_count == 0)")
        self.assertLess(target, activation)
        self.assertLess(activation, no_probe)
        self.assertIn("allow_dram_sram_fallback && !target_ok", init)

    def test_non_v89_profile_refuses_requested_fallback(self) -> None:
        self.assertIn("reason=profile-mismatch", self.source)
        self.assertIn("reason=target-mismatch", self.source)

    def test_artifact_is_clean_and_hash_pinned(self) -> None:
        module = ARTIFACT / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/platform/ruby/board_compat.ko"
        self.assertTrue(module.is_file())
        manifest = (ARTIFACT / "module-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn("platform/ruby/board_compat.ko\t0969752af8257a03", manifest)
        self.assertEqual((ARTIFACT / "depmod-unresolved.log").read_bytes(), b"")


if __name__ == "__main__":
    unittest.main(verbosity=2)
