#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VALIDATOR = ROOT / "tools/validate_router_lyoko_sector_map.py"
SECTOR_MAP = ROOT / "work/mission-state/router-lyoko-v0/sector-map.json"
TRUTH = ROOT / "work/mission-state/router-lyoko-v0/mission-truth.json"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoSectorMapTests(unittest.TestCase):
    def test_sector_map_matches_mission_truth_and_evidence(self):
        proc = run_validator()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertGreaterEqual(report["sectors"], 7)
        self.assertGreaterEqual(report["towers"], 5)

    def test_rejects_sector_status_drift(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SECTOR_MAP.read_text(encoding="utf-8"))
            mutated["sectors"][0]["status"] = "BLOCKED"
            path = Path(td) / "sector-map.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--sector-map", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("status", proc.stderr)

    def test_rejects_missing_evidence_path(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SECTOR_MAP.read_text(encoding="utf-8"))
            mutated["sectors"][0]["evidence"] = ["work/mission-state/does-not-exist.md"]
            path = Path(td) / "sector-map.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--sector-map", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("evidence path missing", proc.stderr)

    def test_rejects_tower_with_unknown_sector(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SECTOR_MAP.read_text(encoding="utf-8"))
            mutated["towers"][0]["sector"] = "mar_digital"
            path = Path(td) / "sector-map.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--sector-map", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("unknown sector", proc.stderr)

    def test_rejects_tower_without_evidence_paths(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SECTOR_MAP.read_text(encoding="utf-8"))
            mutated["towers"][0].pop("evidence", None)
            path = Path(td) / "sector-map.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--sector-map", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("tower tower_ssh has no evidence paths", proc.stderr)

    def test_rejects_executable_control_token(self):
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(SECTOR_MAP.read_text(encoding="utf-8"))
            mutated["towers"][0]["real_service"] = "operator should run reboot"
            path = Path(td) / "sector-map.json"
            path.write_text(json.dumps(mutated), encoding="utf-8")
            proc = run_validator("--sector-map", str(path))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("forbidden executable/control token", proc.stderr)


if __name__ == "__main__":
    unittest.main()
