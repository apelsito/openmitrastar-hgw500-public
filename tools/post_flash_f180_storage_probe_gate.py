#!/usr/bin/env python3
"""Read-only post-boot gate for the F180 storage layout probe."""
from __future__ import annotations

import argparse
import json
import re
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--wait-seconds", type=int, default=300)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-version", default="lyoko-foundation-1.3-f180")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    base_dir = out / "base"
    base = subprocess.run(
        [
            sys.executable, str(BASE_GATE), "--host", args.host,
            "--wait-seconds", str(args.wait_seconds),
            "--expected-rootfs-size", "00460000",
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
echo OMF180_BEGIN
cat /proc/mtd
cat /proc/mounts
printf 'VERSION='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'STORE_HASH='; sha256sum /dev/mtdblock4 2>/dev/null | cut -d' ' -f1
echo OMF180_END
'''
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    proc = subprocess.run(
        [
            ssh, "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
            f"root@{args.host}", remote,
        ],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False,
    )
    (out / "storage.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "storage.stderr.log").write_text(proc.stderr, encoding="utf-8")
    text = proc.stdout
    checks = {
        "base_gate": base.returncode == 0 and base_status.get("status") == "PASS",
        "ssh": proc.returncode == 0 and tcp_open(args.host, 22),
        "transcript": "OMF180_BEGIN" in text and "OMF180_END" in text,
        "release": f"VERSION={args.expected_version}" in text,
        "rootfs_mtd3": bool(re.search(r'(?m)^mtd3: 00460000 00010000 "rootfs_live"$', text)),
        "store_mtd4": bool(re.search(r'(?m)^mtd4: 001c0000 00010000 "lyoko_store"$', text)),
        "store_unmounted": not bool(re.search(r'(?m)^/dev/mtdblock4\s+', text)),
        "store_readable": bool(re.search(r'(?m)^STORE_HASH=[0-9a-f]{64}$', text)),
    }
    result = {
        "schema": "openmitrastar.f180-storage-postflash/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "store_write_attempted": False,
        "flash": False,
        "base_status": str(base_status_path),
        "stdout": str(out / "storage.stdout.log"),
        "stderr": str(out / "storage.stderr.log"),
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
