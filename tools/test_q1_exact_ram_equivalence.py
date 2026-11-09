#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_q1_exact_ram_equivalence.py"
SPEC = importlib.util.spec_from_file_location("q1_exact_ram_eq", RUNNER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Q1ExactRamEquivalenceTests(unittest.TestCase):
    def test_exact_inputs_and_profile_are_pinned(self) -> None:
        base = MODULE.BASE
        self.assertEqual("bd473ef7f7238a5f9488e4739308615355c7e86526c5c867e16d3a232908c306",
                         base.EXPECTED_SHA256)
        self.assertEqual(3_647_602, base.EXPECTED_BYTES)
        self.assertEqual("Q1_FULL_PRODUCT", base.PROFILE)
        self.assertEqual("OEM-PARITY-INTEGRATION", base.SCOPE)
        self.assertEqual(("S35-radio-modules", "S50-radio-ap"),
                         base.EXPECTED_DEGRADED_SERVICES)

    def test_default_dry_run_is_local_only_and_passes_exact_uart(self) -> None:
        proc = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OM_Q1_EXACT_RAM_EQ_DRY_RUN_PASS=1", proc.stdout)
        self.assertIn(MODULE.BASE.EXPECTED_SHA256, proc.stdout)
        self.assertIn('"hardware_actions": false', proc.stdout)
        self.assertIn('"radio_ap_failed_closed": true', proc.stdout)
        self.assertIn('"uart_log_sha256_pinned": true', proc.stdout)

    def test_uart_gate_rejects_any_radio_service_success_or_fatal(self) -> None:
        log = MODULE.BASE.DEFAULT_UART_LOG.read_text(encoding="utf-8", errors="replace")
        passed, markers = MODULE.BASE.uart_gate(MODULE.BASE.DEFAULT_UART_LOG)
        self.assertTrue(passed, markers)
        self.assertIn("OMINIT_SERVICE_END name=S35-radio-modules rc=1", log)
        self.assertIn("OMINIT_SERVICE_END name=S50-radio-ap rc=1", log)

    def test_runtime_degraded_predicate_names_both_services(self) -> None:
        script = MODULE.BASE.remote_snapshot_command()
        self.assertIn('S35-radio-modules', script)
        self.assertIn('S50-radio-ap', script)
        self.assertIn('n == 2', script)


if __name__ == "__main__":
    unittest.main()
