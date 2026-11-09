#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import hashlib
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "monitor_2g_live_traffic.py"
SPEC = importlib.util.spec_from_file_location("monitor_2g_live_traffic", TOOL)
assert SPEC and SPEC.loader
MONITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MONITOR)

WAITER_TOOL = ROOT / "tools" / "wait_w2_2g_client.py"
WAITER_SPEC = importlib.util.spec_from_file_location("wait_w2_2g_client", WAITER_TOOL)
assert WAITER_SPEC and WAITER_SPEC.loader
WAITER = importlib.util.module_from_spec(WAITER_SPEC)
WAITER_SPEC.loader.exec_module(WAITER)


class Monitor2GLiveTrafficTests(unittest.TestCase):
    def test_sample_contract_includes_full_tx3_gate(self) -> None:
        line = (
            "OM2G seq=12 phase=during uptime=900 state=ENABLED assoc=1 authorized=1 "
            "sta_tx_retries=2 sta_tx_failed=0 wifi_rx=10 wifi_tx=20 "
            "wifi_rx_bytes=1000 wifi_tx_bytes=2000 wifi_rxerr=0 wifi_txerr=0 "
            "br_rx=11 br_tx=21 br_rx_bytes=1100 br_tx_bytes=2100 "
            "eth_rx=12 eth_tx=22 eth_rx_bytes=1200 eth_tx_bytes=2200 "
            "irq28=300 irq20=400 be_boot_max=4 be_run_max=73 be_events=8 "
            "be_close_events=3 be_doorbell_events=5 be_sw_rp=10 be_sw_wp=14 be_hw_rp=10 be_hw_wp=14 "
            "fatal_run=0 carrier=1 ssh_alive=1"
        )
        match = MONITOR.LINE_RE.fullmatch(line)
        self.assertIsNotNone(match)
        self.assertEqual(match.group("phase"), "during")
        self.assertEqual(match.group("be_run_max"), "73")
        self.assertEqual(match.group("sta_tx_retries"), "2")
        self.assertEqual(match.group("be_hw_wp"), "14")
        self.assertEqual(match.group("be_doorbell_events"), "5")

    def test_remote_command_is_read_only_and_captures_required_surfaces(self) -> None:
        command = MONITOR.remote_command(180, 1, "auto", 10, 10)
        for required in (
            "hostapd_cli", "all_sta", "station dump", "/proc/interrupts",
            "/sys/class/net/wlan0/statistics", "queue=1", "q=1",
            "pci-tx-queued", "tx retries:",
            "OMRTLTXCLOSE", "tx-doorbell-post", "be_doorbell_events", "qidx_hex",
            "hw_rp=", "tx failed:", "ssh_alive=1", "phase=before", "phase=during",
            "phase=after", '"$assoc" != "$last_assoc"',
            '"$authorized" != "$last_authorized"',
        ):
            self.assertIn(required, command)
        for forbidden in (
            "insmod ", "rmmod ", "reboot", "flash_erase", "fw_setenv",
            "hostapd_cli reload", "hostapd_cli terminate",
        ):
            self.assertNotIn(forbidden, command)

    def test_monitor_caps_untrusted_ssh_output_and_binds_raw_log(self) -> None:
        source = TOOL.read_text(encoding="utf-8")
        self.assertIn("--max-output-bytes", source)
        self.assertIn("remote-output-limit-exceeded", source)
        self.assertIn('stderr.read(65_536)', source)
        self.assertIn('"raw_log_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest()', source)
        self.assertIn('"producer": "tools/monitor_2g_live_traffic.py"', source)

    def test_counter_reset_does_not_create_negative_or_false_failed_delta(self) -> None:
        samples = [
            {"sta_tx_failed": 8},
            {"sta_tx_failed": 0},
            {"sta_tx_failed": 0},
        ]
        self.assertEqual(MONITOR.counter_increase(samples, "sta_tx_failed"), 0)

    def test_peak_rate_uses_during_samples_and_counter_progress(self) -> None:
        samples = [
            {"phase": "before", "uptime": 0, "wifi_tx_bytes": 0},
            {"phase": "during", "uptime": 2, "wifi_tx_bytes": 0},
            {"phase": "during", "uptime": 4, "wifi_tx_bytes": 2_000_000},
            {"phase": "after", "uptime": 6, "wifi_tx_bytes": 2_000_000},
        ]
        self.assertEqual(
            MONITOR.peak_rate_mbps(samples, "wifi_tx_bytes", phase="during"),
            8.0,
        )

    def test_wrapper_binds_exact_tx3_and_never_uses_uart(self) -> None:
        wrapper = (ROOT / "tools" / "run_w2_2g_tx3_gate.ps1").read_text(encoding="utf-8")
        self.assertIn("38930e350c2da27c00d5a3dff693dfab967c8cff1255904ebfc4897314bd203e", wrapper)
        self.assertIn("RAM-ONLY-NO-FLASH-READ-ONLY-SSH", wrapper)
        self.assertIn("uart_opened = $false", wrapper)
        self.assertNotIn("COM3", wrapper)

    def test_tx7_wrapper_binds_exact_hybrid_image_via_readonly_candidate_gate(self) -> None:
        wrapper = (ROOT / "tools" / "run_w2_2g_tx7_gate.ps1").read_text(encoding="utf-8")
        self.assertIn("run_w2_2g_candidate_gate.ps1", wrapper)
        self.assertIn("verify_post_tx7_recovery_result.py", wrapper)
        self.assertIn("RecoveryResultJson", wrapper)
        self.assertIn("OM2G_TX7_REQUIRES_RECOVERY_RESULT_JSON=1", wrapper)
        self.assertIn("linux510-w2-2g-parity-tx7-hybrid32-v1-RAM-TEST-NO-FLASH.bin", wrapper)
        self.assertIn("d547524667d3c1f59b4a4dbf891c1271fe837ee3b5649682a6095492a45781a3", wrapper)
        self.assertIn("-ExpectedBytes 4330928", wrapper)
        self.assertIn('"TX7"', wrapper)
        self.assertNotIn("COM3", wrapper)
        self.assertNotIn("reboot", wrapper.lower())
        self.assertNotIn("flash_erase", wrapper)
        self.assertNotIn("fw_setenv", wrapper)

    def test_tx7_wrapper_plan_only_advertises_recovery_result_requirement(self) -> None:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "tools" / "run_w2_2g_tx7_gate.ps1"),
                "-PlanOnly",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OM2G_CANDIDATE_GATE_PLAN_PASS=1", proc.stdout)
        self.assertIn("OM2G_TX7_REQUIRES_RECOVERY_RESULT_JSON=1", proc.stdout)

    def test_tx7_auto_wrapper_waits_for_client_before_gate_and_stays_readonly(self) -> None:
        wrapper = (ROOT / "tools" / "run_w2_2g_tx7_auto_gate.ps1").read_text(encoding="utf-8")
        self.assertIn("wait_w2_2g_client.py", wrapper)
        self.assertIn("run_w2_2g_tx7_gate.ps1", wrapper)
        self.assertIn("verify_post_tx7_recovery_result.py", wrapper)
        self.assertIn("--require-authorized", wrapper)
        self.assertIn("OM2G_TX7_AUTO_GATE_CLIENT_READY", wrapper)
        self.assertIn("linux510-w2-2g-parity-tx7-hybrid32-v1-RAM-TEST-NO-FLASH.bin", wrapper)
        self.assertIn("d547524667d3c1f59b4a4dbf891c1271fe837ee3b5649682a6095492a45781a3", wrapper)
        self.assertNotIn("COM3", wrapper)
        self.assertNotIn("reboot", wrapper.lower().replace("reboot = $false", ""))
        self.assertNotIn("flash_erase", wrapper)
        self.assertNotIn("fw_setenv", wrapper)

    def test_tx7_auto_wrapper_plan_only_is_executable_without_hardware(self) -> None:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "tools" / "run_w2_2g_tx7_auto_gate.ps1"),
                "-PlanOnly",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OM2G_TX7_AUTO_GATE_PLAN_PASS=1", proc.stdout)
        self.assertIn("OM2G_TX7_AUTO_GATE_REQUIRES_RECOVERY_RESULT_JSON=1", proc.stdout)
        self.assertNotIn("OM2G_TX7_AUTO_GATE_WAITING", proc.stdout)

    def test_waiter_line_parser_and_remote_command_are_readonly(self) -> None:
        line = (
            "OM2G_WAIT seq=0 uptime=2331 state=ENABLED assoc=1 "
            "authorized=1 kernel_sta=1 kernel_authenticated=1 "
            "kernel_associated=1 kernel_authorized=1 carrier=1 "
            "ctrl=/run/openmitrastar/radio2g/ctrl"
        )
        sample = WAITER.parse_sample(line, 7)
        self.assertEqual(sample["seq"], 7)
        self.assertEqual(sample["assoc"], 1)
        self.assertEqual(sample["authorized"], 1)
        self.assertEqual(sample["kernel_associated"], 1)
        command = WAITER.remote_command("auto")
        for required in (
            "hostapd_cli", "all_sta", "/sys/class/net/wlan0/carrier",
            "OM2G_WAIT", "/run/openmitrastar/radio2g/ctrl",
        ):
            self.assertIn(required, command)
        for forbidden in (
            "insmod ", "rmmod ", "reboot", "flash_erase", "fw_setenv",
            "hostapd_cli reload", "hostapd_cli terminate",
        ):
            self.assertNotIn(forbidden, command)

    def test_tx7_wrapper_execution_requires_verified_recovery_result(self) -> None:
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(ROOT / "tools" / "run_w2_2g_tx7_gate.ps1"),
                "-Seconds",
                "1",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("RecoveryResultJson", proc.stderr)
        self.assertNotIn("OM2G_CANDIDATE_GATE_ARMED", proc.stdout)

    def test_candidate_wrapper_evaluates_summary_without_mutations(self) -> None:
        wrapper = (ROOT / "tools" / "run_w2_2g_candidate_gate.ps1").read_text(encoding="utf-8")
        self.assertIn("evaluate_w2_2g_live_traffic.py", wrapper)
        self.assertIn("gate-result.json", wrapper)
        self.assertIn("uart_opened = $false", wrapper)
        self.assertIn("module_reload = $false", wrapper)
        self.assertIn("reboot = $false", wrapper)
        self.assertIn("flash = $false", wrapper)


if __name__ == "__main__":
    unittest.main()
