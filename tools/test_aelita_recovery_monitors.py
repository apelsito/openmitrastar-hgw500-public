#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SUPERVISOR = ROOT / "tools/aelita_recover_uart_then_flash_f66.ps1"
STATUS = ROOT / "tools/status_aelita_radio_goal.ps1"
F66_MONITOR = ROOT / "tools/monitor_f66_flash_then_2g_gate.ps1"
SSH_MONITOR = ROOT / "tools/monitor_router_ssh_then_radio_gate.ps1"
BOOTBASE_FLASH = ROOT / "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_autoboot_atgu_flash.ps1"


class AelitaRecoveryMonitorTests(unittest.TestCase):
    def test_supervisor_waits_for_rx_then_breaks_autoboot_and_starts_f66(self) -> None:
        text = SUPERVISOR.read_text(encoding="utf-8")
        self.assertIn("OPENMITRASTAR_AELITA_RECOVER_UART_FLASH_F66_RECLAIM_021CD489", text)
        self.assertIn('[string]$CurrentLiveCrc32 = "26523198"', text)
        self.assertIn("Wait-UartRxContinuous", text)
        self.assertIn("RX_CONTINUOUS_FIRST_BYTE_SPACE_SENT", text)
        self.assertIn('$serial.Write(" ")', text)
        self.assertIn("[switch]$AllowBlindAutobreak", text)
        self.assertIn("RX_CONTINUOUS_BLIND_SPACE_SENT", text)
        self.assertIn("blind_space_count", text)
        self.assertIn("watch_flash_f66_2g_qguard_until_bootbase.ps1", text)
        self.assertIn("-CurrentLiveCrc32", text)
        self.assertIn("-AllowBlindAutobreak", text)
        self.assertIn("-AllowNoRxRebootAssist", text)
        self.assertIn("verify_f66_offline_preflight.py", text)
        self.assertIn("f66-offline-preflight-before-watch.json", text)
        self.assertIn("F66 offline preflight failed before watcher start", text)

    def test_bootbase_flash_fails_fast_when_uart_rx_is_silent(self) -> None:
        text = BOOTBASE_FLASH.read_text(encoding="utf-8")
        self.assertIn("[int]$NoRxAbortSeconds = 30", text)
        self.assertIn("OMQ3_F45_AUTOBREAK_UART_RX_SILENT_ZERO_BYTES", text)
        self.assertIn("UART_RX_SILENT_ZERO_BYTES", text)
        self.assertIn("[switch]$AllowBlindAutobreak", text)
        self.assertIn("[int]$BlindAtguAfterNoRxSeconds = 0", text)
        self.assertIn("Send-BlindAtguSequence", text)
        self.assertIn("$script:omLastBlindAtguAt = [DateTime]::MinValue", text)
        self.assertIn("OMQ3_F45_AUTOBREAK_BLIND_ATGU_SENT", text)
        self.assertIn("OMQ3_F45_AUTOBREAK_BLIND_ATGU_SPACE_SENT", text)
        self.assertIn("[switch]$AllowNoRxRebootAssist", text)
        self.assertIn("$AllowBlindAutobreak -and -not $bootbaseSeen", text)
        self.assertIn("$BlindAtguAfterNoRxSeconds -gt 0", text)
        self.assertIn("$script:omLastBlindAtguAt).TotalSeconds -ge $BlindAtguAfterNoRxSeconds", text)
        self.assertIn("$AllowNoRxRebootAssist", text)

    def test_f66_wrappers_propagate_blind_autobreak_controls(self) -> None:
        wrapper = (ROOT / "tools/flash_f66_2g_qguard.ps1").read_text(encoding="utf-8")
        watcher = (ROOT / "tools/watch_flash_f66_2g_qguard_until_bootbase.ps1").read_text(encoding="utf-8")
        for text in (wrapper, watcher):
            self.assertIn("[switch]$AllowBlindAutobreak", text)
            self.assertIn("[switch]$AllowNoRxRebootAssist", text)
            self.assertIn('if ($AllowBlindAutobreak) { $args += "-AllowBlindAutobreak" }', text)
            self.assertIn('if ($AllowNoRxRebootAssist) { $args += "-AllowNoRxRebootAssist" }', text)

    def test_f66_and_router_monitors_run_radio_gate_after_recovery(self) -> None:
        f66 = F66_MONITOR.read_text(encoding="utf-8")
        ssh = SSH_MONITOR.read_text(encoding="utf-8")
        for text in (f66, ssh):
            self.assertIn("post_flash_f65_radio_gate.ps1", text)
            self.assertIn("-Run2gProbe", text)
            self.assertIn("-Run5gProbe", text)
            self.assertIn("-Min2gMbps", text)
            self.assertIn("-FiveGProfile", text)
            self.assertIn("-FiveGSeconds", text)
        self.assertIn("F66 state=$state", f66)
        self.assertIn("state -eq \"pass\"", f66)
        self.assertIn("TCP/22 is reachable; starting radio gate", ssh)
        self.assertIn("run_5g_probe", f66)
        self.assertIn("run_5g_probe", ssh)

    def test_status_aggregator_lists_all_active_monitor_families(self) -> None:
        text = STATUS.read_text(encoding="utf-8")
        self.assertIn("monitor_f66_flash_then_2g_gate", text)
        self.assertIn("monitor_router_ssh_then_radio_gate", text)
        self.assertIn("status_f93_f95_chain.ps1", text)
        self.assertIn("flash_f93_2g_ht40sgi", text)
        self.assertIn("flash_f95_2g_mcs15", text)
        self.assertIn("monitor_f93_restore_then_f95", text)
        self.assertIn("F93_F95_CHAIN_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING", text)
        self.assertIn("F93_F95_UART_RX_ZERO_CURRENT_CHAIN", text)
        self.assertIn("monitor_f125_flash_then_assoc_only_5g", text)
        self.assertIn("f125_5g_assoc_monitor", text)
        self.assertIn("F125_UART_RX_ZERO_CURRENT_ATTEMPT", text)
        self.assertIn("WATCH_F125_FLASH_THEN_5G_ASSOC_ONLY", text)
        self.assertIn("monitor_f126_flash_then_assoc_only_5g", text)
        self.assertIn("f126_5g_assoc_monitor", text)
        self.assertIn("F126_UART_RX_ZERO_CURRENT_ATTEMPT", text)
        self.assertIn("F126_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING", text)
        self.assertIn("WATCH_F126_FLASH_THEN_5G_ASSOC_ONLY", text)
        self.assertIn("WATCH_F93_RESTORE_THEN_F95_CHAIN", text)
        self.assertIn("f93_f95_chain", text)
        self.assertIn("f95_candidate", text)
        self.assertIn("monitor_f7[678]_flash_then_stage_gate", text)
        self.assertIn("f78-flash-pass-then-stage-gate", text)
        self.assertIn("F78_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING", text)
        self.assertIn("F78_UART_RX_ZERO_CURRENT_ATTEMPT", text)
        self.assertIn("WATCH_F78_FLASH", text)
        self.assertIn("f77-flash-pass-then-stage-gate", text)
        self.assertIn("F77_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING", text)
        self.assertIn("F77_UART_RX_ZERO_CURRENT_ATTEMPT", text)
        self.assertIn("WATCH_F77_FLASH", text)
        self.assertIn("WATCH_F76_FLASH", text)
        self.assertIn("F76_FLASH_WATCHER_STALE", text)
        self.assertIn("F76_FLASH_UART_RX_ZERO_WAITING_POWER_CYCLE_OR_WIRING", text)
        self.assertIn("f78_stage_monitor", text)
        self.assertIn("f78_candidate", text)
        self.assertIn("f77_stage_monitor", text)
        self.assertIn("f77_candidate", text)
        self.assertIn("f76_stage_monitor", text)
        self.assertIn("f76_candidate", text)
        self.assertIn("F76_UART_RX_ZERO_LAST_ATTEMPT", text)
        self.assertIn("physical_path_blocked_or_power_cycle_needed", text)
        self.assertIn("uart_rx_zero_observed", text)
        self.assertIn("uart_rx_zero_terminal_marker", text)
        self.assertIn("uart_rx_zero_long", text)
        self.assertIn("blind_space_count", text)
        self.assertIn("f66_2g_monitor", text)
        self.assertIn("router_ssh_monitor", text)
        self.assertIn("stale_attempt_running", text)
        self.assertIn("Get-SerialTriage", text)
        self.assertIn("Compress-CommandLine", text)
        self.assertIn("Get-StatusBoundProcesses", text)
        self.assertIn("status_bound_processes", text)
        self.assertIn("f78_status_current_process", text)
        self.assertIn("Get-LatestExecutedFlashDir", text)
        self.assertIn("uart_triage", text)
        self.assertIn("UART_RX_SILENT_DESPITE_ACTIVE_AUTOBREAK", text)
        self.assertIn("PHYSICAL_UART_RX_PATH_BLOCKED", text)
        self.assertIn("physical_path_blocked", text)
        self.assertIn("recommended_action", text)
        self.assertIn("silent_seconds", text)
        self.assertIn("active_autobreak_seconds", text)
        self.assertIn("[string]$OutputPath", text)
        self.assertIn("Set-Content -Encoding ascii -LiteralPath $resolvedOutput", text)
        self.assertIn("rx_logs", text)
        self.assertIn("uart.raw.bin", text)
        self.assertIn("WAIT_PHYSICAL_UART_RX_PATH_OR_POWER_CYCLE", text)

    def test_f76_monitor_stops_on_stale_running_dead_flash_process(self) -> None:
        text = (ROOT / "tools/monitor_f76_flash_then_stage_gate.ps1").read_text(encoding="utf-8")
        self.assertIn("Test-ProcessAliveById", text)
        self.assertIn('"running_foreground"', text)
        self.assertIn('"background_armed"', text)
        self.assertIn("process_id", text)
        self.assertIn("current_process_id", text)
        self.assertIn("Test-F76FlashUartRxZero", text)
        self.assertIn("BLOCKED_BY_FLASH_UART_RX_ZERO", text)
        self.assertIn("failure_reason", text)
        self.assertIn("BLOCKED_BY_FLASH_STALE_RUNNING_PROCESS_DEAD", text)
        self.assertIn("blocked_by_flash_stale_running", text)

    def test_status_aggregator_prefers_background_child_pid(self) -> None:
        text = STATUS.read_text(encoding="utf-8")
        self.assertIn("$f76Pid = $null", text)
        self.assertIn("$f75Pid = $null", text)
        self.assertIn("process_id", text)
        self.assertIn("current_process_id", text)


if __name__ == "__main__":
    unittest.main()
