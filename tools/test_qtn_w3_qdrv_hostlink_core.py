#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_qtn_w3_qdrv_hostlink_core.py"
REMOTE = ROOT / "tools/qtn_w3_qdrv_hostlink_core_remote.sh"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QDRV_HOSTLINK_CORE_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QDRV_HOSTLINK_CORE_GATE.approved.env"


def values(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="utf-8").splitlines()
                if line and not line.startswith("#") and "=" in line)


class QdrvHostlinkCoreGateTests(unittest.TestCase):
    def test_gate_pair_differs_only_by_approval_and_reason(self):
        closed, approved = values(CLOSED), values(APPROVED)
        differences = {key for key in closed if closed[key] != approved[key]}
        self.assertEqual(differences, {"W3_QDRV_HOSTLINK_CORE_APPROVED", "W3_STOP_REASON"})

    def test_gate_is_ram_only_without_vap_or_rf(self):
        gate = values(APPROVED)
        self.assertEqual(gate["W3_QDRV_COMMAND_COUNT"], "9")
        self.assertEqual(gate["W3_VAP_CREATE_COUNT"], "0")
        for key in ("W3_RF_ENABLE", "W3_WIFI_ENABLE", "W3_VAP_ENABLE", "W3_FLASH_ENABLE"):
            self.assertEqual(gate[key], "0")

    def test_remote_stops_after_core_and_requires_wire_completion(self):
        text = REMOTE.read_text(encoding="utf-8")
        self.assertNotIn("start 0 ap wifi0", text)
        self.assertIn("OMQDRVHLINK stage=alloc-pass", text)
        self.assertIn("OMQDRVHLINK stage=publish", text)
        self.assertIn("OMQDRVHLINK stage=complete", text)
        self.assertIn("cmd=19", text)
        self.assertIn("rc=1", text)
        self.assertIn("test ! -e /sys/class/net/wifi0", text)

    def test_runner_pins_new_qdrv_and_parent(self):
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("quantenna-linux510-radiohw-qdrv-hostlinkwire-20260820", text)
        self.assertIn("quantenna-linux510-radiohw-qdrv-sequential-20260819", text)
        self.assertIn("W3_REMOTE_SHA256", text)

    def test_no_rmmod_flash_or_rf_mutation(self):
        combined = (RUNNER.read_text(encoding="utf-8") + REMOTE.read_text(encoding="utf-8")).lower()
        for forbidden in ("rmmod ", "flash_erase", "mtd write", "saveenv", "openmitrastar_rf_enable=1"):
            self.assertNotIn(forbidden, combined)

    def test_dry_run(self):
        result = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT,
                                text=True, capture_output=True, timeout=60, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("W3_QDRV_HOSTLINK_CORE_DRY_RUN_PASS=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
