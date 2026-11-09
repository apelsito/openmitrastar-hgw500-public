#!/usr/bin/env python3
"""Read-only F171 acceptance gate plus an isolated no-op transaction."""
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
BASE_GATE = ROOT / "tools/post_flash_f164_squashfs_gate.py"


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def json_rows(text: str) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            rows.append(value)
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-version", default="lyoko-foundation-1.0-f171")
    parser.add_argument("--expected-rootfs-size", default="00620000")
    args = parser.parse_args()

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    base_dir = out / "base"
    base = subprocess.run(
        [
            sys.executable, str(BASE_GATE), "--host", args.host,
            "--wait-seconds", str(args.wait_seconds),
            "--expected-rootfs-size", args.expected_rootfs_size,
            "--output-dir", str(base_dir),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=args.wait_seconds + 120,
        check=False,
    )
    (out / "base-gate.stdout.log").write_text(base.stdout, encoding="utf-8")
    (out / "base-gate.stderr.log").write_text(base.stderr, encoding="utf-8")
    base_status_path = base_dir / "status.json"
    base_status = json.loads(base_status_path.read_text(encoding="ascii")) if base_status_path.is_file() else {}

    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline and not tcp_open(args.host, 22):
        time.sleep(3)

    remote = r'''
echo OMF171_BEGIN
printf 'BOOT_STATE='; cat /run/openmitrastar/boot-state 2>/dev/null || true
printf 'PRODUCT_VERSION='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 status
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 radios/2g
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 radios/5g
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 firmware
txn=/run/openmitrastar/f171-gate.$$
mkdir -p "$txn"
channel=$(awk -F= '$1=="RADIO2G_CHANNEL"{print $2;exit}' /run/openmitrastar/config/active.conf)
printf 'band=2g\nchannel=%s\n' "$channel" >"$txn/pending-v1.conf"
OM_TXN_DIR="$txn" /usr/sbin/om-config-transaction apply
if [ ! -e "$txn/pending-v1.conf" ] && [ ! -e "$txn/rollback-v1.conf" ]; then echo TXN_CLEAN=1; else echo TXN_CLEAN=0; fi
rm -rf "$txn"
echo OMF171_END
'''
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    proc = subprocess.run(
        [
            ssh, "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes",
            "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
            "-o", "LogLevel=ERROR", f"root@{args.host}", remote,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
        check=False,
    )
    (out / "foundation.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "foundation.stderr.log").write_text(proc.stderr, encoding="utf-8")
    rows = json_rows(proc.stdout)
    by_schema = {str(row.get("schema")): row for row in rows}
    radio = [row for row in rows if row.get("schema") == "lyoko.api.radio/v1"]
    radio2 = next((row for row in radio if row.get("id") == "2g"), {})
    radio5 = next((row for row in radio if row.get("id") == "5g"), {})
    firmware = by_schema.get("lyoko.api.firmware/v1", {})
    transaction = by_schema.get("lyoko.config.apply/v1", {})
    forbidden = {"psk", "passphrase", "private_key", "calibration", "client_mac"}
    exposed = sorted(forbidden.intersection({key.lower() for row in rows for key in row}))
    checks = {
        "base_gate": base.returncode == 0 and base_status.get("status") == "PASS",
        "ssh_strict_host_key": proc.returncode == 0 and tcp_open(args.host, 22),
        "transcript": "OMF171_BEGIN" in proc.stdout and "OMF171_END" in proc.stdout,
        "boot_ready": "BOOT_STATE=ready" in proc.stdout,
        "release": f"PRODUCT_VERSION={args.expected_version}" in proc.stdout,
        "api_status": by_schema.get("lyoko.api.status/v1", {}).get("ok") is True,
        "radio2": radio2.get("state") == "ENABLED" and radio2.get("passphrase_set") is True,
        "radio5": radio5.get("state") == "ready" and int(radio5.get("tx_power_dbm", 0)) > 0,
        "firmware": firmware.get("version") == args.expected_version and bool(firmware.get("build_id")),
        "no_op_transaction": (
            transaction.get("verified") is True
            and transaction.get("commit") == "no-op"
            and transaction.get("rollback_available") is False
            and "TXN_CLEAN=1" in proc.stdout
        ),
        "privacy": not exposed,
    }
    result = {
        "schema": "openmitrastar.f171-foundation-postflash/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "privacy_exposed_keys": exposed,
        "base_status": str(base_status_path),
        "stdout": str(out / "foundation.stdout.log"),
        "stderr": str(out / "foundation.stderr.log"),
        "flash": False,
        "uart": False,
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
