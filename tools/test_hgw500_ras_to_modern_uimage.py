"""Format/range regression tests: no device access or real firmware writes."""
import hashlib
import struct
import unittest
import zlib

from hgw500_ras_to_modern_uimage import convert, LOW, HIGH


def ras(payload, comp=0, load=LOW, entry=LOW+4, arch=19):
    header = bytearray(struct.pack(">7I4B32s", 0x27051956, 0, 0, len(payload), load, entry,
                                  zlib.crc32(payload) & 0xFFFFFFFF, 5, arch, 2, comp, b"fixture"))
    struct.pack_into(">I", header, 4, zlib.crc32(header) & 0xFFFFFFFF)
    return bytes(header) + bytes(0x2000-64) + payload


class ConversionTests(unittest.TestCase):
    def test_uncompressed_exact_payload(self):
        payload = bytes(range(256)) * 4
        data = ras(payload)
        out, result = convert(data)
        self.assertEqual(out[64:], payload)
        self.assertEqual(out[29], 23)
        self.assertEqual(result["load_end"], hex(LOW + len(payload)))
        # Only hcrc/arch in header may differ; all payload bytes must match.
        allowed = {4, 5, 6, 7, 29}
        self.assertTrue(all(a == b or i in allowed for i, (a,b) in enumerate(zip(data[:64], out[:64]))))
        header = bytearray(out[:64]); stored = struct.unpack_from(">I", header, 4)[0];header[4:8]=bytes(4)
        self.assertEqual(zlib.crc32(header) & 0xFFFFFFFF, stored)
        self.assertEqual(hashlib.sha256(data[0x2000:]).hexdigest(), result["payload_sha256"])

    def test_invalid_magic_header_payload_and_truncation(self):
        data = ras(bytes(range(256)))
        mutants = [data[:50], data[:-1], bytes([data[0]^1])+data[1:],
                   data[:8]+bytes([data[8]^1])+data[9:],
                   data[:-1]+bytes([data[-1]^1])]
        for mutant in mutants:
            with self.subTest(size=len(mutant)), self.assertRaises(ValueError):convert(mutant)

    def test_architecture_and_compression(self):
        for arch,comp in [(23,0),(2,0),(19,1),(19,3)]:
            with self.subTest(arch=arch,comp=comp), self.assertRaises(ValueError):convert(ras(bytes(256),arch=arch,comp=comp))

    def test_load_entry_and_overlap(self):
        for load,entry in [(LOW-4,LOW),(HIGH-128,HIGH-124),(LOW,LOW-4),(LOW,LOW+256),(LOW,LOW+1)]:
            with self.subTest(load=load,entry=entry), self.assertRaises(ValueError):convert(ras(bytes(256),load=load,entry=entry))


if __name__ == "__main__":unittest.main()
