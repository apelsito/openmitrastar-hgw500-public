import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
AUDIT = ROOT / "tools/audit_qtn_5g_master_offline.py"


class Qtn5gMasterOfflineAuditTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        proc = subprocess.run(
            [sys.executable, str(AUDIT)],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        cls.returncode = proc.returncode
        cls.report = json.loads(proc.stdout)
        cls.stderr = proc.stderr

    def test_offline_contract_passes(self):
        self.assertEqual(0, self.returncode, self.stderr)
        self.assertTrue(self.report["reentry_gate"]["offline_contract_pass"])

    def test_board_65535_is_expected(self):
        self.assertEqual(65535, self.report["board"]["board_id"])
        self.assertIn("expected", self.report["board"]["board_id_meaning"])

    def test_latest_fault_is_not_attributed_to_qdrv(self):
        self.assertEqual("realtek_rtl8192ee_rx", self.report["latest_hard_fault"]["owner"])
        self.assertEqual("quantenna_qdrv", self.report["latest_hard_fault"]["not_owner"])

    def test_current_q3_is_not_reentry_eligible(self):
        gate = self.report["reentry_gate"]
        self.assertFalse(gate["current_q3_contains_realtek_rx_fix"])
        self.assertFalse(gate["ram_validation_eligible"])

    def test_proven_and_unproven_scope_is_separated(self):
        matrix = self.report["completion_matrix"]
        self.assertEqual("PROVEN", matrix["open_auth_assoc"])
        self.assertEqual("PROVEN", matrix["client_to_ap_l2"])
        self.assertEqual("NOT_PROVEN", matrix["ap_to_client_l2"])
        self.assertEqual("NOT_PROVEN", matrix["dfs_cac_radar"])

    def test_audit_is_offline_only(self):
        safety = self.report["safety"]
        self.assertFalse(safety["router_accessed"])
        self.assertFalse(safety["uart_used"])
        self.assertFalse(safety["tftp_used"])
        self.assertFalse(safety["mtd_writes"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
