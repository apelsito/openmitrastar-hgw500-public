#!/usr/bin/env python3
"""Exercise every F313 writable Quantenna setting with exact rollback."""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import http.cookiejar
import json
from pathlib import Path
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary"
EXPECTED_VERSION = "lyoko-foundation-6.8.1-f313-full-developer-qtn-controls-device"
RELEASE = "f313"
DEFAULT_KNOWN_HOSTS = DEVICE / "firmware/f313-device-bound/known_hosts.f313"
DEFAULT_OUTPUT_DIR = ROOT / "outputs/f3-certification/f313-qtn-control-matrix"
EXPECTED_WRITABLE = [
    "ssid", "ssid_broadcast", "client_isolation", "wmm", "short_gi",
    "beacon_interval", "dtim_period", "retry_count", "ldpc", "forty_only",
    "ba_control", "ba_max", "ampdu_density", "tpc_interval", "multicast_rate",
]
CONFIRM = "OPENMITRASTAR_CONFIG_TRANSACTION_V1"
ACTION_TIMEOUT = 360


class Api:
    def __init__(self, host: str, password_file: Path):
        self.base = f"http://{host}/api/v1"
        self.root = f"http://{host}"
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        password = password_file.read_text(encoding="utf-8").rstrip("\r\n")
        body = urllib.parse.urlencode({"login_password": password}).encode()
        password = ""
        self._request("/index.cgi", method="POST", body=body, api=False)
        self.csrf = str(self.get("status")["csrf"])

    def _request(self, endpoint: str, *, method: str = "GET", body: bytes | None = None,
                 headers: dict[str, str] | None = None, api: bool = True,
                 timeout: int = 30) -> tuple[int, object]:
        url = (self.base if api else self.root) + endpoint
        request = urllib.request.Request(url, data=body, method=method)
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with self.opener.open(request, timeout=timeout) as response:
                raw = response.read()
                return response.status, json.loads(raw) if api else raw
        except urllib.error.HTTPError as exc:
            raw = exc.read()
            try:
                payload: object = json.loads(raw)
            except json.JSONDecodeError:
                payload = raw.decode("utf-8", "replace")
            return exc.code, payload

    def get(self, endpoint: str) -> dict:
        status, payload = self._request("/" + endpoint)
        if status != 200 or not isinstance(payload, dict):
            raise RuntimeError(f"GET {endpoint} failed: HTTP {status} {payload}")
        return payload

    def post_form(self, endpoint: str, values: dict[str, object], *, timeout: int = 30) -> tuple[int, object]:
        body = urllib.parse.urlencode({key: str(value).lower() if isinstance(value, bool) else value for key, value in values.items()}).encode()
        return self._request(
            "/" + endpoint,
            method="POST",
            body=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", "X-OM-CSRF": self.csrf},
            timeout=timeout,
        )

    def action(self, endpoint: str, transaction_id: str) -> tuple[int, object]:
        return self.post_form(
            endpoint,
            {"_confirm": CONFIRM, "_transaction": transaction_id},
            timeout=ACTION_TIMEOUT,
        )


def ssh(host: str, known_hosts: Path, command: str) -> str:
    ssh_binary = shutil.which("ssh")
    if not ssh_binary:
        raise RuntimeError("OpenSSH client is unavailable")
    proc = subprocess.run(
        [
            ssh_binary,
            "-i", str(Path.home() / ".ssh/id_ed25519"),
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=yes", "-o", f"UserKnownHostsFile={known_hosts}",
            "-o", "LogLevel=ERROR", f"root@{host}", command,
        ],
        text=True, capture_output=True, timeout=30, check=False,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or proc.stdout.strip() or f"ssh rc={proc.returncode}")
    return proc.stdout.strip()


def setting_map(contract: dict) -> dict[str, dict]:
    return {str(row["id"]): row for row in contract["settings"]["settings"]}


def alternate(key: str, current: object) -> object:
    if isinstance(current, bool):
        return not current
    choices = {
        "ssid": "Lyoko-F313-Control-Gate",
        "beacon_interval": 200,
        "dtim_period": 5,
        "retry_count": 7,
        "ba_control": 255,
        "ba_max": 32,
        "ampdu_density": 4,
        "tpc_interval": 60,
        "multicast_rate": 6000,
    }
    value = choices[key]
    if str(value) != str(current):
        return value
    fallback = {
        "ssid": "Lyoko-F313-Control-Gate-B",
        "beacon_interval": 100,
        "dtim_period": 3,
        "retry_count": 0,
        "ba_control": 65535,
        "ba_max": 64,
        "ampdu_density": 5,
        "tpc_interval": 30,
        "multicast_rate": 1000,
    }
    return fallback[key]


def wait_setting(api: Api, key: str, expected: object, timeout: int = 30) -> dict:
    deadline = time.monotonic() + timeout
    latest: dict = {}
    while time.monotonic() < deadline:
        latest = setting_map(api.get("radios/5g?view=contract"))
        if key in latest and str(latest[key].get("current")).lower() == str(expected).lower():
            return latest[key]
        time.sleep(1)
    raise RuntimeError(f"readback timeout {key}: expected={expected!r} actual={latest.get(key, {}).get('current')!r}")


def value_digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def runtime_health(api: Api) -> dict[str, object]:
    radio2 = api.get("radios/2g")
    radio5 = api.get("radios/5g")
    status = api.get("status")
    diagnostics = api.get("diagnostics")
    return {
        "radio2_ready": radio2.get("lifecycle") == "ap-ready" and radio2.get("state") in {"ENABLED", "ready"},
        "radio5_ready": radio5.get("lifecycle") == "ap-ready" and radio5.get("state") == "ready",
        "health_ready": status.get("health") == "ready",
        "fatal_count": int(diagnostics.get("fatal_count") or 0),
    }


def control_snapshot(api: Api) -> dict[str, object]:
    contract = api.get("radios/5g?view=contract")
    settings = setting_map(contract)
    snapshot = {key: settings[key]["current"] for key in EXPECTED_WRITABLE}
    radio = contract.get("snapshot", {}).get("status", {})
    snapshot["channel"] = radio.get("channel")
    snapshot["bandwidth"] = radio.get("bandwidth")
    return snapshot


def require_snapshot(actual: dict[str, object], expected: dict[str, object], context: str) -> None:
    mismatches = {
        key: {"expected": expected.get(key), "actual": actual.get(key)}
        for key in expected
        if value_digest(actual.get(key)) != value_digest(expected.get(key))
    }
    if mismatches:
        raise RuntimeError(f"{context} snapshot mismatch: {json.dumps(mismatches, sort_keys=True)}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--password-file", type=Path, default=DEVICE / "web_password.txt")
    parser.add_argument("--known-hosts", type=Path, default=DEFAULT_KNOWN_HOSTS)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    release_upper = RELEASE.upper()
    required_ack = f"OPENMITRASTAR_{release_upper}_QTN_CONTROL_MATRIX"
    print(json.dumps({
        "schema": f"openmitrastar.{RELEASE}-qtn-control-matrix-plan/v1",
        "mode": "execute" if args.execute else "dry-run",
        "firmware": EXPECTED_VERSION,
        "controls": EXPECTED_WRITABLE,
        "blocked_probes": ["channel", "bandwidth"] + (["tpc_interval"] if RELEASE == "f314" else []),
        "dfs": "fail-closed",
        "flash": False,
        "mtd_writes": False,
    }, indent=2))
    if not args.execute:
        return 0
    if args.ack != required_ack:
        raise SystemExit("exact --ack is required")

    api = Api(args.host, args.password_file)
    firmware = api.get("firmware")
    contract = api.get("radios/5g?view=contract")
    if firmware.get("version") != EXPECTED_VERSION:
        raise SystemExit(f"unexpected firmware: {firmware.get('version')}")
    writable = list(contract["capabilities"].get("writable_settings") or [])
    if writable != EXPECTED_WRITABLE:
        raise SystemExit(f"unexpected writable controls: {writable}")
    live_radio = contract.get("snapshot", {}).get("status", {})
    if int(live_radio.get("channel") or 0) not in {36, 40, 44, 48}:
        raise SystemExit(f"unsafe preflight: current 5 GHz channel is {live_radio.get('channel')}, expected non-DFS 36-48")
    if contract["capabilities"].get("dfs_linux510_backend_ready") is not False:
        raise SystemExit("unexpected DFS backend state for the F313 gate")
    initial_health = runtime_health(api)
    if not initial_health["radio2_ready"] or not initial_health["radio5_ready"] or not initial_health["health_ready"]:
        raise SystemExit(f"unhealthy preflight: {initial_health}")
    before_fatal = int(initial_health["fatal_count"])
    results: list[dict[str, object]] = []
    args.output_dir.mkdir(parents=True, exist_ok=True)
    checkpoint = args.output_dir / "checkpoint.json"

    if args.resume and checkpoint.exists():
        saved = json.loads(checkpoint.read_text(encoding="ascii"))
        if saved.get("firmware") != EXPECTED_VERSION:
            raise SystemExit("checkpoint firmware does not match the expected live image")
        results = list(saved.get("completed") or [])
        for row in results:
            key = str(row.get("key") or "")
            current = setting_map(api.get("radios/5g?view=contract"))[key]["current"]
            if value_digest(current) != row.get("original_digest"):
                raise SystemExit(f"checkpoint baseline mismatch for {key}")

    completed = {str(row.get("key")) for row in results}

    for key in EXPECTED_WRITABLE:
        if key in completed:
            print(f"OM{release_upper}_CONTROL_RESUME_SKIP key={key}", flush=True)
            continue
        baseline = control_snapshot(api)
        current = baseline[key]
        target = alternate(key, current)
        print(f"OM{release_upper}_CONTROL_START key={key}", flush=True)
        status, stage = api.post_form("radios/5g/stage", {key: target})
        if status != 200 or not isinstance(stage, dict) or stage.get("ok") is not True:
            raise RuntimeError(f"stage failed {key}: HTTP {status} {stage}")
        transaction_id = str(stage["transaction_id"])
        rolled_back = False
        caught: Exception | None = None
        try:
            status, apply = api.action("config/apply", transaction_id)
            if status != 200 or not isinstance(apply, dict) or apply.get("verified") is not True:
                raise RuntimeError(f"apply failed {key}: HTTP {status} {apply}")
            applied_row = wait_setting(api, key, target)
            applied_snapshot = control_snapshot(api)
            expected_applied = dict(baseline)
            expected_applied[key] = target
            require_snapshot(applied_snapshot, expected_applied, f"apply {key}")
            applied_health = runtime_health(api)
            ssh(args.host, args.known_hosts, "true")
            if (applied_health["fatal_count"] != before_fatal or not applied_health["radio2_ready"] or
                    not applied_health["radio5_ready"] or not applied_health["health_ready"]):
                raise RuntimeError(f"health regression while {key} was applied")
            status, rollback = api.action("config/rollback", transaction_id)
            if status != 200 or not isinstance(rollback, dict) or rollback.get("verified") is not True:
                raise RuntimeError(f"rollback failed {key}: HTTP {status} {rollback}")
            restored_row = wait_setting(api, key, current)
            restored_snapshot = control_snapshot(api)
            require_snapshot(restored_snapshot, baseline, f"rollback {key}")
            rolled_back = True
            health = runtime_health(api)
            ssh(args.host, args.known_hosts, "true")
            if (health["fatal_count"] != before_fatal or not health["radio2_ready"] or
                    not health["radio5_ready"] or not health["health_ready"]):
                raise RuntimeError(f"health regression after {key}")
            results.append({
                "key": key,
                "original": current if key != "ssid" else "redacted",
                "original_digest": value_digest(current),
                "target": target if key != "ssid" else "temporary-test-value",
                "apply_readback": applied_row["current"] if key != "ssid" else "matched",
                "rollback_readback": restored_row["current"] if key != "ssid" else "matched",
                "apply_full_snapshot": "matched",
                "rollback_full_snapshot": "matched",
                "applied_health": applied_health,
                **health,
                "ssh_alive": True,
                "status": "PASS",
            })
            checkpoint.write_text(json.dumps({
                "schema": f"openmitrastar.{RELEASE}-qtn-control-matrix-checkpoint/v1",
                "firmware": EXPECTED_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "completed": results,
                "next": EXPECTED_WRITABLE[len(results)] if len(results) < len(EXPECTED_WRITABLE) else None,
            }, indent=2, sort_keys=True) + "\n", encoding="ascii")
            print(f"OM{release_upper}_CONTROL_PASS key={key}", flush=True)
        except Exception as exc:
            caught = exc
        finally:
            if not rolled_back:
                try:
                    status, rollback = api.action("config/rollback", transaction_id)
                    if status != 200 or not isinstance(rollback, dict) or rollback.get("verified") is not True:
                        raise RuntimeError(f"emergency rollback failed {key}: HTTP {status} {rollback}")
                    wait_setting(api, key, current, timeout=45)
                    rolled_back = True
                except Exception as rollback_error:
                    if caught is not None:
                        raise RuntimeError(f"{caught}; emergency rollback failed: {rollback_error}") from caught
                    raise
        if caught is not None:
            checkpoint.write_text(json.dumps({
                "schema": f"openmitrastar.{RELEASE}-qtn-control-matrix-checkpoint/v1",
                "firmware": EXPECTED_VERSION,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "completed": results,
                "failed": {"key": key, "error": str(caught), "rollback_restored": rolled_back},
                "next": key,
            }, indent=2, sort_keys=True) + "\n", encoding="ascii")
            raise caught

    blocked: list[dict[str, object]] = []
    blocked_values = [("channel", 40), ("bandwidth", 40)]
    if RELEASE == "f314":
        blocked_values.append(("tpc_interval", 60))
    for key, value in blocked_values:
        status, payload = api.post_form("radios/5g/stage", {key: value})
        passed = status in {400, 409} and isinstance(payload, dict) and payload.get("ok") is False
        blocked.append({"key": key, "http_status": status, "payload": payload, "status": "PASS" if passed else "FAIL"})
        if not passed:
            raise RuntimeError(f"blocked control unexpectedly accepted: {key}")

    final_contract = api.get("radios/5g?view=contract")
    final_health = runtime_health(api)
    if (final_health["fatal_count"] != before_fatal or not final_health["radio2_ready"] or
            not final_health["radio5_ready"] or not final_health["health_ready"]):
        raise RuntimeError(f"final health gate failed: {final_health}")
    ssh_state = ssh(
        args.host,
        args.known_hosts,
        "set -e; test \"$(cat /run/openmitrastar/boot-state)\" = ready; "
        "/usr/sbin/om-radioctl status 2g | grep -q '\"state\":\"ENABLED\"'; "
        "/usr/sbin/om-radioctl status 5g | grep -q '\"state\":\"ready\"'; printf verified",
    )
    if ssh_state != "verified":
        raise RuntimeError(f"final SSH state gate failed: {ssh_state!r}")
    output = {
        "schema": f"openmitrastar.{RELEASE}-qtn-control-matrix/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS",
        "firmware": firmware["version"],
        "controls": results,
        "blocked_controls": blocked,
        "dfs": {
            "hardware_present": final_contract["capabilities"].get("dfs_hardware_present") is True,
            "linux510_backend_ready": final_contract["capabilities"].get("dfs_linux510_backend_ready") is True,
            "write_policy": "fail-closed",
        },
        "final_health": final_health,
        "fatal_count_before": before_fatal,
        "fatal_count_after": int(final_health["fatal_count"]),
        "ssh_readback": ssh_state,
        "flash": False,
        "mtd_writes": False,
        "secrets_logged": False,
    }
    path = args.output_dir / f"result-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    path.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(output, indent=2, sort_keys=True))
    print(f"OM{release_upper}_QTN_CONTROL_MATRIX_PASS={path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
