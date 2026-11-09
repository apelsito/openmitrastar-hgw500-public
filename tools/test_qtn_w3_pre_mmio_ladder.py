#!/usr/bin/env python3
from __future__ import annotations

import re
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/qtn_w3_pre_mmio_ladder.sh"
GATE = ROOT / "work/mission-state/w3-offline/W3_RUNTIME_GATE.env"


class QuantennaPreMmioLadderTests(unittest.TestCase):
    def test_shell_syntax(self) -> None:
        result = subprocess.run(
            ["wsl", "--exec", "sh", "-n", str(SCRIPT).replace("C:\\", "/mnt/c/").replace("\\", "/")],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_current_gate_is_fail_closed(self) -> None:
        values = dict(
            line.split("=", 1)
            for line in GATE.read_text(encoding="utf-8").splitlines()
            if line and not line.startswith("#")
        )
        self.assertEqual(values["W3_PAIR_APPROVED"], "1")
        self.assertEqual(values["W3_HARDWARE_ACTIVE_APPROVED"], "0")
        self.assertEqual(values["W3_STOP_REASON"], "HARDWARE_ACTIVE_NOT_APPROVED")
        self.assertEqual(values["W3_OVERLAP_CLASS"], "OEM_QUIRK_PROVEN")

    def test_no_irreversible_module_or_core_command(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        executable = "\n".join(
            line for line in text.splitlines() if not line.lstrip().startswith("#")
        )
        self.assertNotRegex(executable, r"insmod[^\n]*(?:hbm|switch_tqe|temp_sens|gpio)\.ko")
        self.assertNotRegex(executable, r"(?:echo|printf)[^\n]*(?:clearsram|qdrv start)")
        self.assertNotIn("/dev/mtd", executable)
        self.assertNotIn("flash_erase", executable)
        self.assertRegex(executable, r"stop 42 .*pre_mmio_checkpoint")

    def test_exact_board_values_and_absent_env_are_preserved(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        for token in ("board_id=65535", "emac0=1", "emac1=1", "wifi_hw=7", "rfic=4"):
            self.assertIn(token, text)
        self.assertNotRegex(text, re.compile(r"\bbond_opt="))
        self.assertNotRegex(text, re.compile(r"\bpower_recheck="))
        self.assertNotRegex(text, re.compile(r"\bpost_mask="))
        self.assertNotRegex(text, re.compile(r"\bdev_mode="))


if __name__ == "__main__":
    unittest.main(verbosity=2)
