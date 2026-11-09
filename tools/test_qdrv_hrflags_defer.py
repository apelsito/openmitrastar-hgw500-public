#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WLAN = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"
REMOTE = ROOT / "tools/qtn_w3_qdrv_sequential_bringup_remote.sh"


class QdrvHrflagsDeferTests(unittest.TestCase):
    def test_hrflags_waits_for_first_vap(self):
        text = WLAN.read_text(encoding="utf-8")
        self.assertIn('TAILQ_EMPTY(&qw->ic.ic_vaps)', text)
        self.assertIn('OMQDRVHR stage=deferred reason=no-vap', text)
        self.assertIn('mod_timer(&qw->hr_timer, jiffies + HZ)', text)
        self.assertIn('OMQDRVHR stage=send-pass', text)
        self.assertIn('qdrv_hostlink_set_hrflags(qw, 1)', text)
        self.assertIn('hr_rc < 0 || (hr_rc & QTN_HLINK_RC_ERR)', text)
        self.assertIn('!!(hr_rc & QTN_HLINK_RC_DONE)', text)

    def test_runtime_gate_rejects_muc_exception(self):
        text = REMOTE.read_text(encoding="utf-8")
        self.assertIn('MuC exception', text)
        self.assertIn('forcing reboot', text)
        self.assertIn('reason=fatal_runtime_marker', text)


if __name__ == "__main__":
    unittest.main()
