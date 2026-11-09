#!/usr/bin/env python3
"""Exercise the F247/F245 signed package catalog and volatile lifecycle."""
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
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--expected-version", default="lyoko-foundation-4.9-f245-device")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument(
        "--known-hosts",
        type=Path,
        default=Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f247-device-bound/known_hosts.f247",
    )
    args = parser.parse_args()
    required_ack = "OPENMITRASTAR_F247_PACKAGE_CATALOG_PHYSICAL"
    preview = {
        "mode": "execute" if args.execute else "dry-run",
        "host": args.host,
        "expected_version": args.expected_version,
        "queries": ["update", "search", "info", "depends", "plan"],
        "mutations": ["install lyoko-netdiag", "remove lyoko-netdiag"],
        "persistent_writes": False,
        "mtd5": "hash-before-after-only",
        "network_fetch": False,
        "maintainer_scripts": False,
    }
    print(json.dumps(preview, indent=2))
    if not args.execute:
        return 0
    if args.ack != required_ack:
        raise SystemExit("exact --ack is required")
    if not tcp_open(args.host) or not KEY.is_file() or not args.known_hosts.is_file():
        raise SystemExit("F247 SSH identity is unavailable")

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    remote = r'''
set -eu
api=/usr/libexec/openmitrastar/om-api-v1
ctl=/usr/sbin/om-package-api
body_install='action=install&package=lyoko-netdiag'
body_remove='action=remove&package=lyoko-netdiag'
trap '$ctl disable >/dev/null 2>&1 || true' EXIT HUP INT TERM
echo OMF247_PACKAGE_CATALOG_BEGIN
printf 'VERSION='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'BOOT='; cat /run/openmitrastar/boot-state
printf 'DATA_HASH_BEFORE='; sha256sum /dev/mtdblock2 | cut -d' ' -f1
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET QUERY_STRING='view=update' "$api" packages
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET QUERY_STRING='view=search&query=net' "$api" packages
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET QUERY_STRING='view=info&package=lyoko-netdiag' "$api" packages
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET QUERY_STRING='view=depends&package=lyoko-netdiag' "$api" packages
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET QUERY_STRING='view=plan&package=lyoko-netdiag' "$api" packages
$ctl enable
printf '%s' "$body_install" | OM_API_AUTH_BYPASS=1 REQUEST_METHOD=POST HTTP_X_OM_CSRF=development HTTP_X_OM_CONFIRM=OPENMITRASTAR_LYOKO_PKG_INSTALL_V1 CONTENT_LENGTH=${#body_install} "$api" packages
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET "$api" packages
printf '%s' "$body_remove" | OM_API_AUTH_BYPASS=1 REQUEST_METHOD=POST HTTP_X_OM_CSRF=development HTTP_X_OM_CONFIRM=OPENMITRASTAR_LYOKO_PKG_REMOVE_V1 CONTENT_LENGTH=${#body_remove} "$api" packages
$ctl disable
$ctl status
test ! -e /run/lyoko-packages/pkgs/lyoko-netdiag
test ! -e /run/lyoko-packages/state/lyoko-netdiag
printf 'DATA_HASH_AFTER='; sha256sum /dev/mtdblock2 | cut -d' ' -f1
printf 'FATAL_COUNT='; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Machine Check' || true
echo OMF247_PACKAGE_CATALOG_END
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
        timeout=300,
        check=False,
    )
    (out / "stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "stderr.log").write_text(proc.stderr, encoding="utf-8")
    before = next((line.split("=", 1)[1] for line in proc.stdout.splitlines() if line.startswith("DATA_HASH_BEFORE=")), "")
    after = next((line.split("=", 1)[1] for line in proc.stdout.splitlines() if line.startswith("DATA_HASH_AFTER=")), "")
    checks = {
        "ssh": proc.returncode == 0 and tcp_open(args.host),
        "firmware": f"VERSION={args.expected_version}" in proc.stdout,
        "boot_ready": "BOOT=ready" in proc.stdout,
        "update": '"operation":"update"' in proc.stdout and '"verified":true' in proc.stdout,
        "search": '"operation":"search"' in proc.stdout and '"query":"net"' in proc.stdout,
        "info": '"operation":"info"' in proc.stdout and '"kernel_abi":"5.10.260-openmitrastar-radiohw"' in proc.stdout,
        "depends": '"operation":"depends"' in proc.stdout,
        "plan": '"operation":"plan"' in proc.stdout and '"plan":["lyoko-netdiag"]' in proc.stdout,
        "install": '"action":"install"' in proc.stdout and '"result":"installed"' in proc.stdout,
        "inventory": '"runtime_installed_count":1' in proc.stdout,
        "remove": '"action":"remove"' in proc.stdout and '"result":"removed"' in proc.stdout,
        "gate_disabled_after": "state=disabled" in proc.stdout and "source=default" in proc.stdout,
        "mtd5_unchanged": bool(before) and before == after,
        "no_fatal": "FATAL_COUNT=0" in proc.stdout,
        "bounded_transcript": len(proc.stdout.encode("utf-8")) <= 49152 and len(proc.stderr.encode("utf-8")) <= 8192,
    }
    result = {
        "schema": "openmitrastar.f247-package-catalog-physical-gate/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "persistent_writes": False,
        "feature_gate_restored": "disabled",
        "stdout": str(out / "stdout.log"),
        "stderr": str(out / "stderr.log"),
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
