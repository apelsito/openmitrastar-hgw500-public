#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/radiohw-intx-socmask-20260818-042500-RAM-ONLY-NO-FLASH"
sys.path.insert(0, str(ROOT / "tools"))
from make_spi_slot_image import validate_candidate


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class LegacyIntxArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))

    def test_artifact_hashes_and_webformat(self) -> None:
        for relative, spec in self.manifest["artifacts"].items():
            path = BUNDLE / relative
            self.assertEqual(path.stat().st_size, spec["bytes"])
            self.assertEqual(sha256(path), spec["sha256"])
        info = validate_candidate(
            (BUNDLE / "linux510-radiohw-intx-socmask-webformat.bin").read_bytes()
        )
        self.assertTrue(info["hcrc_ok"])
        self.assertTrue(info["dcrc_ok"])
        self.assertEqual(info["arch"], "0x13")
        self.assertEqual(info["load"], "0x8493a000")
        self.assertEqual(info["entry"], "0x849b8000")

    def test_oem_rmw_and_readback_are_exact(self) -> None:
        source = (BUNDLE / "evidence/pcie-qtn-topaz.c").read_text(encoding="utf-8")
        self.assertIn("#define TOPAZ_SYSCTL_PCIE_INT_MASK\t0x0c0", source)
        self.assertIn("#define TOPAZ_PCIE_LEGACY_INTX_EN\tBIT(11)", source)
        self.assertIn("before = readl(pcie->sysctl + TOPAZ_SYSCTL_PCIE_INT_MASK);", source)
        self.assertIn("writel(before | TOPAZ_PCIE_LEGACY_INTX_EN,", source)
        self.assertIn("after = readl(pcie->sysctl + TOPAZ_SYSCTL_PCIE_INT_MASK);", source)
        self.assertIn("legacy INTx mask before=%08x after=%08x bit11=%u", source)
        for forbidden in ("ATU_VIEWPORT", "ATU_CR1", "ATU_CR2", "0x900", "0x904", "0x908"):
            self.assertNotIn(forbidden, source)

    def test_ebusy_order_is_not_reverted(self) -> None:
        source = (BUNDLE / "evidence/pcie-qtn-topaz.c").read_text(encoding="utf-8")
        irq = source.index("irq = platform_get_irq")
        alloc = source.index("bridge = devm_pci_alloc_host_bridge")
        intx = source.index("ret = topaz_pcie_enable_legacy_intx")
        probe = source.index("ret = pci_host_probe")
        self.assertLess(irq, alloc)
        self.assertLess(intx, probe)

    def test_arc_disassembly_contains_exact_register_operation(self) -> None:
        disasm = (BUNDLE / "evidence/topaz_pcie_probe.disasm.txt").read_text(encoding="utf-8")
        self.assertIn("<platform_get_irq>", disasm)
        self.assertIn("<devm_pci_alloc_host_bridge>", disasm)
        self.assertIn("mov_s\tr1,0xc0", disasm)
        self.assertIn("bset\tr3,r2,0xb", disasm)
        self.assertIn("and\tr16,r3,0x800", disasm)
        self.assertIn("<pci_host_probe>", disasm)
        self.assertLess(disasm.index("<platform_get_irq>"), disasm.index("<devm_pci_alloc_host_bridge>"))

    def test_bundle_is_ram_only(self) -> None:
        self.assertEqual(self.manifest["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(self.manifest["candidate_eligible"])
        self.assertFalse(self.manifest["change"]["iatu_modified"])
        self.assertFalse(self.manifest["safety"]["boot_performed"])
        self.assertFalse(self.manifest["safety"]["flash_supported"])

    def test_compatible_realtek_bundle_is_pinned_to_this_kernel(self) -> None:
        spec = self.manifest["compatible_realtek_bundle"]
        bundle = ROOT / spec["path"]
        manifest_path = bundle / "manifest.json"
        self.assertEqual(sha256(manifest_path), spec["manifest_sha256"])
        realtek = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(realtek["base_ram_image"]["sha256"], spec["base_ram_image_sha256"])
        self.assertEqual(realtek["base_vmlinux"]["sha256"], spec["base_vmlinux_sha256"])
        artifacts = {item["path"]: item["sha256"] for item in realtek["artifacts"]}
        self.assertEqual(artifacts["modules/rtl_pci.ko"], spec["rtl_pci_sha256"])
        self.assertEqual(artifacts["modules/rtl8192ee.ko"], spec["rtl8192ee_sha256"])


if __name__ == "__main__":
    unittest.main()
