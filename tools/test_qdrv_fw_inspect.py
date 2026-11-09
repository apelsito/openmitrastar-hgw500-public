#!/usr/bin/env python3
"""Offline tests for qdrv_fw_inspect using local .62 and .89 firmware."""
from __future__ import annotations

import struct
import tarfile
import unittest
from pathlib import Path

from qdrv_fw_inspect import FirmwareFormatError, infer_cpu, inspect_firmware


ROOT = Path(__file__).resolve().parents[1]
FW89 = ROOT / "work/revival/rootfs/etc/firmware"
GPL62_TAR = ROOT / "work/sources/Quantenna-GPL/quantenna-bin-v37.4.0.62.1.tar"
GPL62_BASE = "./buildroot/target/device/Quantenna/Ruby/fw/topaz-bin/"


class QdrvFirmwareInspectorTests(unittest.TestCase):
    def test_all_local_89_firmware(self) -> None:
        expected = {
            "auc_driver.default.0.bin": ("auc", 9, 0),
            "auc_driver.nomu.0.bin": ("auc", 9, 0),
            "qtn_driver.qtn_ruby.0.bin": ("muc", 9, 0),
            "rdsp_driver.0.bin": ("dsp", 4, 28),
        }
        self.assertTrue(FW89.is_dir(), FW89)
        for name, (cpu, phnum, trailer) in expected.items():
            with self.subTest(name=name):
                path = FW89 / name
                report = inspect_firmware(path.read_bytes(), source=str(path), cpu=cpu)
                self.assertEqual(report.program_headers, phnum)
                self.assertEqual(report.trailer_size, trailer)
                self.assertEqual(len(report.sha256), 64)
                self.assertTrue(all(len(segment.payload_sha256) == 64 for segment in report.segments))

    def test_all_local_62_firmware_from_tar(self) -> None:
        expected = {
            "auc_driver.0.bin": ("auc", 8, 0),
            "qtn_driver.qtn_ruby.0.bin": ("muc", 8, 0),
            "rdsp_driver.0.bin": ("dsp", 3, 28),
        }
        self.assertTrue(GPL62_TAR.is_file(), GPL62_TAR)
        with tarfile.open(GPL62_TAR) as archive:
            for name, (cpu, phnum, trailer) in expected.items():
                with self.subTest(name=name):
                    extracted = archive.extractfile(GPL62_BASE + name)
                    self.assertIsNotNone(extracted)
                    report = inspect_firmware(
                        extracted.read(), source=f"{GPL62_TAR}!{name}", cpu=cpu
                    )
                    self.assertEqual(report.program_headers, phnum)
                    self.assertEqual(report.trailer_size, trailer)

    def test_rejects_bad_magic_and_endian(self) -> None:
        original = bytearray((FW89 / "qtn_driver.qtn_ruby.0.bin").read_bytes())
        bad_magic = bytearray(original)
        bad_magic[0] = 0
        with self.assertRaisesRegex(FirmwareFormatError, "magic"):
            inspect_firmware(bytes(bad_magic), source="bad", cpu="muc")
        bad_endian = bytearray(original)
        bad_endian[5] = 2
        with self.assertRaisesRegex(FirmwareFormatError, "big-endian"):
            inspect_firmware(bytes(bad_endian), source="bad", cpu="muc")

    def test_rejects_bad_phdr_size_and_file_larger_than_memory(self) -> None:
        original = bytearray((FW89 / "qtn_driver.qtn_ruby.0.bin").read_bytes())
        bad_phdr = bytearray(original)
        struct.pack_into("<H", bad_phdr, 42, 31)
        with self.assertRaisesRegex(FirmwareFormatError, "program-header size"):
            inspect_firmware(bytes(bad_phdr), source="bad", cpu="muc")
        bad_sizes = bytearray(original)
        phoff = struct.unpack_from("<I", bad_sizes, 28)[0]
        file_size = struct.unpack_from("<I", bad_sizes, phoff + 16)[0]
        struct.pack_into("<I", bad_sizes, phoff + 20, file_size - 1)
        with self.assertRaisesRegex(FirmwareFormatError, "p_filesz"):
            inspect_firmware(bytes(bad_sizes), source="bad", cpu="muc")

    def test_rejects_file_range_overflow_and_address_wrap(self) -> None:
        original = bytearray((FW89 / "qtn_driver.qtn_ruby.0.bin").read_bytes())
        phoff = struct.unpack_from("<I", original, 28)[0]
        bad_file = bytearray(original)
        struct.pack_into("<II", bad_file, phoff + 16, 0xFFFFFFFF, 0xFFFFFFFF)
        with self.assertRaisesRegex(FirmwareFormatError, "file range"):
            inspect_firmware(bytes(bad_file), source="bad", cpu="muc")
        bad_address = bytearray(original)
        struct.pack_into("<I", bad_address, phoff + 8, 0xFFFFFFF0)
        struct.pack_into("<I", bad_address, phoff + 12, 0)
        struct.pack_into("<I", bad_address, phoff + 20, 0x1000)
        with self.assertRaisesRegex(FirmwareFormatError, "address range"):
            inspect_firmware(bytes(bad_address), source="bad", cpu="muc")

    def test_rejects_loaded_segment_overlap(self) -> None:
        original = bytearray((FW89 / "qtn_driver.qtn_ruby.0.bin").read_bytes())
        phoff = struct.unpack_from("<I", original, 28)[0]
        first_virtual = struct.unpack_from("<I", original, phoff + 8)[0]
        second = phoff + 32
        struct.pack_into("<I", original, second + 8, first_virtual)
        struct.pack_into("<I", original, second + 12, 0)
        with self.assertRaisesRegex(FirmwareFormatError, "overlap"):
            inspect_firmware(bytes(original), source="bad", cpu="muc")

    def test_cpu_name_inference(self) -> None:
        self.assertEqual(infer_cpu("qtn_driver.qtn_ruby.0.bin"), "muc")
        self.assertEqual(infer_cpu("rdsp_driver.0.bin"), "dsp")
        self.assertEqual(infer_cpu("auc_driver.nomu.0.bin"), "auc")
        with self.assertRaises(FirmwareFormatError):
            infer_cpu("unknown.bin")


if __name__ == "__main__":
    unittest.main(verbosity=2)
