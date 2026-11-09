#!/usr/bin/env python3
from __future__ import annotations

import json
import lzma
import struct
import sys
import unittest
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import compose_f164_squashfs_product as f164  # noqa: E402


class F164SquashfsProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.web = f164.OUT / f"{f164.BASE}.webformat.bin"
        cls.manifest = json.loads((f164.OUT / "manifest.json").read_text(encoding="ascii"))
        cls.data = cls.web.read_bytes()

    def test_bootbase_header_and_layout(self) -> None:
        values = list(struct.unpack(">7I4B32s", self.data[:64]))
        header = bytearray(self.data[:64])
        header[4:8] = b"\0" * 4
        self.assertEqual(0x27051956, values[0])
        self.assertEqual(zlib.crc32(header) & 0xFFFFFFFF, values[1])
        self.assertEqual(len(self.data) - 0x2000, values[3])
        self.assertEqual(zlib.crc32(self.data[0x2000:]) & 0xFFFFFFFF, values[6])
        self.assertEqual(0x13, values[8])
        self.assertEqual(3, values[10])
        self.assertEqual(b"hsqs", self.data[f164.ROOTFS_OFFSET:f164.ROOTFS_OFFSET + 4])

    def test_kernel_stream_and_rootfs_fit(self) -> None:
        payload = self.data[0x2000:]
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        raw = decoder.decompress(payload)
        self.assertTrue(decoder.eof)
        used = len(payload) - len(decoder.unused_data)
        gap = f164.ROOTFS_OFFSET - 0x2000 - used
        self.assertGreaterEqual(gap, 0)
        self.assertEqual(b"\0" * gap, decoder.unused_data[:gap])
        self.assertEqual(b"hsqs", decoder.unused_data[gap:gap + 4])
        self.assertEqual(
            raw,
            (f164.OUT / f"{f164.BASE}.kernel.raw.bin").read_bytes(),
        )
        self.assertLess(len(self.data), f164.f71.SLOT_BYTES)

    def test_contracts_and_kernel_configuration(self) -> None:
        self.assertEqual("PASS", self.manifest["contracts"]["bootbase"])
        self.assertTrue(self.manifest["contracts"]["kernel_before_rootfs"])
        config = (f164.OUT / f"{f164.BASE}.config").read_text(encoding="ascii")
        self.assertIn('CONFIG_INITRAMFS_SOURCE=""', config)
        self.assertIn("CONFIG_SQUASHFS=y", config)
        self.assertIn("CONFIG_SQUASHFS_XZ=y", config)
        dtb = (f164.OUT / f"{f164.BASE}.dtb").read_bytes()
        self.assertIn(b"root=31:3", dtb)
        self.assertIn(b"rootfs_live", dtb)


if __name__ == "__main__":
    unittest.main(verbosity=2)
