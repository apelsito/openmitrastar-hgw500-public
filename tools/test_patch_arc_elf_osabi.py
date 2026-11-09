#!/usr/bin/env python3
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/patch_arc_elf_osabi.py"
LOADER = ROOT / "outputs/kernel-port/qcsapi-5g-ap36-bw80-ram-only-20260819/runtime/lib/ld-uClibc-0.9.29.so"


class ArcElfOsabiPatchTests(unittest.TestCase):
    def test_only_eflags_change(self):
        with tempfile.TemporaryDirectory() as temporary:
            output = Path(temporary) / "loader.so"
            result = subprocess.run([sys.executable, str(SCRIPT), str(LOADER), str(output)],
                                    cwd=ROOT, text=True, capture_output=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            before, after = LOADER.read_bytes(), output.read_bytes()
            self.assertEqual(len(before), len(after))
            self.assertEqual(before[:36], after[:36])
            self.assertEqual(before[40:], after[40:])
            self.assertEqual(struct.unpack_from("<I", before, 36)[0], 0x3)
            self.assertEqual(struct.unpack_from("<I", after, 36)[0], 0x403)

    def test_tool_is_narrow(self):
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("EF_ARC_OSABI_MSK", text)
        self.assertIn("EM_ARC_COMPACT", text)
        self.assertNotIn("flash", text.lower())


if __name__ == "__main__":
    unittest.main()
