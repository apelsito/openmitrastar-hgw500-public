#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools/verify_router_lyoko_static_index.py"
INDEX = ROOT / "work/mission-state/router-lyoko-v0/rootfs/var/www/lyoko-data/index.json"
MANIFEST = ROOT / "work/mission-state/router-lyoko-v0/manifest.json"


def run_verifier(payload: dict, *args: str) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "index.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(VERIFIER), "--input-json", str(path), "--manifest", str(MANIFEST), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


class RouterLyokoStaticIndexVerifierTests(unittest.TestCase):
    def test_accepts_current_static_index_against_manifest(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(VERIFIER), "--input-json", str(INDEX), "--manifest", str(MANIFEST)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertTrue(all(check["ok"] for check in report["checks"]))

    def test_rejects_static_index_hash_drift(self) -> None:
        payload = json.loads(INDEX.read_text(encoding="utf-8"))
        payload["files"]["mission-truth.json"]["sha256"] = "0" * 64
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("manifest.mission-truth.json.sha256", failing)

    def test_rejects_write_safety_flag(self) -> None:
        payload = json.loads(INDEX.read_text(encoding="utf-8"))
        payload["safety"]["flash_write"] = True
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("safety.flash_write.false", failing)

    def test_rejects_extra_file_not_in_manifest(self) -> None:
        payload = json.loads(INDEX.read_text(encoding="utf-8"))
        payload["files"]["stale-extra.json"] = {"bytes": 1, "sha256": "1" * 64}
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("manifest.no_extra_index_files", failing)


if __name__ == "__main__":
    unittest.main()
