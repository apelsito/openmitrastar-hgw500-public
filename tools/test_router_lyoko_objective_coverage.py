#!/usr/bin/env python3

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "verify_router_lyoko_objective_coverage.py"
OVERLAY = ROOT / "work/mission-state/router-lyoko-v0"
RECOVERED_TX7_BOOT_STATES = {
    "TX7_RAM_RECOVERED_2G_CLIENT_GATE_ACTIVE",
    "TX7_RAM_RECOVERED_2G_NO_CLIENT_SOAK_COMPLETE",
}


def run_guard(overlay: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), "--overlay", str(overlay)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def copy_overlay(tmp: Path) -> Path:
    dst = tmp / "router-lyoko-v0"
    shutil.copytree(OVERLAY, dst)
    return dst


class RouterLyokoObjectiveCoverageTests(unittest.TestCase):
    def test_current_overlay_covers_objective_without_overclaim(self):
        proc = run_guard(OVERLAY)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["classification"], "READONLY-OBJECTIVE-COVERAGE-NO-HARDWARE")
        self.assertGreaterEqual(report["surfaces_checked"], 12)
        self.assertFalse(report["completion_state"]["achieved"])
        if report["completion_state"]["hardware_blocked"]:
            self.assertEqual(report["completion_state"]["next_gate"], "phase1.current-post-tx7-recovery")
        else:
            self.assertIn(report["completion_state"]["boot_state"], RECOVERED_TX7_BOOT_STATES)
            self.assertIn(
                report["completion_state"]["next_gate"],
                {"phase1.bridge-ethernet-ssh", "phase2.realtek-2g-complete"},
            )
        surface_ids = {surface["id"] for surface in report["surfaces"]}
        self.assertIn("router.realtek_2g", surface_ids)
        self.assertIn("router.quantenna_5g", surface_ids)
        self.assertIn("lyoko.aelita_persona_memory", surface_ids)

    def test_rejects_missing_objective_panel(self):
        with tempfile.TemporaryDirectory() as td:
            overlay = copy_overlay(Path(td))
            html = overlay / "rootfs/var/www/lyoko.html"
            html.write_text(
                html.read_text(encoding="utf-8").replace('id="runtime-clients"', 'id="runtime-clients-missing"', 1),
                encoding="utf-8",
            )
            proc = run_guard(overlay)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            kinds = {finding["kind"] for finding in report["findings"]}
            self.assertIn("missing_html_surface", kinds)

    def test_rejects_goal_completion_overclaim(self):
        with tempfile.TemporaryDirectory() as td:
            overlay = copy_overlay(Path(td))
            audit_path = overlay / "rootfs/var/www/lyoko-data/goal-audit.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["achieved"] = True
            audit["status"] = "COMPLETE"
            audit["summary"]["hardware_blocked"] = False
            audit["summary"]["boot_state"] = "TX7_POST_5G_MISALIGNED_ACCESS_HUNG_WAITING_PHYSICAL_POWER_CYCLE"
            audit["summary"]["next_gate"] = "phase2.realtek-2g-complete"
            audit_path.write_text(json.dumps(audit, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            proc = run_guard(overlay)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            kinds = {finding["kind"] for finding in report["findings"]}
            self.assertIn("goal_overclaim", kinds)
            self.assertIn("goal_status_overclaim", kinds)
            self.assertIn("hardware_block_missing", kinds)

    def test_rejects_hardware_gate_promoted_from_static_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            overlay = copy_overlay(Path(td))
            truth_path = overlay / "rootfs/var/www/lyoko-data/mission-truth.json"
            truth = json.loads(truth_path.read_text(encoding="utf-8"))
            for gate in truth["gates"]:
                if gate["id"] == "phase2.realtek-2g-complete":
                    gate["status"] = "PROVEN"
            truth_path.write_text(json.dumps(truth, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            proc = run_guard(overlay)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertIn("hardware_overclaim", {finding["kind"] for finding in report["findings"]})

    def test_rejects_missing_evidence_binding_for_surface(self):
        with tempfile.TemporaryDirectory() as td:
            overlay = copy_overlay(Path(td))
            bindings_path = overlay / "rootfs/var/www/lyoko-data/evidence-bindings.json"
            bindings = json.loads(bindings_path.read_text(encoding="utf-8"))
            bindings["bindings"] = [
                binding for binding in bindings["bindings"] if binding.get("id") != "static.aelita_memory"
            ]
            bindings_path.write_text(json.dumps(bindings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            proc = run_guard(overlay)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            self.assertIn("missing_evidence_binding", {finding["kind"] for finding in report["findings"]})


if __name__ == "__main__":
    unittest.main()
