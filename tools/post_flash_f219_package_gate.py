#!/usr/bin/env python3
"""Validate the signed Lyoko package lifecycle on physical F219."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess


ROOT = Path(__file__).resolve().parents[1]
KEY = Path.home() / ".ssh/id_ed25519"


def tcp_open(host: str, port: int = 22, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-version", default="lyoko-foundation-3.4-f219-device")
    parser.add_argument(
        "--known-hosts",
        type=Path,
        default=Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f219-device-bound/known_hosts.f219",
    )
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if not tcp_open(args.host) or not KEY.is_file() or not args.known_hosts.is_file():
        raise SystemExit("F219 SSH identity is unavailable")

    remote = r'''
set -eu
root=/run/lyoko-packages/f219-physical-gate
echo OMF219_PKG_BEGIN
printf 'VERSION='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'BOOT='; cat /run/openmitrastar/boot-state
printf 'DATA_HASH_BEFORE='; sha256sum /dev/mtdblock2 | cut -d' ' -f1
test -x /usr/bin/lyoko-ed25519-verify
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 packages
LYOKO_PKG_RUN_ROOT="$root" /usr/bin/lyoko-pkg status
LYOKO_PKG_RUN_ROOT="$root" /usr/bin/lyoko-pkg verify lyoko-netdiag
LYOKO_PKG_RUN_ROOT="$root" /usr/bin/lyoko-pkg install lyoko-netdiag
LYOKO_PKG_RUN_ROOT="$root" /usr/bin/lyoko-pkg list-installed
LYOKO_PKG_RUN_ROOT="$root" /usr/bin/lyoko-pkg exec lyoko-netdiag lyoko-netdiag
LYOKO_PKG_RUN_ROOT="$root" /usr/bin/lyoko-pkg remove lyoko-netdiag
if [ ! -e "$root/pkgs/lyoko-netdiag" ] && [ ! -e "$root/state/lyoko-netdiag" ]; then echo PACKAGE_CLEAN=1; else echo PACKAGE_CLEAN=0; fi
rm -rf "$root"
printf 'DATA_HASH_AFTER='; sha256sum /dev/mtdblock2 | cut -d' ' -f1
printf 'FATAL_COUNT='; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Machine Check' || true
echo OMF219_PKG_END
'''
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    proc = subprocess.run(
        [
            ssh, "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={args.known_hosts}", "-o", "LogLevel=ERROR",
            f"root@{args.host}", remote,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=240,
        check=False,
    )
    (out / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "stderr.log").write_text(proc.stderr, encoding="utf-8")
    before = next((line.split("=", 1)[1] for line in proc.stdout.splitlines() if line.startswith("DATA_HASH_BEFORE=")), "")
    after = next((line.split("=", 1)[1] for line in proc.stdout.splitlines() if line.startswith("DATA_HASH_AFTER=")), "")
    checks = {
        "ssh": proc.returncode == 0 and tcp_open(args.host),
        "transcript": "OMF219_PKG_BEGIN" in proc.stdout and "OMF219_PKG_END" in proc.stdout,
        "firmware": f"VERSION={args.expected_version}" in proc.stdout,
        "boot_ready": "BOOT=ready" in proc.stdout,
        "api_signed_feed": '"schema":"lyoko.api.packages/v1"' in proc.stdout and '"signature_verified":true' in proc.stdout,
        "verify": "LYOKO_PKG_VERIFY_PASS package=lyoko-netdiag" in proc.stdout,
        "install": "LYOKO_PKG_INSTALL_PASS package=lyoko-netdiag" in proc.stdout,
        "exec": "bridge_members=" in proc.stdout and "eth0_rx_errors=" in proc.stdout,
        "remove": "LYOKO_PKG_REMOVE_PASS package=lyoko-netdiag" in proc.stdout and "PACKAGE_CLEAN=1" in proc.stdout,
        "mtd5_unchanged": bool(before) and before == after,
        "no_fatal": "FATAL_COUNT=0" in proc.stdout,
    }
    result = {
        "schema": "openmitrastar.f219-package-physical-gate/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "runtime_root": "/run/lyoko-packages/f219-physical-gate",
        "persistent_writes": False,
        "flash": False,
        "stdout": str(out / "stdout.log"),
        "stderr": str(out / "stderr.log"),
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
