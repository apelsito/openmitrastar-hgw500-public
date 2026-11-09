#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_qtn_5g_aelita_one_shot.py"
STARTER = ROOT / "tools/start_qtn_5g_windows_oracle_task.ps1"
WATCHDOG = ROOT / "tools/restore_wifi_oracle_watchdog.ps1"


class Qtn5gAelitaOneShotTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SCRIPT.read_text(encoding="utf-8")
        cls.starter = STARTER.read_text(encoding="utf-8")

    def test_dry_run_is_exact_and_network_free(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=ROOT,
            text=True, capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        marker = "OMQTN5G_AELITA_ONE_SHOT_DRY_RUN_PASS=1"
        self.assertIn(marker, proc.stdout)
        payload = json.loads(proc.stdout[:proc.stdout.index(marker)])
        self.assertEqual("AELITA@192.168.1.63", payload["oracle"])
        self.assertEqual("ISOLATED_L3_READY_AFTER_ROUTER_RECOVERY", payload["runtime_compatibility"])
        self.assertIn("stable_2g_current_gate", payload["runtime_snapshot"])
        self.assertIn("192.168.77.1/24", payload["topology"])
        self.assertFalse(payload["network_changed_now"])
        self.assertIn("--stable-2g-ack OPENMITRASTAR_2G_STABLE_FOR_QTN5G", payload["exact_command"])
        self.assertIn("--seconds 120", payload["exact_command"])
        self.assertIn("--tx-path-trace", payload["exact_command"])

    def test_v6_scheduler_diag_dry_run_pins_exact_qdrv(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--v6-scheduler-diag"], cwd=ROOT,
            text=True, capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        marker = "OMQTN5G_AELITA_ONE_SHOT_DRY_RUN_PASS=1"
        self.assertIn(marker, proc.stdout)
        payload = json.loads(proc.stdout[:proc.stdout.index(marker)])
        self.assertTrue(payload["v6_scheduler_diag"])
        self.assertFalse(payload["tx_path_trace"])
        self.assertIn("--v6-scheduler-diag", payload["exact_command"])
        self.assertEqual(
            "5b9ae80e5121c4b00965ce4716ad80285f1b599e29845e8efbf938a79600df35",
            payload["v6_contract"]["qdrv_artifact_sha256"],
        )
        self.assertFalse(payload["v6_contract"]["product_integration"]["enabled_service"])

    def test_oracle_identity_and_host_key_are_pinned(self) -> None:
        for marker in (
            'ORACLE_HOST = "192.168.1.63"',
            'ORACLE_USER = "AELITA"',
            "oracle_rsa_unencrypted",
            "client.load_host_keys",
            "paramiko.RejectPolicy()",
            "this gate is pinned to AELITA@192.168.1.63",
        ):
            self.assertIn(marker, self.source)
        self.assertNotIn("AutoAddPolicy", self.source)

    def test_reinforced_watchdog_is_staged_and_started_first(self) -> None:
        for marker in (
            "restore_wifi_oracle_watchdog.ps1",
            "OpenMitraStar-QTN5G-Restore",
            "watchdog_preflight = 'passed-as-SYSTEM'",
            "New-ScheduledTaskPrincipal -UserId 'SYSTEM'",
            "SYSTEM restore-watchdog preflight produced no status file",
            "-RepetitionInterval (New-TimeSpan -Minutes 2)",
            "-StartWhenAvailable -WakeToRun",
        ):
            self.assertIn(marker, self.starter)
        self.assertLess(
            self.starter.index("Register-ScheduledTask -TaskName $watchdogTaskName"),
            self.starter.index("Register-ScheduledTask -TaskName $taskName"),
        )
        self.assertLess(
            self.starter.index("Start-ScheduledTask -TaskName $watchdogTaskName"),
            self.starter.index("Start-ScheduledTask -TaskName $taskName"),
        )

    def test_one_shot_has_router_and_oracle_rollback_boundaries(self) -> None:
        for marker in (
            "qtn_runner.arm_rollback",
            "qtn_runner.stage_safe_overlay",
            "prepare_remote_radio5_runtime(args.router_host)",
            "OMQTN5G_RUNTIME_PREP_PASS",
            "qtn_runner.commit",
            "qtn_runner.collect_radio5_failure_snapshot",
            'qtn_runner.stop_radio5(args.router_host, "aelita-one-shot-failed")',
            "wait_oracle_result",
            "stop_server(server)",
            "monitor_seconds = min(args.seconds + 300, 900)",
            "qtn_runner.arm_rollback(args.router_host, 240, run_id)",
            "qtn_runner.arm_rollback(args.router_host, monitor_seconds + 300, run_id)",
            "qtn_runner.prepare_radio5_gate(args.router_host, run_id)",
            "server = start_server(args.controller_ip, 8081)",
            "qtn_runner.cleanup_safe_overlay(args.router_host)",
            "configure_tx_path_trace",
            "configure_v6_scheduler_diag",
            "--v6-scheduler-diag",
            "qtn_5g_v62_scheduler_contract.py",
            "TRACE_MANIFEST_SHA",
            "TX path trace manifest does not match",
            "OMQDRVTXPATH stage=",
        ):
            self.assertIn(marker, self.source)
        for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot_boot_ramssh"):
            self.assertNotIn(forbidden, self.source)

        qtn_runner = (ROOT / "tools/run_qtn_w3_tx7_client_traffic.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("Q3_RADIO5_TQE_RING_ENTRIES=512", qtn_runner)
        self.assertIn("OM_RADIO5_TQE512_FEATURE", qtn_runner)
        main = self.source[self.source.index("def main()") :]
        self.assertLess(
            main.index("qtn_runner.collect_radio5_failure_snapshot(args.router_host, failure_log, run_id)"),
            main.index('qtn_runner.stop_radio5(args.router_host, "aelita-one-shot-failed")'),
        )

    def test_trace_artifact_keeps_the_a4a4_runtime_profile_contract(self) -> None:
        qtn_runner = (ROOT / "tools/run_qtn_w3_tx7_client_traffic.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("QDRV_PROFILE_SHA256 = SAFE_QDRV_SHA256", qtn_runner)
        self.assertIn("awk -F= -v q={QDRV_PROFILE_SHA256}", qtn_runner)
        self.assertIn('check "$root/upload/qdrv.ko" {QDRV_SHA256}', qtn_runner)

    def test_watchdog_window_is_after_bounded_oracle_runtime(self) -> None:
        self.assertIn("[ValidateRange(2, 30)][int]$RestoreWatchdogMinutes = 22", self.starter)
        self.assertIn("-ExecutionTimeLimit (New-TimeSpan -Seconds ($SoakSeconds + 600))", self.starter)

    def test_prestart_rollback_and_speed_server_order(self) -> None:
        main = self.source[self.source.index("def main()") :]
        self.assertLess(
            main.index("qtn_runner.arm_rollback(args.router_host, 240, run_id)"),
            main.index("qtn_runner.start_radio5(args.router_host, run_id)"),
        )
        self.assertLess(
            main.index("server = start_server(args.controller_ip, 8081)"),
            main.index("start_oracle_task("),
        )

    def test_current_watchdog_contract_still_parses(self) -> None:
        self.assertTrue(WATCHDOG.is_file())
        escaped = str(WATCHDOG).replace("'", "''")
        command = (
            "$e=$null;$t=$null;"
            f"[System.Management.Automation.Language.Parser]::ParseFile('{escaped}',[ref]$t,[ref]$e)|Out-Null;"
            "if($e.Count){$e|ForEach-Object{$_.ToString()};exit 1}"
        )
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
            text=True, capture_output=True, timeout=20, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)


if __name__ == "__main__":
    unittest.main(verbosity=2)
