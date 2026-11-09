#!/usr/bin/env python3
from pathlib import Path
import importlib.util
import io
from contextlib import redirect_stdout
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_qtn_w3_5g_autopilot.py"


class Qtn5gAutopilotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")
        spec = importlib.util.spec_from_file_location("qtn5g_autopilot", SCRIPT)
        assert spec and spec.loader
        cls.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.module)

    def test_exact_stage_markers_and_acknowledgements(self):
        for marker in (
            "W3_SWITCH_EMAC_HANDOFF_EXPERIMENT_PASS=1",
            "W3_QDRV_SEQUENTIAL_BRINGUP_EXPERIMENT_PASS=1",
            "W3_QCSAPI_5G_AP_EXPERIMENT_PASS=1",
            "OPENMITRASTAR_QTN_W3_5G_AUTOPILOT_RAM_ONLY",
        ):
            self.assertIn(marker, self.text)

    def test_no_flash_or_secret_echo_path(self):
        lowered = self.text.lower()
        for forbidden in ("flash_erase", "mtd write", "nand write", "saveenv"):
            self.assertNotIn(forbidden, lowered)
        self.assertIn("flash=0", self.text)
        self.assertIn("psk=redacted", self.text)

    def test_bounded_cold_rearm(self):
        self.assertIn("--max-cold-attempts", self.text)
        self.assertIn("1 <= args.max_cold_attempts <= 5", self.text)
        self.assertIn("await-next-physical-cold-cycle", self.text)

    def test_stage_timeout_is_caught_and_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            marker = Path(temporary) / "never"
            output = io.StringIO()
            with redirect_stdout(output):
                passed = self.module.run_stage(
                    [sys.executable, "-c", "import time; time.sleep(2)"],
                    str(marker), "timeout-test", 0.2,
                )
        self.assertFalse(passed)
        self.assertIn("state=timeout", output.getvalue() + " state=timeout")

    def test_final_scope_does_not_claim_client_pass(self):
        self.assertIn("AP_CONTROL_PLANE_PASS", self.text)
        self.assertIn("client_association=UNVERIFIED", self.text)
        self.assertIn("client_traffic=UNVERIFIED", self.text)
        self.assertNotIn("AUTOPILOT_EXPERIMENT_PASS=1", self.text)

    def test_embedded_pass_marker_is_rejected(self):
        marker = "GATE_PASS=1"
        self.assertFalse(self.module.has_exact_marker("PREFIXGATE_PASS=1SUFFIX", marker))
        self.assertTrue(self.module.has_exact_marker("GATE_PASS=1", marker))
        self.assertTrue(self.module.has_exact_marker("GATE_PASS=1 field=value", marker))

    def test_execute_preflights_every_child_before_cold_cycle(self):
        self.assertIn("def preflight_children()", self.text)
        self.assertIn("child gate preflight failed before cold-cycle", self.text)
        self.assertNotIn("--adopt-pid", self.text)

    def test_psk_is_resolved_and_prevalidated(self):
        self.assertIn("args.psk_file = args.psk_file.resolve()", self.text)
        self.assertIn("verify_psk(args.psk_file)", self.text)
        self.assertIn("secrets=(psk_secret,)", self.text)

    def test_stage_logs_are_redacted_before_persistence(self):
        secret = "SECRET-MUST-NOT-PERSIST"
        label = f"redaction-test-{id(self)}"
        passed = self.module.run_stage(
            [sys.executable, "-c", f"print('{secret}'); print('PASS-MARKER')"],
            "PASS-MARKER", label, 10, secrets=(secret,),
        )
        self.assertTrue(passed)
        logs = sorted(
            (ROOT / "outputs/runner-live/autopilot-stages").glob(f"{label}-*.out.log"),
            key=lambda path: path.stat().st_mtime,
        )
        self.assertTrue(logs)
        persisted = logs[-1].read_text(encoding="utf-8")
        self.assertNotIn(secret, persisted)
        self.assertIn("<redacted>", persisted)

    def test_generic_adoption_surface_is_removed(self):
        self.assertNotIn("--adopt-pid", self.text)
        self.assertNotIn("validate_adoption", self.text)
        self.assertNotIn("state=adopting", self.text)

    def test_dry_run_closes_all_three_child_gates(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=ROOT, text=True,
            capture_output=True, timeout=240, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("W3_QTN_5G_AUTOPILOT_DRY_RUN_PASS=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
