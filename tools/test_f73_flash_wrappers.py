#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/recover_flash_f73_qcsapi_path_fixed.ps1"
POSTGATE = ROOT / "tools/recover_flash_f73_then_postgate.ps1"


class F73FlashWrapperTests(unittest.TestCase):
    def test_flash_wrapper_exposes_reboot_assist_flags(self) -> None:
        text = FLASH.read_text(encoding="utf-8")
        for needle in (
            "[switch]$SshRebootFirst",
            "[switch]$SysRqRebootFirst",
            "[switch]$ConsoleRebootAssist",
            "[switch]$PulseResetLinesFirst",
            "$args.SshRebootFirst = $true",
            "$args.SysRqRebootFirst = $true",
            "$args.ConsoleRebootAssist = $true",
            "$args.PulseResetLinesFirst = $true",
            "AllowNoRxRebootAssist = $true",
        ):
            self.assertIn(needle, text)

    def test_postgate_wrapper_propagates_reboot_assist_flags(self) -> None:
        text = POSTGATE.read_text(encoding="utf-8")
        for needle in (
            "[switch]$SshRebootFirst",
            "[switch]$SysRqRebootFirst",
            "[switch]$ConsoleRebootAssist",
            "[switch]$PulseResetLinesFirst",
            "$recoveryArgs.SshRebootFirst = $true",
            "$recoveryArgs.SysRqRebootFirst = $true",
            "$recoveryArgs.ConsoleRebootAssist = $true",
            "$recoveryArgs.PulseResetLinesFirst = $true",
        ):
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
