#!/usr/bin/env python3

import pathlib
import json
import re
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools" / "run_openmitrastar_ap_isolated_gate.ps1"
WATCHDOG = ROOT / "tools" / "openmitrastar_ap_isolated_watchdog.sh"


class IsolatedApGateOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runner = RUNNER.read_text(encoding="utf-8")
        cls.watchdog = WATCHDOG.read_text(encoding="utf-8")

    def test_runner_is_dry_run_by_default_and_fixed_isolated(self):
        self.assertIn('[switch]$ExecuteRam', self.runner)
        self.assertNotIn('[string]$Topology', self.runner)
        self.assertIn('$FixedHost = "192.168.1.200"', self.runner)
        self.assertIn('$FixedWlan = "192.168.2.1"', self.runner)
        self.assertIn('$FixedClient = "192.168.2.2"', self.runner)
        self.assertIn('--topology isolated', self.runner)
        self.assertIn('bridge_allowed = $false', self.runner)
        self.assertIn('five_ghz_touched = $false', self.runner)

    def test_runner_requires_local_watchdog_before_ap_launch(self):
        arm = self.runner.index('$watchdogLaunch =')
        ap = self.runner.index('$launch =', arm + 1)
        self.assertLess(arm, ap)
        self.assertIn('scope = "router-local"', self.runner)
        self.assertIn('rollback_transport = "none"', self.runner)
        self.assertIn('OMAP_WATCHDOG_ARMED', self.runner)

    def test_runner_captures_all_pass_markers(self):
        for marker in (
            'state=ENABLED',
            '[AUTHORIZED]',
            'OMAP_SMOKE_PASS topology=isolated',
            'ping=3/3',
            'OMAP_BRIDGE_ABSENT=1',
        ):
            self.assertIn(marker, self.runner)

    def test_auto_discovery_is_opt_in_and_fail_closed(self):
        self.assertIn('[switch]$AutoDiscoverClient', self.runner)
        self.assertIn('Use either -ClientMac or -AutoDiscoverClient, never both', self.runner)
        self.assertIn('hostapd_cli -p $RemoteState/ctrl -i wlan0 all_sta', self.runner)
        self.assertIn('Auto-discovery refused multiple stations', self.runner)
        self.assertIn('$finalSnapshot.All.Count -ne 1', self.runner)
        self.assertIn('$finalSnapshot.Authorized.Count -ne 1', self.runner)

    def test_station_parser_unique_authorized_and_multiple(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell not available")
        runner_path = str(RUNNER).replace("'", "''")
        command = rf"""
$tokens = $null
$errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('{runner_path}', [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ throw ($errors | Out-String) }}
$fn = $ast.Find({{ param($node) $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -eq 'Get-HostapdStationSnapshot' }}, $true)
if (-not $fn) {{ throw 'parser function missing' }}
Invoke-Expression $fn.Extent.Text
$one = Get-HostapdStationSnapshot @('AA:BB:CC:DD:EE:FF', 'flags=[AUTH][ASSOC][AUTHORIZED]')
$many = Get-HostapdStationSnapshot @('aa:bb:cc:dd:ee:ff', 'flags=[AUTHORIZED]', '11:22:33:44:55:66', 'flags=[AUTH][ASSOC]')
[pscustomobject]@{{ oneAll = @($one.All); oneAuthorized = @($one.Authorized); manyAll = @($many.All); manyAuthorized = @($many.Authorized) }} | ConvertTo-Json -Compress
"""
        completed = subprocess.run(
            [powershell, "-NoProfile", "-Command", command],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        payload = json.loads(completed.stdout.strip().splitlines()[-1])
        self.assertEqual(payload["oneAll"], ["aa:bb:cc:dd:ee:ff"])
        self.assertEqual(payload["oneAuthorized"], ["aa:bb:cc:dd:ee:ff"])
        self.assertEqual(len(payload["manyAll"]), 2)
        self.assertEqual(payload["manyAuthorized"], ["aa:bb:cc:dd:ee:ff"])

    def test_auto_discovery_dry_run_remains_offline(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell not available")
        completed = subprocess.run(
            [powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(RUNNER), "-AutoDiscoverClient"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertRegex(completed.stdout, r'"client_selection"\s*:\s*"auto-discover-single-authorized"')
        self.assertIn('OMAP_ISOLATED_DRY_RUN_PASS=1', completed.stdout)

    def test_watchdog_is_ram_only_and_restores_management(self):
        self.assertIn('STATE=/tmp/openmitrastar-ap-isolated-watchdog', self.watchdog)
        self.assertIn('ifconfig eth0 "$RECOVERY_IP"', self.watchdog)
        self.assertIn('ifconfig wlan0 0.0.0.0 down', self.watchdog)
        self.assertIn('rm -f "$AP_ROOT/secret.psk"', self.watchdog)
        self.assertIn('OMAP_WATCHDOG_ROLLBACK_PASS', self.watchdog)
        self.assertNotRegex(self.watchdog, re.compile(r'\b(?:flash_erase|nandwrite|mtd_debug|ubiformat)\b'))

    def test_no_5ghz_control_surface(self):
        joined = (self.runner + "\n" + self.watchdog).lower()
        for forbidden in ("qdrv", "qcsapi", "wifi0", "wlan1"):
            self.assertNotIn(forbidden, joined)

    def test_powershell_dry_run_has_no_remote_execution(self):
        powershell = shutil.which("pwsh") or shutil.which("powershell")
        if not powershell:
            self.skipTest("PowerShell not available")
        completed = subprocess.run(
            [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(RUNNER),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertRegex(completed.stdout, r'"topology"\s*:\s*"isolated"')
        self.assertRegex(completed.stdout, r'"bridge_allowed"\s*:\s*false')
        self.assertIn('OMAP_ISOLATED_DRY_RUN_PASS=1', completed.stdout)
        self.assertNotIn('remote-staging', completed.stdout)


if __name__ == "__main__":
    unittest.main()
