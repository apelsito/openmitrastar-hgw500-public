#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
F75 = ROOT / "tools/flash_f75_2g_stable_5g_manual.ps1"
F76 = ROOT / "tools/flash_f76_2g_stable_5g_control_stage_guard.ps1"
Q3_FLASH = ROOT / "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1"


class F75F76FlashRxSilenceTests(unittest.TestCase):
    def test_wrappers_default_to_bounded_uart_silence_abort(self) -> None:
        for script in (F75, F76):
            text = script.read_text(encoding="utf-8")
            self.assertIn("[int]$NoRxAbortSeconds = 300", text)
            self.assertIn('"-NoRxAbortSeconds", [string]$NoRxAbortSeconds', text)
            self.assertIn("NoRxAbortSeconds = $NoRxAbortSeconds", text)

    def test_underlying_flash_script_reports_zero_rx_explicitly(self) -> None:
        text = Q3_FLASH.read_text(encoding="utf-8")
        self.assertIn("[int]$NoRxAbortSeconds = 30", text)
        self.assertIn("OMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES", text)
        self.assertIn('throw "UART_RX_SILENT_ZERO_BYTES"', text)


if __name__ == "__main__":
    unittest.main()
