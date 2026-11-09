#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/realtek-tx-doorbell/20260818-034233-RAM-ONLY-NO-FLASH"
MANIFEST = BUNDLE / "instrumentation-manifest.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TxDoorbellBundleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def test_upload_modules_match_manifest(self) -> None:
        for relative, expected in self.manifest["upload_artifacts"].items():
            path = BUNDLE / relative
            self.assertTrue(path.is_file(), path)
            self.assertEqual(path.stat().st_size, expected["bytes"])
            self.assertEqual(sha256(path), expected["sha256"])

    def test_arc_and_vermagic_gates(self) -> None:
        for stem in ("rtl_pci", "rtl8192ee"):
            elf = (BUNDLE / f"evidence/{stem}.readelf.txt").read_text(encoding="utf-8")
            vermagic = (BUNDLE / f"evidence/{stem}.vermagic.txt").read_text(encoding="utf-8")
            self.assertIn("Class:                             ELF32", elf)
            self.assertIn("2's complement, little endian", elf)
            self.assertIn("Machine:                           ARCompact", elf)
            self.assertIn("ARC700, v4 ABI", elf)
            self.assertIn("5.10.260-openmitrastar-radiohw", vermagic)

    def test_all_required_markers_are_embedded(self) -> None:
        pci = (BUNDLE / "evidence/rtl_pci_tx.markers.txt").read_text(encoding="utf-8")
        chip = (BUNDLE / "evidence/rtl8192ee_tx.markers.txt").read_text(encoding="utf-8")
        for marker in (
            "pci-tx-desc-filled",
            "pci-tx-bd-filled",
            "pci-tx-doorbell-done",
            "pci-tx-before-poll",
            "pci-tx-after-poll",
        ):
            self.assertIn(marker, pci)
        for marker in (
            "tx-doorbell-pre",
            "tx-doorbell-post",
            "tx-poll-enter",
            "tx-poll-exit",
        ):
            self.assertIn(marker, chip)

    def test_instrumented_functions_have_arc_disassembly(self) -> None:
        checks = {
            "evidence/rtl_pci_tx.disasm.txt": "<rtl_pci_tx>",
            "evidence/rtl92ee_set_desc.disasm.txt": "<rtl92ee_set_desc>",
            "evidence/rtl92ee_tx_polling.disasm.txt": "<rtl92ee_tx_polling>",
        }
        for relative, symbol in checks.items():
            text = (BUNDLE / relative).read_text(encoding="utf-8")
            self.assertIn(symbol, text)
            self.assertIn("R_ARC_32_ME\tprintk", text)

    def test_bundle_remains_ram_only(self) -> None:
        base = json.loads((BUNDLE / "manifest.json").read_text(encoding="utf-8"))
        self.assertEqual(base["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(base["candidate_eligible"])
        self.assertFalse(base["safety"]["flash_supported"])
        self.assertFalse(base["safety"]["persistent_writes_supported"])


if __name__ == "__main__":
    unittest.main()
