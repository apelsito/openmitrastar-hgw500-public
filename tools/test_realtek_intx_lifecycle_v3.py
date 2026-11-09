#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/realtek-intx-lifecycle-v3-final-20260818-050500-RAM-ONLY-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LifecycleV3Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.lifecycle = json.loads((BUNDLE / "lifecycle-manifest.json").read_text(encoding="utf-8"))
        cls.source = (BUNDLE / "evidence-v3/pci.c").read_text(encoding="utf-8")
        cls.header = (BUNDLE / "evidence-v3/pci.h").read_text(encoding="utf-8")

    def test_hashes_and_topaz_scope(self) -> None:
        self.assertEqual(sha256(BUNDLE / "manifest.json"), self.lifecycle["base_bundle_manifest_sha256"])
        self.assertEqual(sha256(BUNDLE / "modules/rtl_pci.ko"), self.lifecycle["rtl_pci_sha256"])
        self.assertEqual(sha256(BUNDLE / "modules/rtl8192ee.ko"), self.lifecycle["rtl8192ee_sha256"])
        self.assertEqual(sha256(BUNDLE / "kernel/linux510-radiohw-intx-irqchip-v2-webformat.bin"), self.lifecycle["kernel_image_sha256"])
        for token in (
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            "pdev->irq == 28",
            "pdev->vendor == PCI_VENDOR_ID_REALTEK",
            "pdev->device == RTL_PCI_8192EE_DID",
        ):
            self.assertIn(token, self.source)
        self.assertIn("bool irq_line_lifecycle_managed;", self.header)

    def test_handler_and_lifecycle_order(self) -> None:
        self.assertIn("return IRQ_NONE;", self.source)
        request = self.source[self.source.index("static int rtl_pci_intr_mode_legacy"):self.source.index("static int rtl_pci_intr_mode_decide")]
        self.assertLess(request.index("request_irq"), request.index('rtl_pci_irq_line_hold(hw, "request-legacy")'))
        start = self.source[self.source.index("static int rtl_pci_start"):self.source.index("static void rtl_pci_stop")]
        self.assertLess(start.index("hw_init(hw)"), start.index("rtl_init_rx_config(hw)"))
        self.assertLess(start.index("rtl_init_rx_config(hw)"), start.index("set_hal_start(rtlhal)"))
        self.assertLess(start.index("set_hal_start(rtlhal)"), start.index('rtl_pci_irq_line_release(hw, "start-ready")'))
        stop = self.source[self.source.index("static void rtl_pci_stop"):self.source.index("static bool _rtl_pci_find_adapter")]
        self.assertLess(stop.index('rtl_pci_irq_line_hold(hw, "stop")'), stop.index("disable_interrupt(hw)"))
        self.assertLess(stop.index("disable_interrupt(hw)"), stop.index("hw_disable(hw)"))

    def test_fail_disconnect_and_pm_balance(self) -> None:
        self.assertIn("goto fail_irq;", self.source)
        self.assertIn("ieee80211_unregister_hw(hw);", self.source[self.source.index("fail_irq:"):])
        disconnect = self.source[self.source.index("void rtl_pci_disconnect"):self.source.index("EXPORT_SYMBOL(rtl_pci_disconnect)")]
        self.assertLess(disconnect.index("disable_interrupt(hw)"), disconnect.index('rtl_pci_irq_line_release(hw, "disconnect-balance")'))
        self.assertLess(
            disconnect.index('rtl_pci_irq_line_release(hw, "disconnect-balance")'),
            disconnect.index("free_irq(rtlpci->pdev->irq"),
        )
        core = (BUNDLE / "evidence-v3/core.c").read_text(encoding="utf-8")
        self.assertLess(core.index("rtl_op_stop(hw);"), core.index("static int rtl_op_resume"))
        resume = core[core.index("static int rtl_op_resume"):]
        self.assertLess(resume.index("now - rtlhal->last_suspend_sec < 5"), resume.index("rtl_op_start(hw);"))
        self.assertIn('rtl_pci_irq_line_hold(hw, "suspend")', self.source)
        self.assertIn("irq-line-resume-held", self.source)

    def test_disassembly_and_safety(self) -> None:
        hold = (BUNDLE / "evidence-v3/rtl_pci_irq_line_hold.disasm.txt").read_text(encoding="utf-8")
        release = (BUNDLE / "evidence-v3/rtl_pci_irq_line_release.disasm.txt").read_text(encoding="utf-8")
        disconnect = (BUNDLE / "evidence-v3/rtl_pci_disconnect.disasm.txt").read_text(encoding="utf-8")
        self.assertIn("disable_irq", hold)
        self.assertIn("enable_irq", release)
        self.assertLess(disconnect.index(".text+0x608"), disconnect.index("free_irq"))
        self.assertEqual(self.lifecycle["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(self.lifecycle["runtime"]["v3_booted"])


if __name__ == "__main__":
    unittest.main()
