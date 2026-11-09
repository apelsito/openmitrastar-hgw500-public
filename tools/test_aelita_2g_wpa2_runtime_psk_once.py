#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_aelita_2g_wpa2_runtime_psk_once.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("aelita_2g_wpa2_runtime_psk_once", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def parse_powershell_text(text: str) -> None:
    command = (
        "$src=[Console]::In.ReadToEnd();"
        "$e=$null;$t=$null;"
        "[System.Management.Automation.Language.Parser]::ParseInput($src,[ref]$t,[ref]$e)|Out-Null;"
        "if($e.Count){$e|ForEach-Object{$_.ToString()};exit 1}"
    )
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
        input=text,
        text=True,
        capture_output=True,
        timeout=20,
        check=True,
    )


class _FakeChannel:
    def __init__(self, rc: int = 0) -> None:
        self._rc = rc
        self.shutdown_write_called = False

    def recv_exit_status(self) -> int:
        return self._rc

    def shutdown_write(self) -> None:
        self.shutdown_write_called = True


class _FakePipe:
    def __init__(self, text: str = "", rc: int = 0) -> None:
        self._text = text
        self.channel = _FakeChannel(rc)
        self.written = ""

    def read(self) -> bytes:
        return self._text.encode("utf-8")

    def write(self, text: str) -> None:
        self.written += text

    def flush(self) -> None:
        pass


class _FakeClient:
    def __init__(self, rc: int, stdout_text: str, stderr_text: str) -> None:
        self.stdin = _FakePipe()
        self.stdout = _FakePipe(stdout_text, rc)
        self.stderr = _FakePipe(stderr_text)
        self.closed = False

    def exec_command(self, command: str, timeout: int):
        self.command = command
        self.timeout = timeout
        return self.stdin, self.stdout, self.stderr

    def close(self) -> None:
        self.closed = True


class Aelita2gRuntimePskRunnerTests(unittest.TestCase):
    def test_runtime_psk_read_retries_transient_ssh_timeout(self) -> None:
        runner = load_runner()
        calls = []
        sleeps = []

        def fake_read(host: str, ssid: str) -> str:
            calls.append((host, ssid))
            if len(calls) == 1:
                raise subprocess.TimeoutExpired(["ssh"], 28)
            return "valid-passphrase"

        original_read = runner._read_router_runtime_psk_once
        original_sleep = runner.time.sleep
        try:
            runner._read_router_runtime_psk_once = fake_read
            runner.time.sleep = sleeps.append
            result = runner.read_router_runtime_psk(
                "192.168.1.90", "OpenMitraStar-Lab", attempts=3, delay_seconds=0.25
            )
        finally:
            runner._read_router_runtime_psk_once = original_read
            runner.time.sleep = original_sleep

        self.assertEqual("valid-passphrase", result)
        self.assertEqual(2, len(calls))
        self.assertEqual([0.25], sleeps)

    def test_runtime_psk_read_exhaustion_is_secret_free(self) -> None:
        runner = load_runner()
        calls = []

        def fake_read(host: str, ssid: str) -> str:
            calls.append((host, ssid))
            raise subprocess.TimeoutExpired(["ssh", "sensitive-command"], 28)

        original_read = runner._read_router_runtime_psk_once
        original_sleep = runner.time.sleep
        try:
            runner._read_router_runtime_psk_once = fake_read
            runner.time.sleep = lambda _: None
            with self.assertRaises(RuntimeError) as ctx:
                runner.read_router_runtime_psk(
                    "192.168.1.90", "OpenMitraStar-Lab", attempts=3, delay_seconds=0
                )
        finally:
            runner._read_router_runtime_psk_once = original_read
            runner.time.sleep = original_sleep

        self.assertEqual(3, len(calls))
        self.assertEqual(
            "router runtime PSK read failed after 3 attempts (TimeoutExpired)",
            str(ctx.exception),
        )

    def test_dry_run_is_network_free_and_pins_secret_contract(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("OM2G_WPA2_AELITA_DRY_RUN_PASS=1 execute=0", proc.stdout)
        self.assertIn("router PSK read over SSH into process memory only", proc.stdout)
        self.assertIn("PSK sent to AELITA over SSH stdin only", proc.stdout)
        self.assertIn("DPAPI LocalMachine blob", proc.stdout)
        self.assertIn("no PSK value or PSK hash is printed", proc.stdout)
        self.assertIn('"wifi_connect_now": false', proc.stdout)

    def test_oracle_ps_failure_reports_full_redacted_stdout_and_stderr(self) -> None:
        runner = load_runner()
        secret = "SecretPass<&>123"
        stdout_text = "stdout-head\n" + ("x" * 2300) + "\nstdout-tail " + secret
        stderr_text = (
            "stderr-head\n"
            + ("y" * 2300)
            + "\nstderr-tail "
            + secret
            + "\n<keyMaterial>leaked-profile-key</keyMaterial>"
            + "\nwpa_passphrase=leaked-passphrase"
        )
        fake_client = _FakeClient(1, stdout_text, stderr_text)
        captured = {}

        def fake_connect(host: str, user: str):
            return fake_client

        def fake_evidence(command, out, err, rc, *, secrets=()):
            captured["command"] = command
            captured["out"] = out
            captured["err"] = err
            captured["rc"] = rc
            captured["secrets"] = secrets
            return Path("oracle-powershell-failure-test.json")

        original_connect = runner.oracle_connect
        original_evidence = runner.write_oracle_failure_evidence
        try:
            runner.oracle_connect = fake_connect
            runner.write_oracle_failure_evidence = fake_evidence
            with self.assertRaises(RuntimeError) as ctx:
                runner.oracle_ps("192.168.1.63", "AELITA", "Write-Output hi", stdin_text=secret)
        finally:
            runner.oracle_connect = original_connect
            runner.write_oracle_failure_evidence = original_evidence

        message = str(ctx.exception)
        self.assertIn("oracle PowerShell rc=1; full stdout/stderr captured", message)
        self.assertIn("stdout-tail [REDACTED]", message)
        self.assertIn("stderr-tail [REDACTED]", message)
        self.assertIn("<keyMaterial>[REDACTED]</keyMaterial>", message)
        self.assertIn("wpa_passphrase=[REDACTED]", message)
        self.assertNotIn(secret, message)
        self.assertNotIn("leaked-profile-key", message)
        self.assertNotIn("leaked-passphrase", message)
        self.assertEqual((secret,), captured["secrets"])
        self.assertTrue(fake_client.stdin.channel.shutdown_write_called)
        self.assertTrue(fake_client.closed)

    def test_start_remote_task_renders_logged_task_without_psk_in_script(self) -> None:
        runner = load_runner()
        secret = "RuntimePskShouldOnlyUseStdin"
        captured = {}

        def fake_oracle_ps_script(host, user, script_name, script_text, *, stdin_text="", timeout=90):
            captured["host"] = host
            captured["user"] = user
            captured["script_name"] = script_name
            captured["script_text"] = script_text
            captured["stdin_text"] = stdin_text
            captured["timeout"] = timeout
            return '{"schema":"test"}'

        args = argparse.Namespace(
            oracle_host="192.168.1.63",
            oracle_user="AELITA",
            router_host="192.168.1.90",
            test_ssid="OpenMitraStar-Lab",
            wifi_interface="Wi-Fi",
            controller_url="",
            traffic_direction="download",
            expected_bssid="",
            connect_timeout=45,
            restore_timeout=90,
            restore_watchdog_minutes=3,
            soak_seconds=10,
        )
        hashes = {
            "run_2g_wpa2_windows_oracle.ps1": "a" * 64,
            "restore_2g_wpa2_watchdog.ps1": "b" * 64,
        }
        original = runner.oracle_ps_script
        try:
            runner.oracle_ps_script = fake_oracle_ps_script
            result = runner.start_remote_task(args, secret, hashes)
        finally:
            runner.oracle_ps_script = original

        script = captured["script_text"]
        self.assertEqual('{"schema":"test"}', result)
        self.assertEqual(secret, captured["stdin_text"])
        self.assertNotIn(secret, script)
        for marker in (
            "2g-wpa2-task-",
            ".stdout.log",
            ".stderr.log",
            "2g-wpa2-watchdog-",
            "`$ProgressPreference = 'SilentlyContinue'",
            "1> $(Quote-PowerShellLiteral $taskStdout) 2> $(Quote-PowerShellLiteral $taskStderr)",
            "1> $(Quote-PowerShellLiteral $watchdogStdout) 2> $(Quote-PowerShellLiteral $watchdogStderr)",
            "-TrafficDirection $(Quote-PowerShellLiteral 'download')",
            "Read-LogIfExists",
            "SYSTEM oracle task did not start after Start-ScheduledTask",
            "task_last_task_result = $launchedInfo.LastTaskResult",
            "task_stdout = $taskStdout",
            "task_stderr = $taskStderr",
        ):
            self.assertIn(marker, script)
        parse_powershell_text(script)

    def test_embedded_oracle_scripts_parse(self) -> None:
        runner = load_runner()
        parse_powershell_text(runner.WORKER_PS1)
        parse_powershell_text(runner.WATCHDOG_PS1)

    def test_empty_controller_url_is_optional(self) -> None:
        runner = load_runner()

        self.assertIn("param([AllowEmptyString()][string]$Url)", runner.WORKER_PS1)
        self.assertIn("if (-not $Url) { return $null }", runner.WORKER_PS1)
        self.assertIn(
            "if ($ControllerUrl -and ($TrafficDirection -eq 'download' -or $TrafficDirection -eq 'both')",
            runner.WORKER_PS1,
        )
        self.assertIn(
            "if ($ControllerUrl -and ($TrafficDirection -eq 'upload' -or $TrafficDirection -eq 'both')",
            runner.WORKER_PS1,
        )

    def test_oracle_target_allows_dhcp_moved_aelita_on_local_lan(self) -> None:
        runner = load_runner()

        runner.validate_oracle_target("192.168.1.63", "AELITA")
        runner.validate_oracle_target("192.168.1.35", "AELITA")
        for host in ("192.168.1.1", "192.168.1.43", "192.168.1.90", "8.8.8.8"):
            with self.assertRaises(SystemExit):
                runner.validate_oracle_target(host, "AELITA")
        with self.assertRaises(SystemExit):
            runner.validate_oracle_target("192.168.1.35", "root")

    def test_refresh_oracle_known_hosts_replaces_stale_pin(self) -> None:
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            known_hosts = Path(tmp) / "known_hosts"
            known_hosts.write_text(
                "192.168.1.63 ssh-rsa STALE\n"
                "192.168.1.35 ssh-ed25519 OTHER\n",
                encoding="ascii",
            )
            calls = []

            def fake_run(args, **kwargs):
                calls.append(args)
                if args[0] == "ssh-keygen":
                    known_hosts.write_text(
                        "192.168.1.35 ssh-ed25519 OTHER\n",
                        encoding="ascii",
                    )
                    return subprocess.CompletedProcess(args, 0, stdout="")
                if Path(args[0]).name.lower() in {"ssh-keyscan", "ssh-keyscan.exe"}:
                    return subprocess.CompletedProcess(
                        args,
                        0,
                        stdout=(
                            "# 192.168.1.63:22 SSH-2.0-OpenSSH\r\n"
                            "192.168.1.63 ssh-ed25519 FRESHED25519\n"
                            "192.168.1.63 ssh-rsa FRESHRSA\n"
                        ),
                    )
                raise AssertionError(args)

            original_known_hosts = runner.KNOWN_HOSTS
            original_run = runner.subprocess.run
            original_fallback = runner._paramiko_keyscan_line
            try:
                runner.KNOWN_HOSTS = known_hosts
                runner.subprocess.run = fake_run
                runner._paramiko_keyscan_line = lambda host: None
                runner.refresh_oracle_known_hosts("192.168.1.63")
            finally:
                runner.KNOWN_HOSTS = original_known_hosts
                runner.subprocess.run = original_run
                runner._paramiko_keyscan_line = original_fallback

            text = known_hosts.read_text(encoding="ascii")
            self.assertNotIn("STALE", text)
            self.assertIn("192.168.1.35 ssh-ed25519 OTHER", text)
            self.assertIn("192.168.1.63 ssh-ed25519 FRESHED25519", text)
            self.assertIn("192.168.1.63 ssh-rsa FRESHRSA", text)
            self.assertEqual("ssh-keygen", calls[0][0])
            self.assertIn(Path(calls[1][0]).name.lower(), {"ssh-keyscan", "ssh-keyscan.exe"})

    def test_refresh_oracle_known_hosts_uses_paramiko_fallback_without_keyscan(self) -> None:
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            known_hosts = Path(tmp) / "known_hosts"

            def fake_run(args, **kwargs):
                return subprocess.CompletedProcess(args, 0, stdout="# no keys\n")

            original_known_hosts = runner.KNOWN_HOSTS
            original_run = runner.subprocess.run
            original_fallback = runner._paramiko_keyscan_line
            try:
                runner.KNOWN_HOSTS = known_hosts
                runner.subprocess.run = fake_run
                runner._paramiko_keyscan_line = lambda host: f"{host} ssh-ed25519 FALLBACK"
                runner.refresh_oracle_known_hosts("192.168.1.63")
            finally:
                runner.KNOWN_HOSTS = original_known_hosts
                runner.subprocess.run = original_run
                runner._paramiko_keyscan_line = original_fallback

            text = known_hosts.read_text(encoding="ascii")
            self.assertIn("192.168.1.63 ssh-ed25519 FALLBACK", text)

    def test_refresh_oracle_known_hosts_fails_closed_without_any_host_key(self) -> None:
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            known_hosts = Path(tmp) / "known_hosts"

            def fake_run(args, **kwargs):
                return subprocess.CompletedProcess(args, 0, stdout="# no keys\n")

            original_known_hosts = runner.KNOWN_HOSTS
            original_run = runner.subprocess.run
            original_fallback = runner._paramiko_keyscan_line
            try:
                runner.KNOWN_HOSTS = known_hosts
                runner.subprocess.run = fake_run
                runner._paramiko_keyscan_line = lambda host: None
                with self.assertRaises(SystemExit):
                    runner.refresh_oracle_known_hosts("192.168.1.63")
            finally:
                runner.KNOWN_HOSTS = original_known_hosts
                runner.subprocess.run = original_run
                runner._paramiko_keyscan_line = original_fallback

    def test_router_ssh_falls_back_to_user_key_on_publickey_denied(self) -> None:
        runner = load_runner()

        with tempfile.TemporaryDirectory() as tmp:
            first_key = Path(tmp) / "old_key"
            second_key = Path(tmp) / "id_ed25519"
            first_key.write_text("old", encoding="ascii")
            second_key.write_text("new", encoding="ascii")
            calls = []

            def fake_run(args, **kwargs):
                calls.append(args)
                if str(first_key) in args:
                    return subprocess.CompletedProcess(
                        args,
                        255,
                        stdout="",
                        stderr="root@192.168.1.90: Permission denied (publickey).",
                    )
                if str(second_key) in args:
                    return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")
                raise AssertionError(args)

            original_candidates = runner.router_key_candidates
            original_refresh = runner.refresh_router_known_hosts
            original_run = runner.subprocess.run
            try:
                runner.router_key_candidates = lambda: [first_key, second_key]
                runner.refresh_router_known_hosts = lambda host: None
                runner.subprocess.run = fake_run
                rc, out, err = runner.router_ssh("192.168.1.90", "true")
            finally:
                runner.router_key_candidates = original_candidates
                runner.refresh_router_known_hosts = original_refresh
                runner.subprocess.run = original_run

            self.assertEqual(0, rc)
            self.assertEqual("ok", out)
            self.assertEqual("", err)
            self.assertEqual(2, len(calls))


if __name__ == "__main__":
    unittest.main(verbosity=2)
