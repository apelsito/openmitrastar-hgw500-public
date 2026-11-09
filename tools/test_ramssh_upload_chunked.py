#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/ramssh_upload_chunked.py"


class ChunkedUploadTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_bounded_chunks_and_retries(self):
        self.assertIn("default=65536", self.text)
        self.assertIn("16384 <= args.chunk_bytes <= 131072", self.text)
        self.assertIn("args.retries", self.text)

    def test_new_connection_per_chunk(self):
        self.assertIn("client = connect(host, key)", self.text)
        self.assertIn("cat >> {destination}", self.text)

    def test_remote_hash_before_atomic_rename(self):
        self.assertIn("/bin/busybox sha256sum", self.text)
        self.assertLess(self.text.index("sha256sum"), self.text.index("mv {temporary} {destination}"))

    def test_no_secret_or_flash_surface(self):
        lowered = self.text.lower()
        for forbidden in ("password=", "flash_erase", "mtd write", "saveenv"):
            self.assertNotIn(forbidden, lowered)


if __name__ == "__main__":
    unittest.main()
