#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PS = ROOT / "tools/run_qtn_5g_windows_oracle.ps1"
EVALUATOR = ROOT / "tools/evaluate_qtn_5g_windows_oracle.py"
SERVER = ROOT / "tools/openmitrastar_l2_speed_server.py"
TASK = ROOT / "tools/start_qtn_5g_windows_oracle_task.ps1"
SERVER_START = ROOT / "tools/start_qtn_5g_oracle_server.ps1"

spec = importlib.util.spec_from_file_location("qtn_5g_eval", EVALUATOR)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def pass_windows() -> dict:
    return {
        "execution_error": None,
        "expected_bssid": None,
        "test": {
            "connected": True,
            "bssid_match": None,
            "dhcp": True,
            "ipv4": {
                "dhcp_enabled": True,
                "ipv4": "192.168.1.70",
                "gateway": "192.168.1.1",
                "dns_servers": ["192.168.1.1"],
            },
            "router_ping": {"pass": True},
            "controller_ping": {"pass": True},
            "dns_ok": True,
            "internet_https": {"pass": True, "bytes": 5430},
            "ap_to_client": {"pass": True, "bytes": 32 * 1024 * 1024, "mbps": 42.0},
            "client_to_ap": {"pass": True, "bytes": 32 * 1024 * 1024, "mbps": 38.0},
            "soak": {"requested_seconds": 600, "samples": 120, "connected_samples": 120, "disconnects": 0},
        },
        "restore": {"connected": True, "ipv4": {"ipv4": "192.168.1.43"}},
    }


def pass_router() -> dict:
    return {
        "complete": True,
        "management_lost": False,
        "health_failure": False,
        "association_observed": True,
        "duration_observed_seconds": 600.2,
        "samples_observed": 601,
        "wifi_rx_delta": 900,
        "wifi_tx_delta": 1100,
        "eth_rx_delta": 1200,
        "eth_tx_delta": 1000,
        "irq8_delta": 4500,
        "irq20_delta": 800,
    }


class Qtn5gWindowsOracleGateTests(unittest.TestCase):
    def test_pass_requires_both_directions_and_restore(self) -> None:
        result = module.evaluate(pass_windows(), pass_router())
        self.assertEqual("PASS", result["status"])
        self.assertTrue(result["directions"]["ap_to_client"])
        self.assertTrue(result["directions"]["client_to_ap"])
        self.assertTrue(result["claims"]["primary_network_restored"])

    def test_each_direction_is_correlated_with_router_counters(self) -> None:
        router = pass_router()
        router["wifi_tx_delta"] = 0
        result = module.evaluate(pass_windows(), router)
        self.assertIn("ap_to_client_router_correlation", result["failures"])
        router = pass_router()
        router["eth_tx_delta"] = 0
        result = module.evaluate(pass_windows(), router)
        self.assertIn("client_to_ap_router_correlation", result["failures"])

    def test_dhcp_dns_https_and_performance_fail_closed(self) -> None:
        for key, failure in (("dhcp", "windows_dhcp"), ("dns_ok", "windows_dns")):
            windows = pass_windows()
            windows["test"][key] = False
            self.assertIn(failure, module.evaluate(windows, pass_router())["failures"])
        windows = pass_windows()
        windows["test"]["internet_https"]["pass"] = False
        self.assertIn("windows_internet_https", module.evaluate(windows, pass_router())["failures"])
        windows = pass_windows()
        windows["test"]["ap_to_client"]["mbps"] = 1.0
        self.assertIn("ap_to_client_mbps", module.evaluate(windows, pass_router())["failures"])

    def test_soak_disconnect_or_restore_failure_is_fatal(self) -> None:
        windows = pass_windows()
        windows["test"]["soak"]["disconnects"] = 1
        self.assertIn("windows_disconnects", module.evaluate(windows, pass_router())["failures"])
        windows = pass_windows()
        windows["restore"]["connected"] = False
        self.assertIn("windows_primary_network_restored", module.evaluate(windows, pass_router())["failures"])

    def test_powershell_defaults_to_dry_run_and_restores_in_finally(self) -> None:
        source = PS.read_text(encoding="utf-8")
        for marker in (
            "if (-not $Execute)",
            "[switch]$AssociationOnly",
            "OPENMITRASTAR_QTN_5G_WINDOWS_ORACLE_RAM_ONLY",
            "finally {",
            "Connect-SsidWithRetry $WifiInterface $RestoreSsid",
            "OMQTN5G_WINDOWS_ORACLE_CAPTURE_COMPLETE=1",
            "association_only={2}",
            "--request PUT",
            "CURLE_INTERFACE_FAILED",
            "for ($attempt = 1; $attempt -le 5; $attempt++)",
            "replyCount",
            "loss_percent",
            "Connect-SsidWithRetry",
            "router_ping_static_neighbor",
            "New-NetNeighbor",
            "Remove-NetNeighbor",
            "Respuesta desde|Reply from",
            "[regex]::Escape($TargetIp)",
            "(?:AP\\s+)?BSSID",
        ):
            self.assertIn(marker, source)
        self.assertNotIn("--interface $SourceIp", source)
        for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "reboot", "COM3"):
            self.assertNotIn(forbidden, source)

    def test_powershell_dry_run_has_no_network_mutation(self) -> None:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(PS)],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OMQTN5G_WINDOWS_ORACLE_DRY_RUN_PASS=1", proc.stdout)

    def test_powershell_supports_short_association_only_dry_run(self) -> None:
        proc = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(PS), "-AssociationOnly", "-IsolatedL3", "-SoakSeconds", "0",
            ],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OMQTN5G_WINDOWS_ORACLE_DRY_RUN_PASS=1", proc.stdout)
        self.assertIn('"association_only":  true', proc.stdout)

    def test_speed_server_has_bounded_get_and_put_paths(self) -> None:
        source = SERVER.read_text(encoding="utf-8")
        self.assertIn('self.path != "/upload.bin"', source)
        self.assertIn("def do_PUT", source)
        self.assertIn("def do_POST", source)
        self.assertIn("max_upload_bytes", source)
        self.assertIn("direction=ap-to-client", source)
        self.assertIn("direction=client-to-ap", source)

    def test_scheduled_task_survives_network_switch_and_keeps_restore_contract(self) -> None:
        source = TASK.read_text(encoding="utf-8")
        for marker in (
            "if (-not $Execute)",
            "[switch]$AssociationOnly",
            "OPENMITRASTAR_QTN_5G_WINDOWS_ORACLE_TASK_RAM_ONLY",
            "New-ScheduledTaskPrincipal -UserId 'SYSTEM'",
            "watchdog_preflight = 'required-as-SYSTEM-before-oracle'",
            "restore_wifi_oracle_watchdog.ps1",
            "SYSTEM restore-watchdog preflight produced no status file",
            "Start-ScheduledTask",
            '$oracleCommand += " -AssociationOnly"',
        ):
            self.assertIn(marker, source)
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(TASK)],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OMQTN5G_WINDOWS_ORACLE_TASK_DRY_RUN_PASS=1", proc.stdout)

    def test_scheduled_task_supports_short_association_only_dry_run(self) -> None:
        proc = subprocess.run(
            [
                "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
                "-File", str(TASK), "-AssociationOnly", "-IsolatedL3", "-SoakSeconds", "0",
            ],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OMQTN5G_WINDOWS_ORACLE_TASK_DRY_RUN_PASS=1", proc.stdout)
        self.assertIn('"association_only":  true', proc.stdout)

    def test_controller_server_launcher_defaults_to_plan_only(self) -> None:
        source = SERVER_START.read_text(encoding="utf-8")
        self.assertIn("if (-not $Execute)", source)
        self.assertIn("firewall_changes = $false", source)
        self.assertIn("openmitrastar_l2_speed_server.py", source)
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(SERVER_START)],
            cwd=ROOT, capture_output=True, text=True, timeout=20, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OMQTN5G_ORACLE_SERVER_DRY_RUN_PASS=1", proc.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
