#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_qtn_w3_hostlink_core_cold_pipeline.py"


class HostlinkCoreColdPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SCRIPT.read_text(encoding="utf-8")

    def test_pipeline_is_ram_only_without_vap_rf_or_flash(self):
        self.assertIn("flash=0 vap=0 rf=0", self.text)
        self.assertNotIn("run_qtn_w3_qcsapi_5g_ap.py", self.text)
        self.assertNotIn("start 0 ap", self.text)

    def test_switch_precedes_core(self):
        self.assertLess(self.text.index("run_qtn_w3_switch_emac_handoff.py"),
                        self.text.index("run_qtn_w3_qdrv_hostlink_core.py"))
        self.assertIn("RAMSSH_CYCLE_START", self.text)

    def test_exact_ack_and_markers(self):
        self.assertIn("OPENMITRASTAR_QTN_W3_HOSTLINK_CORE_COLD_PIPELINE_RAM_ONLY", self.text)
        self.assertIn("W3_SWITCH_EMAC_HANDOFF_EXPERIMENT_PASS=1", self.text)
        self.assertIn("W3_QDRV_HOSTLINK_CORE_EXPERIMENT_PASS=1", self.text)

    def test_dry_run(self):
        result = subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT,
                                text=True, capture_output=True, timeout=300, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("W3_HOSTLINK_CORE_COLD_PIPELINE_DRY_RUN_PASS=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
