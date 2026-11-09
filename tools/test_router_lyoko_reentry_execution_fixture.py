#!/usr/bin/env python3
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from test_router_lyoko_live_verifier import sample_payload as live_payload


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify_router_lyoko_reentry.ps1"
RESULT_VERIFIER = ROOT / "tools/verify_router_lyoko_reentry_result.py"
WEB_ROOT = ROOT / "work/mission-state/router-lyoko-v0/rootfs/var/www"
RECOVERY_OUTPUTS = ROOT / "outputs/recovery"
ACK = "OPENMITRASTAR_LYOKO_REENTRY_READONLY"


def load_json_file(path: Path) -> dict:
    data = path.read_bytes()
    if data.startswith(b"\xff\xfe") or data.startswith(b"\xfe\xff"):
        return json.loads(data.decode("utf-16"))
    return json.loads(data.decode("utf-8-sig"))


def control_payload() -> dict:
    snapshots = {
        "control_policy": {"present": True, "bytes": 4013},
        "event_taxonomy": {"present": True, "bytes": 3622},
        "safe_mode": {"present": True, "bytes": 2977},
        "goal_audit": {"present": True, "bytes": 8211},
        "aelita_dialogue": {"present": True, "bytes": 2482},
        "aelita_memory": {"present": True, "bytes": 2675},
        "evidence_bindings": {"present": True, "bytes": 4197},
        "telemetry_contract": {"present": True, "bytes": 1384},
    }
    return {
        "ok": True,
        "schema": "router-lyoko.control-contract/v1",
        "classification": "FAIL-CLOSED-OBSERVE-ONLY-NO-DEVICE-WRITE",
        "mode": "observe_only",
        "request": {"status": "described", "executes": False, "writes_device": False},
        "persona": {"name": "Aelita"},
        "policy_snapshot": snapshots,
        "current_allowed_actions": [{"id": "observe", "writes_device": False}],
        "blocked_action_classes": sorted(
            [
                "flash_promotion",
                "boot_environment_change",
                "mtd_write",
                "module_mutation",
                "radio_mutation",
                "network_change",
                "secret_rendering",
            ]
        ),
        "guards": {
            "dashboard_executes_commands": False,
            "device_write": False,
            "flash_write": False,
            "bootenv_write": False,
            "mtd_write": False,
            "module_mutation": False,
            "network_reconfigure": False,
            "radio_control": False,
        },
    }


def bad_live_payload() -> dict:
    payload = live_payload()
    payload["sectors"]["bridge"]["state"] = "down"
    payload["sectors"]["bridge"]["eth0_carrier"] = "0"
    return payload


def bad_control_payload() -> dict:
    payload = control_payload()
    payload["request"]["writes_device"] = True
    return payload


def bad_static_index_payload() -> bytes:
    payload = json.loads((WEB_ROOT / "lyoko-data/index.json").read_text(encoding="utf-8"))
    payload["safety"]["flash_write"] = True
    return json.dumps(payload).encode("utf-8")


class RouterLyokoFixtureHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, _format: str, *_args) -> None:
        return

    def send_bytes(self, status: int, body: bytes, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        if self.path == "/api/lyoko":
            payload = getattr(self.server, "live_payload", live_payload())
            body = json.dumps(payload).encode("utf-8")
            self.send_bytes(200, body, "application/json")
            return
        if self.path == "/api/lyoko-control":
            payload = getattr(self.server, "control_payload", control_payload())
            body = json.dumps(payload).encode("utf-8")
            self.send_bytes(200, body, "application/json")
            return

        request_path = urllib.parse.unquote(self.path.split("?", 1)[0])
        corrupt_files = getattr(self.server, "corrupt_files", {})
        if request_path in corrupt_files:
            self.send_bytes(200, corrupt_files[request_path], "application/octet-stream")
            return

        web_path = request_path.lstrip("/")
        candidate = (WEB_ROOT / Path(*web_path.split("/"))).resolve()
        web_root = WEB_ROOT.resolve()
        if candidate != web_root and web_root in candidate.parents and candidate.is_file():
            self.send_bytes(200, candidate.read_bytes(), "application/octet-stream")
            return
        self.send_bytes(404, b"not found", "text/plain")


class RouterLyokoReentryExecutionFixtureTests(unittest.TestCase):
    def run_reentry_against_fixture(
        self,
        *,
        corrupt_files: dict[str, bytes] | None = None,
        live_response: dict | None = None,
        control_response: dict | None = None,
        prefix: str = "lyoko-reentry-fixture-",
    ) -> tuple[subprocess.CompletedProcess[str], Path, ThreadingHTTPServer, threading.Thread]:
        RECOVERY_OUTPUTS.mkdir(parents=True, exist_ok=True)
        output_dir = Path(tempfile.mkdtemp(prefix=prefix, dir=RECOVERY_OUTPUTS))
        server = ThreadingHTTPServer(("127.0.0.1", 0), RouterLyokoFixtureHandler)
        setattr(server, "corrupt_files", corrupt_files or {})
        setattr(server, "live_payload", live_response or live_payload())
        setattr(server, "control_payload", control_response or control_payload())
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        host = f"127.0.0.1:{server.server_port}"
        proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(SCRIPT),
                "-HostAddress",
                host,
                "-Timeout",
                "5",
                "-Execute",
                "-Ack",
                ACK,
                "-OutputDir",
                str(output_dir),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
            check=False,
        )
        return proc, output_dir, server, thread

    def stop_fixture(self, output_dir: Path, server: ThreadingHTTPServer, thread: threading.Thread) -> None:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
        shutil.rmtree(output_dir, ignore_errors=True)

    def assert_fail_closed(
        self,
        result: dict,
        *,
        state_ok: bool,
        control_ok: bool,
        static_index_ok: bool,
        served_files_ok: bool,
        served_no_secrets_ok: bool,
    ) -> None:
        self.assertFalse(result["pass"])
        self.assertEqual(result["state_verifier_ok"], state_ok)
        self.assertEqual(result["control_verifier_ok"], control_ok)
        self.assertEqual(result["static_index_verifier_ok"], static_index_ok)
        self.assertEqual(result["served_files_verifier_ok"], served_files_ok)
        self.assertEqual(result["served_no_secrets_verifier_ok"], served_no_secrets_ok)
        self.assertFalse(result["mutations"]["uart_opened"])
        self.assertFalse(result["mutations"]["ssh_command"])
        self.assertFalse(result["mutations"]["reboot"])
        self.assertFalse(result["mutations"]["bootenv"])
        self.assertFalse(result["mutations"]["mtd"])
        self.assertFalse(result["mutations"]["flash"])

    def assert_result_verifier_accepts(self, output_dir: Path) -> None:
        result_path = output_dir / "lyoko-reentry-result.json"
        proc = subprocess.run(
            [
                sys.executable,
                str(RESULT_VERIFIER),
                str(result_path),
                "--output-dir",
                str(output_dir),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
            check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)

    def test_reentry_execute_passes_against_local_read_only_fixture(self) -> None:
        proc, output_dir, server, thread = self.run_reentry_against_fixture()
        try:
            self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
            self.assertIn("OMLYOKO_REENTRY_PASS=1", proc.stdout)

            result_path = output_dir / "lyoko-reentry-result.json"
            self.assertTrue(result_path.is_file())
            result = load_json_file(result_path)
            self.assertTrue(result["pass"])
            self.assertTrue(result["state_verifier_ok"])
            self.assertTrue(result["control_verifier_ok"])
            self.assertTrue(result["static_index_verifier_ok"])
            self.assertTrue(result["served_files_verifier_ok"])
            self.assertTrue(result["served_no_secrets_verifier_ok"])
            self.assertTrue(result["result_verifier_ok"])
            self.assertEqual(result["result_verifier_status"], "LYOKO_REENTRY_RESULT_VERIFIED_READONLY")
            self.assertEqual(result["served_files_verifier_status"], "LYOKO_SERVED_FILES_PROVEN_READONLY")
            self.assertEqual(result["served_no_secrets_verifier_status"], "LYOKO_SERVED_NO_SECRETS_PROVEN_READONLY")

            served_report = load_json_file(output_dir / "lyoko-served-files-verifier.stdout.json")
            self.assertTrue(served_report["ok"])
            self.assertGreaterEqual(served_report["files_checked"], 19)
            no_secrets_report = load_json_file(output_dir / "lyoko-served-no-secrets-verifier.stdout.json")
            self.assertTrue(no_secrets_report["ok"])
            self.assertGreaterEqual(no_secrets_report["payloads_scanned"], 21)
            self.assert_result_verifier_accepts(output_dir)
        finally:
            self.stop_fixture(output_dir, server, thread)

    def test_reentry_execute_fails_closed_when_served_asset_hash_drifts(self) -> None:
        proc, output_dir, server, thread = self.run_reentry_against_fixture(
            corrupt_files={"/lyoko.js": b"/* xana stale served asset */\n"},
            prefix="lyoko-reentry-corrupt-fixture-",
        )
        try:
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("OMLYOKO_REENTRY_PASS=0", proc.stdout)

            result = load_json_file(output_dir / "lyoko-reentry-result.json")
            self.assert_fail_closed(
                result,
                state_ok=True,
                control_ok=True,
                static_index_ok=True,
                served_files_ok=False,
                served_no_secrets_ok=True,
            )
            self.assertEqual(result["served_files_verifier_status"], "LYOKO_SERVED_FILES_NOT_PROVEN")
            self.assertTrue(result["result_verifier_ok"])

            served_report = load_json_file(output_dir / "lyoko-served-files-verifier.stdout.json")
            failing = {check["id"] for check in served_report["checks"] if not check["ok"]}
            self.assertIn("served./lyoko.js.bytes", failing)
            self.assertIn("served./lyoko.js.sha256", failing)
            self.assert_result_verifier_accepts(output_dir)
        finally:
            self.stop_fixture(output_dir, server, thread)

    def test_reentry_execute_fails_closed_when_state_contract_fails(self) -> None:
        proc, output_dir, server, thread = self.run_reentry_against_fixture(
            live_response=bad_live_payload(),
            prefix="lyoko-reentry-bad-state-fixture-",
        )
        try:
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("OMLYOKO_REENTRY_PASS=0", proc.stdout)
            result = load_json_file(output_dir / "lyoko-reentry-result.json")
            self.assert_fail_closed(
                result,
                state_ok=False,
                control_ok=True,
                static_index_ok=True,
                served_files_ok=True,
                served_no_secrets_ok=True,
            )
            self.assertEqual(result["state_verifier_status"], "LYOKO_STATE_NOT_PROVEN")
            self.assertTrue(result["result_verifier_ok"])
            state_report = load_json_file(output_dir / "lyoko-live-verifier.stdout.json")
            failing = {check["id"] for check in state_report["checks"] if not check["ok"]}
            self.assertIn("bridge.up", failing)
            self.assert_result_verifier_accepts(output_dir)
        finally:
            self.stop_fixture(output_dir, server, thread)

    def test_reentry_execute_fails_closed_when_control_contract_claims_write(self) -> None:
        proc, output_dir, server, thread = self.run_reentry_against_fixture(
            control_response=bad_control_payload(),
            prefix="lyoko-reentry-bad-control-fixture-",
        )
        try:
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("OMLYOKO_REENTRY_PASS=0", proc.stdout)
            result = load_json_file(output_dir / "lyoko-reentry-result.json")
            self.assert_fail_closed(
                result,
                state_ok=True,
                control_ok=False,
                static_index_ok=True,
                served_files_ok=True,
                served_no_secrets_ok=True,
            )
            self.assertEqual(result["control_verifier_status"], "LYOKO_CONTROL_NOT_PROVEN")
            self.assertTrue(result["result_verifier_ok"])
            control_report = load_json_file(output_dir / "lyoko-control-verifier.stdout.json")
            failing = {check["id"] for check in control_report["checks"] if not check["ok"]}
            self.assertIn("request.no_write", failing)
            self.assert_result_verifier_accepts(output_dir)
        finally:
            self.stop_fixture(output_dir, server, thread)

    def test_reentry_execute_fails_closed_when_static_index_claims_write(self) -> None:
        proc, output_dir, server, thread = self.run_reentry_against_fixture(
            corrupt_files={"/lyoko-data/index.json": bad_static_index_payload()},
            prefix="lyoko-reentry-bad-index-fixture-",
        )
        try:
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("OMLYOKO_REENTRY_PASS=0", proc.stdout)
            result = load_json_file(output_dir / "lyoko-reentry-result.json")
            self.assert_fail_closed(
                result,
                state_ok=True,
                control_ok=True,
                static_index_ok=False,
                served_files_ok=False,
                served_no_secrets_ok=True,
            )
            self.assertEqual(result["static_index_verifier_status"], "LYOKO_STATIC_INDEX_NOT_PROVEN")
            self.assertTrue(result["result_verifier_ok"])
            index_report = load_json_file(output_dir / "lyoko-static-index-verifier.stdout.json")
            failing = {check["id"] for check in index_report["checks"] if not check["ok"]}
            self.assertIn("safety.flash_write.false", failing)
            self.assert_result_verifier_accepts(output_dir)
        finally:
            self.stop_fixture(output_dir, server, thread)

    def test_reentry_execute_fails_closed_when_control_endpoint_serves_secret(self) -> None:
        secret_control = control_payload()
        secret_control["COOKIE_SESSION_KEY"] = "router-lab-secret-1234"
        proc, output_dir, server, thread = self.run_reentry_against_fixture(
            control_response=secret_control,
            prefix="lyoko-reentry-secret-control-fixture-",
        )
        try:
            self.assertEqual(proc.returncode, 2, proc.stdout + proc.stderr)
            self.assertIn("OMLYOKO_REENTRY_PASS=0", proc.stdout)
            self.assertNotIn("router-lab-secret-1234", proc.stdout)
            result = load_json_file(output_dir / "lyoko-reentry-result.json")
            self.assert_fail_closed(
                result,
                state_ok=True,
                control_ok=True,
                static_index_ok=True,
                served_files_ok=True,
                served_no_secrets_ok=False,
            )
            self.assertEqual(result["served_no_secrets_verifier_status"], "LYOKO_SERVED_NO_SECRETS_NOT_PROVEN")
            self.assertTrue(result["result_verifier_ok"])
            no_secrets_report = load_json_file(output_dir / "lyoko-served-no-secrets-verifier.stdout.json")
            self.assertFalse(no_secrets_report["ok"])
            keys = {finding["key"] for finding in no_secrets_report["findings"]}
            self.assertIn("COOKIE_SESSION_KEY", keys)
            self.assertNotIn("router-lab-secret-1234", json.dumps(no_secrets_report))
            self.assert_result_verifier_accepts(output_dir)
        finally:
            self.stop_fixture(output_dir, server, thread)


if __name__ == "__main__":
    unittest.main(verbosity=2)
