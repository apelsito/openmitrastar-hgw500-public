#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools" / "run_router_lyoko_current_offline_suite.py"


class RouterLyokoCurrentOfflineSuiteTests(unittest.TestCase):
    def test_list_mode_declares_current_safe_scope(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--list"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=15,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMROUTER_LYOKO_CURRENT_OFFLINE_SUITE_LIST_PASS=1", proc.stdout)
        report, _ = json.JSONDecoder().raw_decode(proc.stdout.lstrip())
        self.assertEqual(report["schema"], "router-lyoko.current-offline-suite/v1")
        self.assertEqual(report["classification"], "READONLY-OFFLINE-TEST-SUITE-NO-HARDWARE")
        self.assertEqual(report["test_count"], 46)
        self.assertEqual(report["missing"], [])
        tests = set(report["tests"])
        self.assertIn("tools/test_monitor_2g_live_traffic.py", tests)
        self.assertIn("tools/test_evaluate_w2_2g_live_traffic.py", tests)
        self.assertIn("tools/test_openmitrastar_tool_security.py", tests)
        self.assertIn("tools/test_preflight_post_tx7_resume_offline.py", tests)
        self.assertIn("tools/test_package_router_lyoko_overlay.py", tests)
        self.assertIn("tools/test_post_tx7_recovery_result_verifier.py", tests)
        self.assertIn("tools/test_resume_post_tx7_result_verifier.py", tests)
        self.assertIn("tools/test_router_lyoko_evidence_bindings.py", tests)
        self.assertIn("tools/test_router_lyoko_telemetry_contract.py", tests)
        self.assertIn("tools/test_router_lyoko_objective_coverage.py", tests)
        self.assertIn("tools/test_qdrv_v89_beacon_wire_layout.py", tests)
        self.assertIn("tools/test_w2_tx9_gate.py", tests)
        self.assertIn("tools/test_w2_tx12_mgmt_trace.py", tests)
        self.assertIn("tools/test_w2_tx13_mgmt_trace.py", tests)
        self.assertIn("tools/test_w2_tx17_beacon_aperture.py", tests)
        self.assertIn("tools/test_w2_tx17_ram_boot.py", tests)
        self.assertIn("tools/test_w2_tx18_single_variable.py", tests)
        self.assertIn("tools/test_w2_tx18_ram_boot.py", tests)
        self.assertIn("tools/test_rtl8192ee_mgmt_trace_budget.py", tests)
        self.assertIn("tools/test_rtl8192ee_mgmt_txbd_split.py", tests)
        self.assertIn("tools/test_rtl8192ee_mgmt_frame_fields.py", tests)
        self.assertNotIn("tools/test_openmitrastar_f6_certification.py", tests)
        self.assertNotIn("tools/test_q3_persistent_composite.py", tests)
        self.assertIn("historical Q1/Q2/Q3/W5 product artifact tests", report["excluded_scope"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
