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
import compose_f165_squashfs_product as f165  # noqa: E402


class F165SquashfsExactMtdTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.web = f165.OUT / f"{f165.BASE}.webformat.bin"
        cls.data = cls.web.read_bytes()
        cls.manifest = json.loads((f165.OUT / "manifest.json").read_text(encoding="ascii"))

    def test_bootbase_header_and_split_payload(self) -> None:
        values = list(struct.unpack(">7I4B32s", self.data[:64]))
        header = bytearray(self.data[:64])
        header[4:8] = b"\0" * 4
        self.assertEqual(0x27051956, values[0])
        self.assertEqual(zlib.crc32(header) & 0xFFFFFFFF, values[1])
        self.assertEqual(zlib.crc32(self.data[0x2000:]) & 0xFFFFFFFF, values[6])
        self.assertEqual(0x13, values[8])
        self.assertEqual(b"hsqs", self.data[0x180000:0x180004])
        decoder = lzma.LZMADecompressor(format=lzma.FORMAT_ALONE)
        decoder.decompress(self.data[0x2000:])
        self.assertTrue(decoder.eof)

    def test_exact_mtd_source_contract(self) -> None:
        source = (
            ROOT / "work/kernel-port/linux-5.10/drivers/mtd/maps/physmap-core.c"
        ).read_text(encoding="utf-8")
        self.assertIn("info->maps[i].size = resource_size(res);", source)
        self.assertEqual("PASS", self.manifest["contracts"]["bootbase"])
        self.assertTrue(self.manifest["candidate_eligible"])
        self.assertTrue(self.manifest["flash_supported"])
        self.assertEqual("0x90960000+0x00620000, Linux root=31:3", self.manifest["layout"]["mtd_mapping"].split("read-only mtd-rom ", 1)[1])

    def test_rootfs_has_product_headroom(self) -> None:
        layout = self.manifest["layout"]
        self.assertEqual(0x620000, layout["rootfs_window_bytes"])
        self.assertGreater(layout["rootfs_headroom_bytes"], 3_000_000)
        self.assertLess(layout["candidate_bytes"], layout["slot_bytes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
