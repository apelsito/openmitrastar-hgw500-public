#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/realtek-intx-deferred-v5-final-20260818-061000-RAM-ONLY-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DeferredV5Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((BUNDLE / "deferred-manifest.json").read_text(encoding="utf-8"))
        cls.source = (BUNDLE / "evidence-v5/pci.c").read_text(encoding="utf-8")

    def test_hashes(self) -> None:
        self.assertEqual(sha256(BUNDLE / "manifest.json"), self.manifest["base_manifest_sha256"])
        self.assertEqual(sha256(BUNDLE / "modules/rtl_pci.ko"), self.manifest["rtl_pci_sha256"])
        self.assertEqual(sha256(BUNDLE / "modules/rtl8192ee.ko"), self.manifest["rtl8192ee_sha256"])
        self.assertEqual(sha256(BUNDLE / "kernel/linux510-radiohw-intx-irqchip-v2-webformat.bin"), self.manifest["kernel_sha256"])

    def test_managed_and_shared_returns_are_distinct(self) -> None:
        handler = self.source[self.source.index("static irqreturn_t _rtl_pci_interrupt"):self.source.index("static void _rtl_pci_irq_tasklet")]
        managed = handler[handler.index("if (rtlpci->irq_line_lifecycle_managed)"):]
        self.assertLess(managed.index("return IRQ_HANDLED;"), managed.index("return IRQ_NONE;"))
        self.assertIn("reason=managed-deferred", managed)
        self.assertIn("reason=shared-not-ours", managed)

    def test_disassembly_and_markers(self) -> None:
        markers = (BUNDLE / "evidence-v5/v5.markers.txt").read_text(encoding="utf-8")
        disasm = (BUNDLE / "evidence-v5/rtl_pci_interrupt.disasm.txt").read_text(encoding="utf-8")
        self.assertIn("managed-deferred", markers)
        self.assertIn("shared-not-ours", markers)
        self.assertIn("mov_s\tr0,0x1", disasm)
        self.assertIn("R_ARC_32_ME\tprintk", disasm)

    def test_safety(self) -> None:
        self.assertEqual(self.manifest["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(self.manifest["candidate_eligible"])
        self.assertFalse(self.manifest["runtime"]["v5_booted"])
        self.assertFalse(self.manifest["behavior"]["lifecycle_changed"])


if __name__ == "__main__":
    unittest.main()
