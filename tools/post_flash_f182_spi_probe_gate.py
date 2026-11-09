#!/usr/bin/env python3
"""Read-only post-boot acceptance gate for the F182 SPI probe."""
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
STORAGE_GATE = ROOT / "tools/post_flash_f180_storage_probe_gate.py"


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
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    storage_dir = out / "storage"
    storage = subprocess.run(
        [
            sys.executable, str(STORAGE_GATE), "--host", args.host,
            "--wait-seconds", str(args.wait_seconds),
            "--expected-version", "lyoko-foundation-1.3-f182",
            "--output-dir", str(storage_dir),
        ],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        timeout=args.wait_seconds + 180, check=False,
    )
    (out / "storage-gate.stdout.log").write_text(storage.stdout, encoding="utf-8")
    (out / "storage-gate.stderr.log").write_text(storage.stderr, encoding="utf-8")
    storage_status_path = storage_dir / "status.json"
    storage_status = json.loads(storage_status_path.read_text(encoding="ascii")) if storage_status_path.is_file() else {}

    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline and not tcp_open(args.host, 22):
        time.sleep(3)
    remote = r'''
echo OMF182_BEGIN
cat /run/openmitrastar/spi-probe.state 2>/dev/null || true
grep '^qtn_topaz_spi_probe ' /proc/modules 2>/dev/null || true
for name in jedec_id status_register expected_device write_capable; do
  printf 'PARAM_%s=' "$name"
  cat "/sys/module/qtn_topaz_spi_probe/parameters/$name" 2>/dev/null || true
done
dmesg | grep 'OMSPIPROBE' | tail -n 4
echo OMF182_END
'''
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    proc = subprocess.run(
        [
            ssh, "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes", "-o", "LogLevel=ERROR",
            f"root@{args.host}", remote,
        ],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90, check=False,
    )
    (out / "spi.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "spi.stderr.log").write_text(proc.stderr, encoding="utf-8")
    text = proc.stdout
    checks = {
        "storage_gate": storage.returncode == 0 and storage_status.get("status") == "PASS",
        "ssh": proc.returncode == 0 and tcp_open(args.host, 22),
        "transcript": "OMF182_BEGIN" in text and "OMF182_END" in text,
        "module_loaded": "qtn_topaz_spi_probe " in text and "status=loaded" in text,
        "jedec_id": "jedec_id=12722200" in text and "PARAM_jedec_id=12722200" in text,
        "expected_device": "expected_device=Y" in text and "PARAM_expected_device=Y" in text,
        "write_disabled": "write_capable=N" in text and "PARAM_write_capable=N" in text,
        "kernel_marker": "OMSPIPROBE" in text and "write_capable=0" in text,
    }
    result = {
        "schema": "openmitrastar.f182-spi-probe-postflash/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "write_attempted": False,
        "flash": False,
        "storage_status": str(storage_status_path),
        "stdout": str(out / "spi.stdout.log"),
        "stderr": str(out / "spi.stderr.log"),
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
