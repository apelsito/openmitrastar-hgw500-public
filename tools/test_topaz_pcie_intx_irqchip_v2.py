#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/radiohw-intx-irqchip-v2-20260818-044000-RAM-ONLY-NO-FLASH"
sys.path.insert(0, str(ROOT / "tools"))
from make_spi_slot_image import validate_candidate


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class IntxIrqchipV2Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))

    def test_artifacts_and_webformat(self) -> None:
        for relative, spec in self.manifest["artifacts"].items():
            path = BUNDLE / relative
            self.assertEqual(path.stat().st_size, spec["bytes"])
            self.assertEqual(sha256(path), spec["sha256"])
        info = validate_candidate(
            (BUNDLE / "linux510-radiohw-intx-irqchip-v2-webformat.bin").read_bytes()
        )
        self.assertTrue(info["hcrc_ok"])
        self.assertTrue(info["dcrc_ok"])
        self.assertEqual(info["arch"], "0x13")

    def test_host_probe_no_longer_owns_soc_intx_gate(self) -> None:
        source = (BUNDLE / "evidence/pcie-qtn-topaz.c").read_text(encoding="utf-8")
        for forbidden in ("TOPAZ_SYSCTL_PCIE_INT_MASK", "TOPAZ_PCIE_LEGACY_INTX_EN", "enable_legacy_intx"):
            self.assertNotIn(forbidden, source)
        self.assertLess(source.index("irq = platform_get_irq"), source.index("bridge = devm_pci_alloc_host_bridge"))

    def test_irqchip_masks_only_hwirq28_and_preserves_lhost(self) -> None:
        source = (BUNDLE / "evidence/intc-compact.c").read_text(encoding="utf-8")
        self.assertIn("#define TOPAZ_SYSCTL_LHOST_INT_EN\t0x4c", source)
        self.assertIn("#define TOPAZ_SYSCTL_PCIE_INT_MASK\t0xc0", source)
        self.assertIn("#define TOPAZ_IRQ_PCIE\t\t\t28", source)
        self.assertIn("hwirq != TOPAZ_IRQ_PCIE", source)
        self.assertIn("before | TOPAZ_PCIE_LEGACY_INTX_EN", source)
        self.assertIn("before & ~TOPAZ_PCIE_LEGACY_INTX_EN", source)
        mask = source[source.index("static void arc_irq_mask"):source.index("static void arc_irq_unmask")]
        unmask = source[source.index("static void arc_irq_unmask"):source.index("static struct irq_chip")]
        self.assertLess(mask.index("topaz_pcie_legacy_intx_gate"), mask.index("read_aux_reg"))
        self.assertLess(unmask.index("topaz_direct_irq_gate"), unmask.index("topaz_pcie_legacy_intx_gate"))

    def test_disassembly_proves_gate_and_call_order(self) -> None:
        gate = (BUNDLE / "evidence/topaz_pcie_legacy_intx_gate.disasm.txt").read_text(encoding="utf-8")
        mask = (BUNDLE / "evidence/arc_irq_mask.disasm.txt").read_text(encoding="utf-8")
        unmask = (BUNDLE / "evidence/arc_irq_unmask.disasm.txt").read_text(encoding="utf-8")
        host = (BUNDLE / "evidence/topaz_pcie_probe.disasm.txt").read_text(encoding="utf-8")
        self.assertIn("mov_s\tr3,0xc0", gate)
        self.assertIn("bset\tr3,r4,0xb", gate)
        self.assertIn("bclr\tr3,r4,0xb", gate)
        self.assertLess(mask.index("<topaz_pcie_legacy_intx_gate>"), mask.index("<topaz_direct_irq_gate>"))
        self.assertLess(unmask.index("<topaz_direct_irq_gate>"), unmask.index("<topaz_pcie_legacy_intx_gate>"))
        self.assertNotIn("topaz_pcie_legacy_intx_gate", host)

    def test_realtek_bundle_is_pinned_to_v2(self) -> None:
        spec = self.manifest["compatible_realtek_bundle"]
        bundle = ROOT / spec["path"]
        manifest_path = bundle / "manifest.json"
        self.assertEqual(sha256(manifest_path), spec["manifest_sha256"])
        realtek = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(realtek["base_ram_image"]["sha256"], spec["base_ram_image_sha256"])
        self.assertEqual(realtek["base_vmlinux"]["sha256"], spec["base_vmlinux_sha256"])

    def test_safety_boundary(self) -> None:
        self.assertEqual(self.manifest["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(self.manifest["candidate_eligible"])
        self.assertFalse(self.manifest["change"]["iatu_modified"])
        self.assertFalse(self.manifest["runtime"]["booted_on_hardware"])
        self.assertFalse(self.manifest["safety"]["flash_supported"])


if __name__ == "__main__":
    unittest.main()
