#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_qtn_w3_qdrv_control.py"
REMOTE = ROOT / "tools/qtn_w3_qdrv_control_remote.sh"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QDRV_CONTROL_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QDRV_CONTROL_GATE.approved.env"
QDRV_FWT = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_fwt_compat.c"
WLAN_FWT = ROOT / "work/linux510-radio-port/quantenna/wlan/wlan_fwt_compat.c"
WLAN_LINUX = ROOT / "work/linux510-radio-port/quantenna/wlan/ieee80211_linux.c"


class QdrvControlTests(unittest.TestCase):
    def test_gate_pair(self):
        closed = CLOSED.read_text()
        approved = APPROVED.read_text()
        closed = closed.replace("W3_QDRV_CONTROL_APPROVED=0", "W3_QDRV_CONTROL_APPROVED=1")
        closed = closed.replace("QDRV_CONTROL_NOT_APPROVED", "QDRV_CONTROL_ONE_SHOT_APPROVED")
        self.assertEqual(closed, approved)

    def test_remote_is_control_only_and_rf_closed(self):
        text = REMOTE.read_text()
        self.assertIn("W3_RF_ENABLE", text)
        self.assertIn("stage=control-ready", text)
        self.assertIn("panic_on_muc_halt", text)
        self.assertIn("brif/eth1_emac1", text)
        self.assertIn("stage=module-preloaded module=gpio", text)
        self.assertIn("stage=load-enter module=wlan", text)
        self.assertIn("W3_QDRV_WLAN_ONLY_EXPERIMENT_PASS=1", text)
        self.assertNotRegex(text, re.compile(r"(?:echo|printf).*\b(?:start|clearsram)\b"))
        self.assertNotRegex(text, re.compile(r"\b(?:ifconfig|iwconfig|iwpriv)\s+wifi0\b"))

    def test_fwt_dependencies_are_replaced_fail_closed(self):
        qdrv = QDRV_FWT.read_text()
        wlan = WLAN_FWT.read_text()
        self.assertIn("result=disabled", qdrv)
        self.assertIn("return -EOPNOTSUPP", qdrv)
        self.assertIn("result=unsupported", wlan)
        self.assertNotIn("EXPORT_SYMBOL", qdrv + wlan)

    def test_legacy_wlan_notifier_is_deferred_on_mitrastar(self):
        text = WLAN_LINUX.read_text()
        self.assertIn("OPENMITRASTAR_QDRV_V89_PAIR", text)
        self.assertIn("defer notifier registration", text)

    def test_syntax_and_dry_run(self):
        py = subprocess.run([sys.executable, "-m", "py_compile", str(RUNNER)], cwd=ROOT)
        self.assertEqual(py.returncode, 0)
        sh = subprocess.run(["wsl.exe", "sh", "-n", "/workspace/user-home/Desktop/MitraStar/tools/qtn_w3_qdrv_control_remote.sh"], cwd=ROOT)
        self.assertEqual(sh.returncode, 0)
        dry = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("W3_QDRV_CONTROL_DRY_RUN_PASS=1", dry.stdout)
        runner_text = RUNNER.read_text()
        self.assertIn("capture_topaz_uart.ps1", runner_text)
        self.assertIn("qdrv control remote failed", runner_text)
        self.assertIn("--stop-after-wlan", runner_text)


if __name__ == "__main__":
    unittest.main()
