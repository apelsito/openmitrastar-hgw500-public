#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import random
import struct
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PARSER = ROOT / "tools" / "parse_topaz_physical_flash.py"
LAYOUT = (
    (0, "uboot", 0x000000, 0x020000),
    (1, "uboot_env", 0x020000, 0x010000),
    (2, "uboot_env_bak", 0x030000, 0x010000),
    (3, "linux_safety", 0x040000, 0x7A0000),
    (4, "linux_live", 0x7E0000, 0x7A0000),
    (5, "data", 0xF80000, 0x080000),
)


class TopazPhysicalParserTest(unittest.TestCase):
    def test_complete_streaming_round_trip(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            capture = Path(tmp) / "capture"
            capture.mkdir()
            chunk_bytes = 0x4000
            session = {
                "read_only": True,
                "mtd6_excluded": True,
                "physical_flash_size": 0x1000000,
                "chunk_bytes": chunk_bytes,
                "partitions": [
                    {"index": i, "name": n, "offset": o, "size": s}
                    for i, n, o, s in LAYOUT
                ],
            }
            (capture / "capture-session.json").write_text(json.dumps(session), encoding="utf-8")
            originals: dict[int, bytes] = {}
            rng = random.Random(500)
            for index, name, offset, size in LAYOUT:
                data = rng.randbytes(size)
                originals[index] = data
                log = capture / f"mtd{index}-{name}.uart.log"
                with log.open("w", encoding="utf-8", newline="\n") as stream:
                    for start in range(0, size, chunk_bytes):
                        block = data[start : start + chunk_bytes]
                        stream.write(
                            f"spi_flash read 0x{offset + start:08x} 0x83000000 0x{len(block):08x}\n"
                        )
                        stream.write(f"ret_size={len(block)}\ntopaz> md.l 0x83000000 0x{len(block) // 4:x}\n")
                        for row in range(0, len(block), 16):
                            words = struct.unpack("<4I", block[row : row + 16])
                            stream.write(
                                f"{0x83000000 + row:08x}: "
                                + " ".join(f"{word:08x}" for word in words)
                                + "    ASCII\n"
                            )
                        stream.write("topaz>\n")

            result = subprocess.run(
                [sys.executable, str(PARSER), "--capture-dir", str(capture)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            output = capture / "reconstructed"
            combined = bytearray()
            for index, _, _, _ in LAYOUT:
                reconstructed = (output / f"hgw500_mtdblock{index}.bin").read_bytes()
                self.assertEqual(reconstructed, originals[index])
                combined.extend(originals[index])
            physical = output / "hgw500_physical_16m_current_unit.bin"
            self.assertEqual(physical.read_bytes(), combined)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertFalse(manifest["mtd6_included"])
            self.assertEqual(manifest["physical_image"]["size"], 0x1000000)
            self.assertEqual(
                manifest["physical_image"]["sha256"], hashlib.sha256(combined).hexdigest()
            )

    def test_truncated_chunk_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            capture = Path(tmp)
            session = {
                "read_only": True,
                "mtd6_excluded": True,
                "physical_flash_size": 0x1000000,
                "chunk_bytes": 0x4000,
                "partitions": [
                    {"index": i, "name": n, "offset": o, "size": s}
                    for i, n, o, s in LAYOUT
                ],
            }
            (capture / "capture-session.json").write_text(json.dumps(session), encoding="utf-8")
            (capture / "mtd0-uboot.uart.log").write_text(
                "83000000: 00000000 00000000 00000000 00000000\n", encoding="utf-8"
            )
            result = subprocess.run(
                [sys.executable, str(PARSER), "--capture-dir", str(capture)],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("reconstructed 0 bytes, expected 131072", result.stderr)

    def test_progress_skips_failed_chunk_and_accepts_smaller_resume(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            capture = Path(tmp)
            session = {
                "read_only": True,
                "mtd6_excluded": True,
                "physical_flash_size": 0x1000000,
                "chunk_bytes": 0x4000,
                "partitions": [
                    {"index": i, "name": n, "offset": o, "size": s}
                    for i, n, o, s in LAYOUT
                ],
            }
            (capture / "capture-session.json").write_text(json.dumps(session), encoding="utf-8")
            log = capture / "mtd0-uboot.uart.log"
            with log.open("w", encoding="utf-8") as stream:
                stream.write("spi_flash read 0x00000000 0x83000000 0x00004000\n")
                stream.write("83000000: 00000000 00000000 00000000 00000000\n")
                for offset in (0, 0x1000):
                    stream.write(f"spi_flash read 0x{offset:08x} 0x83000000 0x00001000\n")
                    for row in range(0, 0x1000, 16):
                        stream.write(
                            f"{0x83000000 + row:08x}: 01020304 05060708 11121314 15161718\n"
                        )
            result = subprocess.run(
                [sys.executable, str(PARSER), "--capture-dir", str(capture), "--progress-json"],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            progress = json.loads(result.stdout)
            self.assertEqual(progress["mtd0"]["contiguous_bytes"], 0x2000)
            self.assertEqual(progress["mtd0"]["next_flash_offset"], 0x2000)


if __name__ == "__main__":
    unittest.main()
