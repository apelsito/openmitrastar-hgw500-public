#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/realtek-intx-noautoen-v4-final-20260818-055500-RAM-ONLY-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class NoAutoenV4Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((BUNDLE / "noautoen-manifest.json").read_text(encoding="utf-8"))
        cls.source = (BUNDLE / "evidence-v4/pci.c").read_text(encoding="utf-8")

    def test_hashes_and_scope(self) -> None:
        self.assertEqual(sha256(BUNDLE / "manifest.json"), self.manifest["base_bundle_manifest_sha256"])
        self.assertEqual(sha256(BUNDLE / "modules/rtl_pci.ko"), self.manifest["rtl_pci_sha256"])
        self.assertEqual(sha256(BUNDLE / "modules/rtl8192ee.ko"), self.manifest["rtl8192ee_sha256"])
        self.assertEqual(sha256(BUNDLE / "kernel/linux510-radiohw-intx-irqchip-v2-webformat.bin"), self.manifest["kernel_image_sha256"])
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.source)
        self.assertIn("pdev->irq == 28", self.source)
        self.assertIn("pdev->device == RTL_PCI_8192EE_DID", self.source)

    def test_dedicated_noautoen_and_shared_fallback(self) -> None:
        legacy = self.source[self.source.index("static int rtl_pci_intr_mode_legacy"):self.source.index("static int rtl_pci_intr_mode_decide")]
        self.assertIn("unsigned long irqflags = IRQF_SHARED;", legacy)
        self.assertIn("irqflags = IRQF_NO_AUTOEN;", legacy)
        self.assertIn("request_irq", legacy)
        self.assertNotIn("IRQF_SHARED | IRQF_NO_AUTOEN", legacy)
        self.assertNotIn("rtl_pci_irq_line_hold", legacy)
        self.assertIn("irq_line_disabled = true;", legacy)
        manage = (BUNDLE / "evidence-v4/irq-manage.c").read_text(encoding="utf-8")
        self.assertIn("(irqflags & IRQF_SHARED) && (irqflags & IRQF_NO_AUTOEN)", manage)

    def test_msi_and_handler_gates(self) -> None:
        decide = self.source[self.source.index("static int rtl_pci_intr_mode_decide"):self.source.index("static void platform_enable_dma64")]
        self.assertLess(decide.index("irq_line_lifecycle_managed"), decide.index("msi_support"))
        self.assertIn("return rtl_pci_intr_mode_legacy(hw);", decide)
        msi = self.source[self.source.index("static int rtl_pci_intr_mode_msi"):self.source.index("static int rtl_pci_intr_mode_legacy")]
        self.assertIn("return -EOPNOTSUPP;", msi)
        handler = self.source[self.source.index("static irqreturn_t _rtl_pci_interrupt"):self.source.index("static void _rtl_pci_irq_tasklet")]
        self.assertIn("return IRQ_NONE;", handler)

    def test_disassembly_and_lifecycle_balance(self) -> None:
        legacy = (BUNDLE / "evidence-v4/rtl_pci_intr_mode_legacy.disasm.txt").read_text(encoding="utf-8")
        self.assertIn("mov.ne\tr14,0x1", legacy)
        self.assertIn("asl.ne\tr14,r14,0x13", legacy)
        self.assertIn("mov.eq\tr14,0x80", legacy)
        self.assertIn("request_threaded_irq", legacy)
        self.assertNotIn("disable_irq", legacy)
        start = self.source[self.source.index("static int rtl_pci_start"):self.source.index("static void rtl_pci_stop")]
        self.assertLess(start.index("set_hal_start(rtlhal)"), start.index('rtl_pci_irq_line_release(hw, "start-ready")'))
        disconnect = self.source[self.source.index("void rtl_pci_disconnect"):self.source.index("EXPORT_SYMBOL(rtl_pci_disconnect)")]
        self.assertLess(disconnect.index("disable_interrupt(hw)"), disconnect.index('rtl_pci_irq_line_release(hw, "disconnect-balance")'))
        self.assertLess(disconnect.index('rtl_pci_irq_line_release(hw, "disconnect-balance")'), disconnect.index("free_irq(rtlpci->pdev->irq"))

    def test_safety(self) -> None:
        self.assertEqual(self.manifest["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(self.manifest["candidate_eligible"])
        self.assertFalse(self.manifest["runtime"]["v4_booted"])


if __name__ == "__main__":
    unittest.main()
