#!/usr/bin/env python3
"""Post-boot gate for F184 integrated datapath, packages and capabilities."""
from __future__ import annotations

import argparse
import json
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEY = Path.home() / ".ssh/id_ed25519"
INTEGRATED_GATE = ROOT / "tools/post_flash_f179_integrated_gate.py"


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def parse_json_line(text: str) -> dict:
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                return value
    return {}


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
            "--expected-version", "lyoko-foundation-1.4-f184",
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
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    remote = "OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 capabilities"
    proc = subprocess.run(
        [
            ssh, "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
            f"root@{args.host}", remote,
        ],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=60, check=False,
    )
    (out / "capabilities.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "capabilities.stderr.log").write_text(proc.stderr, encoding="utf-8")
    payload = parse_json_line(proc.stdout)
    items = payload.get("items", []) if isinstance(payload.get("items"), list) else []
    states = {str(item.get("state")) for item in items if isinstance(item, dict)}
    by_id = {str(item.get("id")): item for item in items if isinstance(item, dict)}
    checks = {
        "integrated_gate": integrated.returncode == 0 and integrated_status.get("status") == "PASS",
        "ssh": proc.returncode == 0 and tcp_open(args.host, 22),
        "schema": payload.get("schema") == "lyoko.api.capabilities/v1",
        "item_count": len(items) == 16,
        "state_vocabulary": states == {"available", "readonly", "experimental", "blocked", "unsupported", "certification_required"},
        "package_install_experimental": by_id.get("packages.volatile_install", {}).get("state") == "experimental",
        "persistent_store_certification_required": by_id.get("packages.persistent_store", {}).get("state") == "certification_required",
        "firmware_update_blocked": by_id.get("firmware.update", {}).get("state") == "blocked",
    }
    result = {
        "schema": "openmitrastar.f184-postflash/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "integrated_status": str(integrated_status_path),
        "stdout": str(out / "capabilities.stdout.log"),
        "stderr": str(out / "capabilities.stderr.log"),
        "flash": False,
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
