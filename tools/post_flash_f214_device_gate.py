#!/usr/bin/env python3
"""Post-boot acceptance gate for the private, device-bound F214 image."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess
import time
import urllib.error
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
KEY = Path.home() / ".ssh/id_ed25519"
DEFAULT_EXPECTED_VERSION = "lyoko-foundation-3.0-f214-device"


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def http_get(url: str) -> tuple[int, str]:
    try:
        with urllib.request.urlopen(url, timeout=8) as response:
            return response.status, response.read(256 * 1024).decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(64 * 1024).decode("utf-8", "replace")
    except OSError as exc:
        return 0, str(exc)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--wait-seconds", type=int, default=360)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--device-dir", type=Path, required=True)
    parser.add_argument("--expected-version", default=DEFAULT_EXPECTED_VERSION)
    parser.add_argument("--known-hosts-name", default="known_hosts.f214")
    parser.add_argument(
        "--legacy-dashboard-policy",
        choices=("removed", "present", "ignore"),
        default="removed",
    )
    args = parser.parse_args()

    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    device_dir = args.device_dir.resolve()
    known_hosts = device_dir / args.known_hosts_name
    if not KEY.is_file() or not known_hosts.is_file():
        raise SystemExit("missing SSH key or pinned F214 known_hosts")

    remote = r'''
echo OMF214_BEGIN
printf 'KERNEL='; uname -r
printf 'PRODUCT_VERSION='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'BOOT_STATE='; cat /run/openmitrastar/boot-state 2>/dev/null || true
echo MTD_BEGIN
cat /proc/mtd
echo MTD_END
echo MOUNTS_BEGIN
mount
echo MOUNTS_END
printf 'RADIO2_STATE='; /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null | sed -n 's/^state=//p'
printf 'RADIO5_STATE='; cat /run/openmitrastar/radio5g/state 2>/dev/null || true
printf 'RADIO5_READY='; cat /run/openmitrastar/radio5g/ready 2>/dev/null || true
if [ -e /sys/class/net/br0/brif/wlan0 ]; then echo BR0_WLAN0=1; else echo BR0_WLAN0=0; fi
if [ -e /sys/class/net/br0/brif/wifi0 ]; then echo BR0_WIFI0=1; else echo BR0_WIFI0=0; fi
printf 'MEM_AVAILABLE_KB='; awk '/^MemAvailable:/{print $2}' /proc/meminfo
printf 'SSH_IDENTITY='; test -s /usr/share/openmitrastar/device-identity/dropbear_ed25519_host_key && echo present || echo missing
printf 'WEB_CREDENTIAL='; test -s /run/openmitrastar/secrets/web.password.sha256 && echo loaded || echo missing
printf 'PACKAGE_VERIFIER='; test -x /usr/bin/lyoko-ed25519-verify && echo present || echo missing
printf 'SPI_PROBE_STATE='; sed -n 's/^status=//p' /run/openmitrastar/spi-probe.state 2>/dev/null || true
printf 'MULTICAST_STATE='; sed -n 's/^support=//p' /run/openmitrastar/network/multicast.env 2>/dev/null || true
printf 'FATAL_COUNT='; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|VFS: Unable to mount root' || true
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 status
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 firmware
OM_API_AUTH_BYPASS=1 REQUEST_METHOD=GET /usr/libexec/openmitrastar/om-api-v1 storage
echo OMF214_END
'''
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    command = [
        ssh,
        "-i", str(KEY),
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={known_hosts}",
        "-o", "LogLevel=ERROR",
        f"root@{args.host}",
        remote,
    ]
    deadline = time.monotonic() + args.wait_seconds
    proc = subprocess.CompletedProcess(command, 255, "", "SSH did not become ready")
    attempts = 0
    while time.monotonic() < deadline:
        if not tcp_open(args.host, 22):
            time.sleep(3)
            continue
        attempts += 1
        proc = subprocess.run(
            command,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=45,
            check=False,
        )
        text = proc.stdout
        ready = (
            proc.returncode == 0
            and f"PRODUCT_VERSION={args.expected_version}" in text
            and "BOOT_STATE=ready" in text
            and "RADIO2_STATE=ENABLED" in text
            and "RADIO5_STATE=ready" in text
            and "RADIO5_READY=ready" in text
            and "BR0_WLAN0=1" in text
            and "BR0_WIFI0=1" in text
        )
        if ready:
            break
        time.sleep(3)
    (out / "router.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "router.stderr.log").write_text(proc.stderr, encoding="utf-8")

    login_status, login_body = http_get(f"http://{args.host}/login.html")
    dashboard_status, dashboard_body = http_get(f"http://{args.host}/dashboard.cgi")
    legacy_dashboard_status, legacy_dashboard_body = http_get(f"http://{args.host}/dashboard.html")
    api_status, api_body = http_get(f"http://{args.host}/api/v1/status")
    (out / "login.html").write_text(login_body, encoding="utf-8")
    (out / "dashboard-response.txt").write_text(dashboard_body, encoding="utf-8")
    (out / "legacy-dashboard-response.txt").write_text(legacy_dashboard_body, encoding="utf-8")
    (out / "api-status-response.txt").write_text(api_body, encoding="utf-8")

    text = proc.stdout
    checks = {
        "ssh_pinned_identity": proc.returncode == 0 and tcp_open(args.host, 22),
        "transcript": "OMF214_BEGIN" in text and "OMF214_END" in text,
        "kernel": "KERNEL=5.10.260-openmitrastar-radiohw" in text,
        "release": f"PRODUCT_VERSION={args.expected_version}" in text,
        "boot_ready": "BOOT_STATE=ready" in text,
        "rootfs_window": 'mtd3: 00460000 00010000 "rootfs_live"' in text.lower(),
        "store_window": 'mtd4: 001c0000 00010000 "lyoko_store"' in text.lower(),
        "root_squashfs_ro": " on / type squashfs (ro," in text,
        "run_tmpfs": "tmpfs on /run type tmpfs" in text,
        "tmp_tmpfs": "tmpfs on /tmp type tmpfs" in text,
        "persist_ro": " on /persist type jffs2 (ro," in text,
        "radio2_ready": "RADIO2_STATE=ENABLED" in text,
        "radio5_ready": "RADIO5_STATE=ready" in text and "RADIO5_READY=ready" in text,
        "bridge_members": "BR0_WLAN0=1" in text and "BR0_WIFI0=1" in text,
        "device_identity": "SSH_IDENTITY=present" in text,
        "web_credential": "WEB_CREDENTIAL=loaded" in text,
        "package_verifier": "PACKAGE_VERIFIER=present" in text,
        "spi_probe_disabled": "SPI_PROBE_STATE=disabled" in text,
        "multicast_initialized": "MULTICAST_STATE=available" in text or "MULTICAST_STATE=pending" in text,
        "api_status": '"schema":"lyoko.api.status/v1"' in text,
        "api_firmware": '"schema":"lyoko.api.firmware/v1"' in text and args.expected_version in text,
        "api_storage": '"schema":"lyoko.api.storage/v1"' in text,
        "login_page": login_status == 200 and "Mira debajo" in login_body and "movistar-logo" in login_body,
        "dashboard_protected": dashboard_status in {401, 403, 404} or "Mira debajo" in dashboard_body,
        "legacy_dashboard_removed": (
            legacy_dashboard_status == 404
            if args.legacy_dashboard_policy == "removed"
            else legacy_dashboard_status == 200
            if args.legacy_dashboard_policy == "present"
            else True
        ),
        "api_protected": api_status in {401, 403},
        "no_fatal": "FATAL_COUNT=0" in text,
    }
    result = {
        "schema": "openmitrastar.f214-device-postflash/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "readiness_attempts": attempts,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "http": {
            "login": login_status,
            "dashboard_unauthenticated": dashboard_status,
            "legacy_dashboard": legacy_dashboard_status,
            "api_status_unauthenticated": api_status,
        },
        "legacy_dashboard_policy": args.legacy_dashboard_policy,
        "stdout": str(out / "router.stdout.log"),
        "stderr": str(out / "router.stderr.log"),
        "flash": False,
        "write_target": "mtd4/linux_live",
    }
    (out / "status.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
