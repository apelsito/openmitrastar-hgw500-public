#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/q3_client_stream_openssh.py"


class Q3ClientStreamOpenSshTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_uses_persistent_ed25519_identity(self) -> None:
        self.assertIn('Path.home() / ".ssh/id_ed25519"', self.text)
        self.assertIn('"IdentitiesOnly=yes"', self.text)
        self.assertIn('"BatchMode=yes"', self.text)
        self.assertNotIn("load_private_key", self.text)
        self.assertIn('text=False', self.text)
        self.assertIn('.encode("ascii")', self.text)
        self.assertIn("max(90, args.interval * 30)", self.text)
        self.assertIn("stdout_queue.get(timeout=0.5)", self.text)
        self.assertIn("tail -n 512", self.text)
        self.assertIn('parser.add_argument("--lightweight", action="store_true")', self.text)
        self.assertIn('parser.add_argument("--buffered", action="store_true")', self.text)
        self.assertIn('"lightweight": args.lightweight', self.text)
        self.assertIn('"buffered": args.buffered', self.text)
        self.assertIn("wifi_rx=0", self.text)
        self.assertIn("br_tx=0", self.text)
        self.assertIn("association_sample", self.text)
        self.assertIn('association_sample = "  assoc=0\\n" if lightweight', self.text)
        self.assertIn("radio5_state=$(cat /run/openmitrastar/radio5g/state", self.text)
        self.assertIn('"management_lost": not tcp22_after', self.text)
        self.assertNotIn("fatal=$(dmesg", self.text)

    def test_preserves_single_session_and_read_only_contract(self) -> None:
        self.assertIn('f"root@{args.host}", "sh", "-s"', self.text)
        self.assertIn('"mutations": False', self.text)
        self.assertIn('"flash": False', self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
