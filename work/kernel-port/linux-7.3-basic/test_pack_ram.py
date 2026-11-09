"""Offline corruption and reconstruction checks against the retained exact ELF."""
import importlib.util
from pathlib import Path
import struct
import unittest

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("basic73_pack_ram", HERE / "pack_ram.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)
PROJECT = HERE.parents[2]
EVIDENCE = PROJECT / "outputs/rea/movistar-port-20261022T1327175411798Z"
ELF = EVIDENCE / "basic73-offline-v6/basic73.vmlinux"
TEMPLATE = PROJECT / "hgw500bna-qcv2-firmware-dump-verified/hgw500_mtdblock3.bin"
REFERENCE = EVIDENCE / "basic73-offline-v7-uncompressed/basic73-RAM-ONLY-NO-GO.ras.bin"

class PackageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.elf = ELF.read_bytes()
        cls.template = TEMPLATE.read_bytes()

    def test_exact_elf_reconstructs_selected_ram_artifact(self):
        image, details = m.package(self.elf, self.template)
        self.assertEqual(image, REFERENCE.read_bytes())
        self.assertEqual(details["compression"], 0)
        self.assertEqual(next(x for x in details["initramfs"] if x["name"] == "init")["sha256"], m.INIT_SHA)

    def test_kernel_and_template_mutation_rejected(self):
        for target in ["kernel", "template"]:
            with self.subTest(target=target):
                changed = bytearray(self.elf if target == "kernel" else self.template)
                changed[0x100] ^= 1
                with self.assertRaises(ValueError):
                    m.package(bytes(changed) if target == "kernel" else self.elf,
                              bytes(changed) if target == "template" else self.template)

    def test_wrong_entry_rejected_by_elf_parser(self):
        changed = bytearray(self.elf)
        struct.pack_into("<I", changed, 24, m.ENTRY + 8)
        with self.assertRaisesRegex(ValueError, "entry"):
            m.elf_raw(changed)

    def test_section_table_truncation_rejected(self):
        h = struct.unpack_from("<16sHHIIIIIHHHHHH", self.elf)
        with self.assertRaisesRegex(ValueError, "truncated"):
            m.elf_raw(self.elf[:h[6] + 40])

    def test_allocated_section_outside_ram_rejected(self):
        changed = bytearray(self.elf)
        h = struct.unpack_from("<16sHHIIIIIHHHHHH", changed)
        struct.pack_into("<I", changed, h[6] + 40 + 12, m.DDR_END)
        with self.assertRaisesRegex(ValueError, "outside RAM"):
            m.elf_raw(changed)

    def test_embedded_initramfs_corruption_rejected(self):
        changed = bytearray(self.elf)
        h = struct.unpack_from("<16sHHIIIIIHHHHHH", changed)
        # The exact target's second non-null section is .init.ramfs.
        ramfs = struct.unpack_from("<10I", changed, h[6] + 2 * 40)
        changed[ramfs[4]] ^= 1
        with self.assertRaises(Exception):
            m.elf_raw(changed)

if __name__ == "__main__":
    unittest.main()
