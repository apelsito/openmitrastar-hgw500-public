#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/validate_router_lyoko_evidence_bindings.py"
BINDINGS = ROOT / "work/mission-state/router-lyoko-v0/evidence-bindings.json"
WEB_ROOT = ROOT / "work/mission-state/router-lyoko-v0/rootfs/var/www"


def run_validator(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoEvidenceBindingsTests(unittest.TestCase):
    def test_current_evidence_bindings_pass(self) -> None:
        proc = run_validator()
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["classification"], "READONLY-EVIDENCE-BINDINGS-GUARD-NO-HARDWARE")
        self.assertGreaterEqual(report["runtime_bindings"], 8)
        self.assertGreaterEqual(report["static_bindings"], 5)

    def test_rejects_runtime_binding_without_hardware_proof(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(BINDINGS.read_text(encoding="utf-8"))
            mutated["bindings"][0]["hardware_proof"] = False
            path = Path(td) / "evidence-bindings.json"
            path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
            proc = run_validator("--bindings", str(path), "--web-root", str(WEB_ROOT))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("binding live.system must set hardware_proof=true", proc.stderr)

    def test_rejects_static_binding_promoted_to_hardware_proof(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(BINDINGS.read_text(encoding="utf-8"))
            static_binding = next(item for item in mutated["bindings"] if item["id"] == "static.goal_audit")
            static_binding["hardware_proof"] = True
            path = Path(td) / "evidence-bindings.json"
            path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
            proc = run_validator("--bindings", str(path), "--web-root", str(WEB_ROOT))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("binding static.goal_audit must set hardware_proof=false", proc.stderr)

    def test_rejects_static_source_that_is_not_served(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            mutated = json.loads(BINDINGS.read_text(encoding="utf-8"))
            static_binding = next(item for item in mutated["bindings"] if item["id"] == "static.reentry")
            static_binding["source"] = "/lyoko-data/does-not-exist.json"
            path = Path(td) / "evidence-bindings.json"
            path.write_text(json.dumps(mutated, indent=2), encoding="utf-8")
            proc = run_validator("--bindings", str(path), "--web-root", str(WEB_ROOT))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("binding static.reentry static source missing: /lyoko-data/does-not-exist.json", proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
