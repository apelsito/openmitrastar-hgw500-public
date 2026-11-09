#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FLASH = ROOT / "tools/recover_flash_f74_radio5_rf_before_l3.ps1"
POSTGATE = ROOT / "tools/recover_flash_f74_then_postgate.ps1"
WATCHER = ROOT / "tools/watch_flash_f74_until_bootbase.ps1"
GATE = ROOT / "tools/post_flash_f65_radio_gate.ps1"


class F74FlashWrapperTests(unittest.TestCase):
    def test_flash_wrapper_is_pinned_to_f74_candidate(self) -> None:
        text = FLASH.read_text(encoding="utf-8")
        self.assertIn("q3-persistent-composite-f74-5g-rf-before-l3\\build", text)
        self.assertIn("openmitrastar-linux510-q3-persistent-f74-5g-rf-before-l3-LZMA-OFFLINE-NO-FLASH", text)
        self.assertIn("56962c97dbb59b136f0a2cc71a4be7d32c40b345f15b34bac0c99c23ee5ee009", text)
        self.assertIn("5612368", text)
        self.assertIn("33b885e7", text)
        self.assertIn("67228a88", text)
        self.assertIn("OPENMITRASTAR_Q3_F74_RADIO5_RF_BEFORE_L3_MTD4_FLASH_56962C97", text)
        self.assertIn('[string]$CurrentLiveCrc32 = "484fd8c6"', text)

    def test_postgate_wrapper_propagates_reboot_and_probe_flags(self) -> None:
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
            "Run2gProbe",
            "Run5gProbe",
            "monitor_router_ssh_then_radio_gate.ps1",
        ):
            self.assertIn(needle, text)

    def test_watcher_launches_f74_postgate_and_stops_on_uart_silence(self) -> None:
        text = WATCHER.read_text(encoding="utf-8")
        self.assertIn("openmitrastar.f74-flash-watch-status/v1", text)
        self.assertIn("recover_flash_f74_then_postgate.ps1", text)
        self.assertIn("OPENMITRASTAR_Q3_F74_RADIO5_RF_BEFORE_L3_MTD4_FLASH_56962C97", text)
        self.assertIn("blocked_uart_rx_silent_zero_bytes", text)
        self.assertIn("UART_RX_SILENT_ZERO_BYTES", text)
        self.assertIn("physical power-cycle/reset required", text)
        self.assertIn("candidate_sha256", text)
        self.assertIn("full_slot_crc32", text)
        self.assertIn('[string]$CurrentLiveCrc32 = "484fd8c6"', text)
        self.assertIn("[ValidateRange(0, 300)]", text)
        self.assertIn("[ValidateRange(60, 21600)]", text)

    def test_postgate_uses_native_quantenna_control_not_qcsapi(self) -> None:
        text = GATE.read_text(encoding="utf-8")
        self.assertIn("SECTION_QTN_NATIVE_CONTROL", text)
        self.assertIn("OMQTN_NATIVE_OK", text)
        self.assertIn("OMQTN_HOSTAPD_QTN_PONG", text)
        self.assertIn("native_ap_ready_isolated", text)
        self.assertIn("iwpriv-qtn wifi0 get_mode", text)
        self.assertIn("hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping", text)
        self.assertNotIn("call_qcsapi get_status wifi0", text)


if __name__ == "__main__":
    unittest.main()
