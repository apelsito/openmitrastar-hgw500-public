#!/usr/bin/env python3
"""Validate F179 Foundation, NAPI identity and volatile package manager."""
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
BASE_GATE = ROOT / "tools/post_flash_f171_foundation_gate.py"


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-version", default="lyoko-foundation-1.3-f179")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    base_dir = out / "base"
    base = subprocess.run(
        [
            sys.executable, str(BASE_GATE), "--host", args.host,
            "--wait-seconds", str(args.wait_seconds),
            "--expected-version", args.expected_version,
            "--expected-rootfs-size", "00620000",
            "--output-dir", str(base_dir),
        ],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=args.wait_seconds + 150, check=False,
    )
    (out / "base.stdout.log").write_text(base.stdout, encoding="utf-8")
    (out / "base.stderr.log").write_text(base.stderr, encoding="utf-8")
    base_status_path = base_dir / "status.json"
    base_status = json.loads(base_status_path.read_text(encoding="ascii")) if base_status_path.is_file() else {}

    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline and not tcp_open(args.host, 22):
        time.sleep(3)

    remote = r'''
echo OMF179_BEGIN
printf 'NAPI_WEIGHT='; sed -n 's/^napi_weight=//p' /sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats
printf 'DATA_HASH_BEFORE='; sha256sum /dev/mtdblock2 | cut -d' ' -f1
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 packages
LYOKO_PKG_RUN_ROOT=/run/lyoko-packages/f179-gate /usr/bin/lyoko-pkg status
echo OMF179_LIST_BEGIN
LYOKO_PKG_RUN_ROOT=/run/lyoko-packages/f179-gate /usr/bin/lyoko-pkg list
echo OMF179_LIST_END
LYOKO_PKG_RUN_ROOT=/run/lyoko-packages/f179-gate /usr/bin/lyoko-pkg verify lyoko-netdiag
LYOKO_PKG_RUN_ROOT=/run/lyoko-packages/f179-gate /usr/bin/lyoko-pkg install lyoko-netdiag
LYOKO_PKG_RUN_ROOT=/run/lyoko-packages/f179-gate /usr/bin/lyoko-pkg list-installed
(LYOKO_PKG_RUN_ROOT=/run/lyoko-packages/f179-gate /usr/bin/lyoko-pkg exec lyoko-netdiag lyoko-netdiag)
LYOKO_PKG_RUN_ROOT=/run/lyoko-packages/f179-gate /usr/bin/lyoko-pkg remove lyoko-netdiag
if [ ! -e /run/lyoko-packages/f179-gate/pkgs/lyoko-netdiag ] && [ ! -e /run/lyoko-packages/f179-gate/state/lyoko-netdiag ]; then echo PACKAGE_CLEAN=1; else echo PACKAGE_CLEAN=0; fi
rm -rf /run/lyoko-packages/f179-gate
printf 'DATA_HASH_AFTER='; sha256sum /dev/mtdblock2 | cut -d' ' -f1
printf 'FATAL_COUNT='; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV' || true
echo OMF179_END
'''
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    proc = subprocess.run(
        [
            ssh, "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
            f"root@{args.host}", remote,
        ],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180, check=False,
    )
    (out / "integrated.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "integrated.stderr.log").write_text(proc.stderr, encoding="utf-8")
    text = proc.stdout
    before = next((line.split("=", 1)[1] for line in text.splitlines() if line.startswith("DATA_HASH_BEFORE=")), "")
    after = next((line.split("=", 1)[1] for line in text.splitlines() if line.startswith("DATA_HASH_AFTER=")), "")
    checks = {
        "base_gate": base.returncode == 0 and base_status.get("status") == "PASS",
        "ssh": proc.returncode == 0 and tcp_open(args.host, 22),
        "transcript": "OMF179_BEGIN" in text and "OMF179_END" in text,
        "napi_weight": "NAPI_WEIGHT=128" in text,
        "package_api": '"schema":"lyoko.api.packages/v1"' in text and '"signature_verified":true' in text,
        "runtime_install_disabled_by_api": '"runtime_install_enabled":false' in text,
        "bundled_packages": "lyoko-netdiag 1.0.0-1" in text and "lyoko-sysinfo 1.0.0-1" in text,
        "verify": "LYOKO_PKG_VERIFY_PASS package=lyoko-netdiag" in text,
        "install": "LYOKO_PKG_INSTALL_PASS package=lyoko-netdiag" in text,
        "exec": "bridge_members=" in text and "eth0_rx_errors=" in text,
        "remove": "LYOKO_PKG_REMOVE_PASS package=lyoko-netdiag" in text and "PACKAGE_CLEAN=1" in text,
        "mtd5_unchanged": bool(before) and before == after,
        "no_fatal": "FATAL_COUNT=0" in text,
    }
    result = {
        "schema": "openmitrastar.f179-postflash/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "base_status": str(base_status_path),
        "stdout": str(out / "integrated.stdout.log"),
        "stderr": str(out / "integrated.stderr.log"),
        "flash": False,
        "runtime_package_root": "/run/lyoko-packages/f179-gate",
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
