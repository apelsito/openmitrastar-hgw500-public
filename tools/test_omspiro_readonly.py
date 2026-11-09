#!/usr/bin/env python3
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/omspiro/omspiro.c"


class OmSpiReadOnlyTest(unittest.TestCase):
    def setUp(self) -> None:
        self.text = SOURCE.read_text(encoding="utf-8")

    def test_fixed_hgw_only_window(self) -> None:
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.text)
        self.assertIn("#define OMSPIRO_PHYS_BASE 0x90000000UL", self.text)
        self.assertIn("#define OMSPIRO_SIZE      0x01000000UL", self.text)
        self.assertNotIn("module_param", self.text)

    def test_read_only_fops(self) -> None:
        body = re.search(
            r"static const struct file_operations omspiro_fops = \{(.*?)\n\};",
            self.text,
            re.S,
        )
        self.assertIsNotNone(body)
        fops = body.group(1)
        self.assertIn(".read = omspiro_read", fops)
        for forbidden in (".write", ".unlocked_ioctl", ".compat_ioctl", ".mmap"):
            self.assertNotIn(forbidden, fops)
        self.assertIn("file->f_mode & FMODE_WRITE", self.text)
        self.assertIn(".mode = 0400", self.text)

    def test_bounds_and_bounce_buffer(self) -> None:
        self.assertIn("pos >= OMSPIRO_SIZE", self.text)
        self.assertIn("count > OMSPIRO_SIZE - pos", self.text)
        self.assertIn("memcpy_fromio", self.text)
        self.assertIn("copy_to_user", self.text)
        self.assertNotIn("copy_from_user", self.text)


if __name__ == "__main__":
    unittest.main()
