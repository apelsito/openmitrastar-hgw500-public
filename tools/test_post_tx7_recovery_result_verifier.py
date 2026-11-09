#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify_post_tx7_recovery_result.py"
RECOVERY_OUTPUTS = ROOT / "outputs/recovery"


GOOD_STDOUT = """OMPOSTTX7_RECOVERY_BEGIN
OMPOSTTX7_RECOVERY_UNAME_BEGIN
Linux openmitrastar 5.10.260-openmitrastar-radiohw #1 PREEMPT arc GNU/Linux
OMPOSTTX7_RECOVERY_UNAME_END
OMPOSTTX7_RECOVERY_UPTIME_BEGIN
12.34 56.78
OMPOSTTX7_RECOVERY_UPTIME_END
OMPOSTTX7_RECOVERY_CMDLINE_BEGIN
console=ttyS0
OMPOSTTX7_RECOVERY_CMDLINE_END
OMPOSTTX7_RECOVERY_ETH0_BEGIN
up
1
10
20
OMPOSTTX7_RECOVERY_ETH0_END
OMPOSTTX7_RECOVERY_INTERRUPTS_BEGIN
20: 123 ARC In-core Intc eth0
OMPOSTTX7_RECOVERY_INTERRUPTS_END
OMPOSTTX7_RECOVERY_DMESG_BEGIN
network ready
OMPOSTTX7_RECOVERY_DMESG_END
OMPOSTTX7_RECOVERY_END
"""


def stdout_eth0_ok(stdout: str) -> bool:
    begin = "OMPOSTTX7_RECOVERY_ETH0_BEGIN"
    end = "OMPOSTTX7_RECOVERY_ETH0_END"
    if begin not in stdout or end not in stdout:
        return False
    body = stdout.split(begin, 1)[1].split(end, 1)[0]
    lines = [line.strip() for line in body.splitlines() if line.strip()]
    return (
        len(lines) >= 4
        and lines[0] in {"up", "unknown"}
        and lines[1] == "1"
        and lines[2].isdigit()
        and lines[3].isdigit()
    )


def ping_ok_from_text(ping_text: str, ping_exit: int) -> bool:
    lowered = ping_text.lower()
    return (
        ping_exit == 0
        and "ttl=" in lowered
        and "unreachable" not in lowered
        and "timed out" not in lowered
        and "inaccesible" not in lowered
        and "agotado" not in lowered
    )


def load_report(proc: subprocess.CompletedProcess[str]) -> dict[str, Any]:
    return json.loads(proc.stdout)


class PostTx7RecoveryResultVerifierTests(unittest.TestCase):
    def setUp(self) -> None:
        RECOVERY_OUTPUTS.mkdir(parents=True, exist_ok=True)
        self.output_dir = Path(tempfile.mkdtemp(prefix="post-tx7-recovery-result-test-", dir=RECOVERY_OUTPUTS))
        self.result_path = self.output_dir / "recovery-result.json"
        self.result = self.write_result(pass_value=True)

    def tearDown(self) -> None:
        shutil.rmtree(self.output_dir, ignore_errors=True)

    def write_result(
        self,
        *,
        pass_value: bool,
        ping_exit: int = 0,
        ssh_exit: int = 0,
        stdout: str = GOOD_STDOUT,
        ping_text: str | None = None,
        mutations: dict[str, bool] | None = None,
    ) -> dict[str, Any]:
        mutations = mutations or {}
        ssh_marker = "OMPOSTTX7_RECOVERY_BEGIN" in stdout and "OMPOSTTX7_RECOVERY_END" in stdout
        kernel_ok = "5.10.260-openmitrastar-radiohw" in stdout
        eth0_ok = stdout_eth0_ok(stdout)
        fatal_found = "Misaligned Access" in stdout or "Oops" in stdout
        ping_text = ping_text if ping_text is not None else "Reply from 192.168.1.90: bytes=32 time<1ms TTL=64\n"
        ping_ok = ping_ok_from_text(ping_text, ping_exit)
        ping_path = self.output_dir / "ping.txt"
        ssh_stdout_path = self.output_dir / "ssh.stdout.txt"
        ssh_stderr_path = self.output_dir / "ssh.stderr.txt"
        ping_path.write_text(ping_text if ping_exit == 0 else "Request timed out\n", encoding="utf-8")
        ssh_stdout_path.write_text(stdout, encoding="utf-8")
        ssh_stderr_path.write_text("", encoding="utf-8")
        result = {
            "schema": "openmitrastar.post-tx7-recovery-result/v1",
            "status": "RECOVERY_PROVEN_READONLY" if pass_value else "RECOVERY_NOT_PROVEN",
            "pass": pass_value,
            "host": "192.168.1.90",
            "ping_exit": ping_exit,
            "ping_ok": ping_ok,
            "ssh_exit": ssh_exit,
            "ssh_marker": ssh_marker,
            "kernel_ok": kernel_ok,
            "eth0_ok": eth0_ok,
            "fatal_found": fatal_found,
            "evidence": {
                "output_dir": str(self.output_dir),
                "ping": str(ping_path),
                "ssh_stdout": str(ssh_stdout_path),
                "ssh_stderr": str(ssh_stderr_path),
                "result_json": str(self.result_path),
            },
            "mutations": {
                "uart_opened": False,
                "reboot": False,
                "bootenv": False,
                "mtd": False,
                "flash": False,
                **mutations,
            },
        }
        self.result_path.write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result

    def run_verifier(self) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(self.result_path), "--output-dir", str(self.output_dir)],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_accepts_coherent_recovery_pass(self) -> None:
        proc = self.run_verifier()
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        report = load_report(proc)
        self.assertTrue(report["ok"])
        checks = {check["id"]: check["ok"] for check in report["checks"]}
        self.assertTrue(checks["pass.matches_evidence"])
        self.assertTrue(checks["status.matches_pass"])

    def test_accepts_bridged_eth0_unknown_with_carrier(self) -> None:
        bridged_stdout = GOOD_STDOUT.replace("up\n1\n10\n20", "unknown\n1\n10\n20")
        self.write_result(pass_value=True, stdout=bridged_stdout)
        proc = self.run_verifier()
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertTrue(load_report(proc)["ok"])

    def test_accepts_powershell_utf16_stdout(self) -> None:
        payload = self.write_result(pass_value=True)
        Path(payload["evidence"]["ssh_stdout"]).write_text(GOOD_STDOUT, encoding="utf-16")
        proc = self.run_verifier()
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertTrue(load_report(proc)["ok"])

    def test_rejects_forged_pass_when_ping_failed(self) -> None:
        self.write_result(pass_value=True, ping_exit=1)
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("pass.matches_evidence", failed)

    def test_rejects_forged_pass_when_ping_exit_zero_but_unreachable(self) -> None:
        payload = self.write_result(
            pass_value=True,
            ping_exit=0,
            ping_text="Reply from 192.168.1.43: Destination host unreachable.\n",
        )
        payload["ping_ok"] = True
        self.result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("ping_ok.matches_ping_output", failed)
        self.assertIn("pass.matches_evidence", failed)

    def test_rejects_kernel_flag_mismatch(self) -> None:
        payload = self.write_result(pass_value=False, stdout=GOOD_STDOUT.replace("5.10.260-openmitrastar-radiohw", "5.4.0-other"))
        payload["kernel_ok"] = True
        self.result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("kernel_ok.matches_stdout", failed)

    def test_rejects_fatal_marker_forged_as_clean(self) -> None:
        payload = self.write_result(pass_value=True, stdout=GOOD_STDOUT + "\nMisaligned Access\n")
        payload["fatal_found"] = False
        self.result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("fatal_found.matches_stdout", failed)
        self.assertIn("pass.matches_evidence", failed)

    def test_rejects_eth0_markers_without_proven_link(self) -> None:
        bad_stdout = GOOD_STDOUT.replace("up\n1\n10\n20", "down\n0\n10\n20")
        payload = self.write_result(pass_value=True, stdout=bad_stdout)
        payload["eth0_ok"] = True
        self.result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("eth0_ok.matches_stdout", failed)
        self.assertIn("pass.matches_evidence", failed)

    def test_rejects_eth0_markers_with_malformed_counters(self) -> None:
        bad_stdout = GOOD_STDOUT.replace("up\n1\n10\n20", "up\n1\nrx?\n20")
        payload = self.write_result(pass_value=True, stdout=bad_stdout)
        payload["eth0_ok"] = True
        self.result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("eth0_ok.matches_stdout", failed)
        self.assertIn("pass.matches_evidence", failed)

    def test_rejects_mutation_flag_enabled(self) -> None:
        self.write_result(pass_value=True, mutations={"reboot": True})
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("mutations.reboot.false", failed)

    def test_rejects_evidence_path_escape(self) -> None:
        outside = self.output_dir.parent / "outside-post-tx7-ssh.stdout.txt"
        try:
            outside.write_text(GOOD_STDOUT, encoding="utf-8")
            payload = json.loads(self.result_path.read_text(encoding="utf-8"))
            payload["evidence"]["ssh_stdout"] = str(outside)
            self.result_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            proc = self.run_verifier()
            self.assertEqual(1, proc.returncode)
            failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
            self.assertIn("evidence.ssh_stdout.under_output_dir", failed)
        finally:
            outside.unlink(missing_ok=True)

    def test_rejects_secret_bearing_stdout_without_echoing_secret(self) -> None:
        secret_value = "super-secret-router-key"
        self.write_result(pass_value=True, stdout=GOOD_STDOUT + f"\nwpa_psk={secret_value}\n")
        proc = self.run_verifier()
        self.assertEqual(1, proc.returncode)
        self.assertNotIn(secret_value, proc.stdout)
        self.assertNotIn(secret_value, proc.stderr)
        failed = {check["id"] for check in load_report(proc)["checks"] if not check["ok"]}
        self.assertIn("ssh_stdout.no_secrets", failed)


if __name__ == "__main__":
    unittest.main(verbosity=2)
