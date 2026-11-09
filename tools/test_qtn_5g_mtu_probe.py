#!/usr/bin/env python3
from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class Qtn5gMtuProbeTests(unittest.TestCase):
    def test_windows_oracle_probes_full_ethernet_mtu(self) -> None:
        text = (ROOT / "tools/run_qtn_5g_windows_oracle.ps1").read_text(encoding="utf-8")
        self.assertIn("[switch]$MtuProbe", text)
        self.assertIn("@(32, 256, 512, 1000, 1400, 1472)", text)
        self.assertIn("ping.exe -S $SourceIp -n 5 -w 1500 -f -l $PayloadBytes", text)
        self.assertIn("gateway_ping", text)
        self.assertIn("[switch]$SkipThroughput", text)
        self.assertIn("$TransferTimeoutSeconds", text)
        self.assertIn("restore_profile_autoconnect_suspended", text)
        self.assertIn("connectionmode=manual", text)
        self.assertIn("connectionmode=auto", text)
        self.assertIn("Invoke-FastPingStress", text)
        self.assertIn("PingStressPayloadBytes", text)

    def test_task_and_python_runner_forward_probe_flag(self) -> None:
        starter = (ROOT / "tools/start_qtn_5g_windows_oracle_task.ps1").read_text(encoding="utf-8")
        runner = (ROOT / "tools/run_qtn_5g_aelita_one_shot.py").read_text(encoding="utf-8")
        cert = (ROOT / "tools/run_f142_5g_aelita_certification.py").read_text(encoding="utf-8")
        self.assertIn('if ($MtuProbe) { $oracleCommand += " -MtuProbe" }', starter)
        self.assertIn('mtu_arg = " -MtuProbe" if mtu_probe else ""', runner)
        self.assertIn('throughput_arg = " -SkipThroughput" if skip_throughput else ""', runner)
        self.assertIn("ping_stress_count", runner)
        self.assertIn('parser.add_argument("--mtu-probe", action="store_true")', cert)


if __name__ == "__main__":
    unittest.main(verbosity=2)
