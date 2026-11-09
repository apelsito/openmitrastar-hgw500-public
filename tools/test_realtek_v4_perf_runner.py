from pathlib import Path
import hashlib
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_realtek_v4_perf_gate.ps1"
PERF = ROOT / "outputs/kernel-port/realtek-perf-v4/om_icmp_perf"


class RealtekV4PerfRunnerTests(unittest.TestCase):
    def test_perf_binary_identity(self):
        self.assertEqual(PERF.stat().st_size, 48912)
        self.assertEqual(hashlib.sha256(PERF.read_bytes()).hexdigest(),
                         "8c6fd3cccc7443f90c3ca271899e0c0322fb5cb75763cdfb2310a85549ac2286")

    def test_runner_policy(self):
        source = RUNNER.read_text()
        for required in (
            "OMRTL_V4_PERF_CAPTURE_ARMED_",
            "OMICMPPERF",
            "OMRTL92 stage=rx-rate-decode ht=1",
            "OMRTL stage=tx-complete",
            "performance_threshold_enforced = $false",
        ):
            self.assertIn(required, source)
        for forbidden in ("flashcp", "mtd_debug", "saveenv", "flwrite"):
            self.assertNotIn(forbidden, source)

    def test_dry_run(self):
        command = [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(RUNNER), "-ClientIp", "192.168.1.201",
            "-ClientMac", "02:00:00:00:00:01",
        ]
        result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("OMRTL_V4_PERF_DRY_RUN_PASS=1", result.stdout)


if __name__ == "__main__":
    unittest.main()
