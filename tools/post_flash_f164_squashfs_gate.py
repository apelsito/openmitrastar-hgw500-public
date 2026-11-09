#!/usr/bin/env python3
"""Read-only post-boot acceptance gate for F164 SquashFS."""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEY = Path.home() / ".ssh/id_ed25519"


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--wait-seconds", type=int, default=240)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--expected-rootfs-size", default="00400000")
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline and not tcp_open(args.host, 22):
        time.sleep(3)
    tcp_before = tcp_open(args.host, 22)
    stdout_path = out / "router.stdout.log"
    stderr_path = out / "router.stderr.log"
    if not tcp_before:
        result = {"status": "FAIL", "reason": "ssh-timeout", "host": args.host}
        (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
        print(json.dumps(result, indent=2))
        return 2

    known_hosts = out / "known_hosts"
    remote = r'''
echo OMF164_BEGIN
uname -a
echo CMDLINE
cat /proc/cmdline
echo MTD
cat /proc/mtd
echo MOUNTS
mount
echo ROOT_RELEASE
cat /etc/openmitrastar/release 2>/dev/null || true
echo RADIO2G
i=0
while [ "$(/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 ping 2>/dev/null)" != PONG ] && [ "$i" -lt 60 ]; do
    i=$((i + 1))
    sleep 2
done
/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null || true
echo RADIO5
i=0
while [ "$(cat /run/openmitrastar/radio5g/state 2>/dev/null)" != ready ] && [ "$i" -lt 60 ]; do
    i=$((i + 1))
    sleep 2
done
cat /run/openmitrastar/radio5g/state 2>/dev/null || true
cat /run/openmitrastar/radio5g/ready 2>/dev/null || true
/usr/sbin/iwconfig-qtn wifi0 2>/dev/null || true
if [ -e /sys/class/net/br0/brif/wifi0 ]; then echo OMF164_BR0_WIFI0=1; else echo OMF164_BR0_WIFI0=0; fi
echo MEMORY
cat /proc/meminfo | head -n 12
echo FATAL
dmesg | grep -Ei 'MuC exception|MuC has halted|HLINK MSG timed out|EV_TLB|EV_ProtV|Oops:|BUG:|Kernel panic|panic:|VFS: Unable to mount root' | tail -n 40 || true
echo OMF164_END
'''
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    proc = subprocess.run(
        [ssh, "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
         "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=accept-new",
         "-o", f"UserKnownHostsFile={known_hosts}", "-o", "HostKeyAlgorithms=+ssh-rsa",
         "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa", "-o", "LogLevel=ERROR",
         f"root@{args.host}", remote],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=90, check=False,
    )
    stdout_path.write_text(proc.stdout, encoding="utf-8")
    stderr_path.write_text(proc.stderr, encoding="utf-8")
    text = proc.stdout
    checks = {
        "ssh": proc.returncode == 0 and tcp_open(args.host, 22),
        "transcript": "OMF164_BEGIN" in text and "OMF164_END" in text,
        "kernel": "5.10.260-openmitrastar-radiohw" in text,
        "root_cmdline": "root=31:3" in text and "rootfstype=squashfs" in text,
        "root_squashfs_ro": bool(re.search(r"(?m)^(?:/dev/root|rootfs) on / type squashfs \(ro[,)]", text)),
        "rootfs_mtd": bool(re.search(
            rf'(?m)^mtd3: {re.escape(args.expected_rootfs_size.lower())} 00010000 "rootfs_live"$',
            text.lower(),
        )),
        "run_tmpfs": bool(re.search(r"(?m)^tmpfs on /run type tmpfs", text)),
        "tmp_tmpfs": bool(re.search(r"(?m)^tmpfs on /tmp type tmpfs", text)),
        "persist_ro": bool(re.search(r"(?m)^/dev/mtdblock2 on /persist type jffs2 \(ro,", text)),
        "radio2g": bool(re.search(r"(?m)^state=ENABLED$", text)),
        "radio5_ready": bool(re.search(r"(?m)^ready$", text)),
        "radio5_txpower": "Tx-Power=21 dBm" in text,
        "wifi0_bridged": "OMF164_BR0_WIFI0=1" in text,
        "no_fatal": not bool(re.search(r"MuC exception|MuC has halted|HLINK MSG timed out|EV_TLB|EV_ProtV|Oops:|BUG:|Kernel panic|VFS: Unable to mount root", text, re.I)),
    }
    result = {
        "schema": "openmitrastar.f164-squashfs-postflash/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "stdout": str(stdout_path),
        "stderr": str(stderr_path),
        "flash": False,
        "uart": False,
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
