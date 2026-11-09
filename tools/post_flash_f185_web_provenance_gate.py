#!/usr/bin/env python3
"""Post-boot gate for F185 Foundation identity, UI assets and F184 integration."""
from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEY = Path.home() / ".ssh/id_ed25519"
INTEGRATED_GATE = ROOT / "tools/post_flash_f179_integrated_gate.py"
EXPECTED = {
    "ui_version": "1.5.0",
    "build_id": "f0adf5af5b71dfde",
    "source": "lyoko-foundation-1.5-f185",
    "asset_bytes": 21478,
    "html_sha256": "82dcb93b7577fe7f6f5b09ac29dddaf953ca3bca8b65c17ac0f4f58062ef63d8",
    "js_sha256": "0f48855381416425489df606af1f820ad44dbe1229dbe14c96af7128ae3808cb",
    "css_sha256": "29cabb245663f39735605caba49ca9876aebf41844e28fb11abba0e3db688d15",
}


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def parse_json_line(text: str) -> dict:
    for line in text.splitlines():
        try:
            value = json.loads(line.strip())
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def ssh_command(host: str, command: str) -> subprocess.CompletedProcess[str]:
    ssh = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/OpenSSH/ssh.exe"
    return subprocess.run(
        [
            str(ssh), "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
            f"root@{host}", command,
        ],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    integrated_dir = out / "integrated"
    integrated = subprocess.run(
        [
            sys.executable, str(INTEGRATED_GATE), "--host", args.host,
            "--wait-seconds", str(args.wait_seconds),
            "--expected-version", "lyoko-foundation-1.5-f185",
            "--output-dir", str(integrated_dir),
        ],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=args.wait_seconds + 240, check=False,
    )
    (out / "integrated-gate.stdout.log").write_text(integrated.stdout, encoding="utf-8")
    (out / "integrated-gate.stderr.log").write_text(integrated.stderr, encoding="utf-8")
    integrated_status_path = integrated_dir / "status.json"
    integrated_status = json.loads(integrated_status_path.read_text(encoding="ascii")) if integrated_status_path.is_file() else {}

    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline and not tcp_open(args.host, 22):
        time.sleep(3)
    frontend_proc = ssh_command(args.host, "OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 frontend")
    hashes_proc = ssh_command(args.host, "sha256sum /www/dashboard.html /www/app.js /www/app.css")
    (out / "frontend.stdout.log").write_text(frontend_proc.stdout, encoding="utf-8")
    (out / "frontend.stderr.log").write_text(frontend_proc.stderr, encoding="utf-8")
    (out / "asset-hashes.stdout.log").write_text(hashes_proc.stdout, encoding="utf-8")
    (out / "asset-hashes.stderr.log").write_text(hashes_proc.stderr, encoding="utf-8")

    payload = parse_json_line(frontend_proc.stdout)
    remote_hashes = {}
    for line in hashes_proc.stdout.splitlines():
        parts = line.split()
        if len(parts) == 2:
            remote_hashes[Path(parts[1]).name] = parts[0].lower()
    assets = payload.get("assets", {}) if isinstance(payload.get("assets"), dict) else {}
    checks = {
        "integrated_gate": integrated.returncode == 0 and integrated_status.get("status") == "PASS",
        "ssh": frontend_proc.returncode == 0 and hashes_proc.returncode == 0 and tcp_open(args.host, 22),
        "schema": payload.get("schema") == "lyoko.api.frontend/v1",
        "runtime": payload.get("runtime") == "router",
        "ui_version": payload.get("ui_version") == EXPECTED["ui_version"],
        "build_id": payload.get("build_id") == EXPECTED["build_id"],
        "source": payload.get("source") == EXPECTED["source"],
        "asset_budget": payload.get("asset_bytes") == EXPECTED["asset_bytes"] and EXPECTED["asset_bytes"] < 64 * 1024,
        "metadata_hashes": all(assets.get(key) == EXPECTED[key] for key in ("html_sha256", "js_sha256", "css_sha256")),
        "file_hashes": (
            remote_hashes.get("dashboard.html") == EXPECTED["html_sha256"]
            and remote_hashes.get("app.js") == EXPECTED["js_sha256"]
            and remote_hashes.get("app.css") == EXPECTED["css_sha256"]
        ),
    }
    result = {
        "schema": "openmitrastar.f185-postflash/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "frontend": payload,
        "integrated_status": str(integrated_status_path),
        "flash": False,
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
