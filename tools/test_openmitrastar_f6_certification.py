#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools/verify_openmitrastar_f6_certification.py"
MATRIX = ROOT / "docs/OPENMITRASTAR_F6_CERTIFICATION_MATRIX.json"
spec = importlib.util.spec_from_file_location("f6_verify", VERIFIER)
assert spec and spec.loader
f6 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f6)


class F6CertificationTests(unittest.TestCase):
    def test_matrix_counts_and_integrity(self):
        data = json.loads(MATRIX.read_text(encoding="utf-8"))
        counts, errors = f6.validate_matrix(data)
        self.assertEqual(errors, [])
        self.assertEqual(sum(counts.values()), 49)
        self.assertEqual(counts["PROVEN"], 13)
        self.assertEqual(counts["PARTIAL"], 21)
        self.assertEqual(counts["PENDING"], 10)
        self.assertEqual(counts["BLOCKED"], 5)

    def test_default_verifier_fails_closed(self):
        result = subprocess.run(
            [sys.executable, str(VERIFIER)], cwd=ROOT,
            capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn("F6_MATRIX_INTEGRITY_PASS", result.stdout)
        self.assertIn("F6_CERTIFICATION_INCOMPLETE", result.stdout)

    def test_allow_incomplete_is_audit_only(self):
        result = subprocess.run(
            [sys.executable, str(VERIFIER), "--allow-incomplete", "--json"],
            cwd=ROOT, capture_output=True, text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('"complete": false', result.stdout)
        self.assertIn("F6_CERTIFICATION_INCOMPLETE", result.stdout)


if __name__ == "__main__":
    unittest.main()
