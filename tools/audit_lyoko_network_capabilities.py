#!/usr/bin/env python3
"""Audit Lyoko VLAN, multicast/IGMP and DFS capabilities without mutation."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import socket
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
KEY = Path.home() / ".ssh/id_ed25519"
F222_CONFIG = Path.home() / (
    ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f222-device-bound/"
    "openmitrastar-linux510-f222-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.config"
)
F171_CONFIG = next(
    (ROOT / "work/mission-state/q3-persistent-composite-f171-lyoko-foundation-health-fix/build").glob("*.config")
)
DEFAULT_CONFIG = F222_CONFIG if F222_CONFIG.is_file() else F171_CONFIG


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def config_value(text: str, name: str) -> str:
    if re.search(rf"(?m)^{re.escape(name)}=y$", text):
        return "y"
    if re.search(rf"(?m)^# {re.escape(name)} is not set$", text):
        return "n"
    return "unknown"


def parse_kv(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Z0-9_]+", key):
            result[key] = value.strip()
    return result


def nonnegative_int(value: str | None) -> int:
    return int(value) if value and value.isdigit() else 0


def tcp_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--kernel-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--wait-seconds", type=int, default=60)
    args = parser.parse_args()
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)

    deadline = time.monotonic() + args.wait_seconds
    while time.monotonic() < deadline and not tcp_open(args.host, 22):
        time.sleep(2)
    if not tcp_open(args.host, 22):
        raise SystemExit("router SSH unavailable")

    remote = r'''
printf 'KERNEL='; uname -r
printf 'BOOT_STATE='; cat /run/openmitrastar/boot-state 2>/dev/null || true
printf 'VLAN_DEVICE_COUNT='; if [ -r /proc/net/vlan/config ]; then awk 'NR>2 && NF {n++} END{print n+0}' /proc/net/vlan/config; else echo 0; fi
printf 'BRIDGE_MEMBERS='; first=1; for p in /sys/class/net/br0/brif/*; do [ -e "$p" ] || continue; [ "$first" = 1 ] || printf ','; first=0; printf '%s' "${p##*/}"; done; echo
printf 'IGMP_V4_GROUPS='; if [ -r /proc/net/igmp ]; then awk 'NR>1 && /^[[:space:]]+[0-9A-Fa-f]+/ {n++} END{print n+0}' /proc/net/igmp; else echo 0; fi
printf 'IGMP_V6_GROUPS='; if [ -r /proc/net/igmp6 ]; then awk 'NF {n++} END{print n+0}' /proc/net/igmp6; else echo 0; fi
printf 'BRIDGE_MULTICAST_SNOOPING='; cat /sys/class/net/br0/bridge/multicast_snooping 2>/dev/null || echo unavailable
printf 'BRIDGE_MULTICAST_QUERIER='; cat /sys/class/net/br0/bridge/multicast_querier 2>/dev/null || echo unavailable
printf 'BRIDGE_MULTICAST_ROUTER='; cat /sys/class/net/br0/bridge/multicast_router 2>/dev/null || echo unavailable
printf 'RADIO5_STATE='; cat /run/openmitrastar/radio5g/state 2>/dev/null || true
printf 'RADIO5_REGION_CODE='; /usr/sbin/iwpriv-qtn wifi0 get_region 2>/dev/null | sed -n 's/.*get_region:\([0-9][0-9]*\).*/\1/p'
printf 'RADIO5_FREQUENCY_GHZ='; /usr/sbin/iwconfig-qtn wifi0 2>/dev/null | sed -n 's/.*Frequency:\([0-9.]*\) GHz.*/\1/p' | head -n 1
'''
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    proc = subprocess.run(
        [
            ssh, "-i", str(KEY), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8", "-o", "StrictHostKeyChecking=yes",
            "-o", "LogLevel=ERROR", f"root@{args.host}", remote,
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=90,
        check=False,
    )
    (out / "router.stdout.log").write_text(proc.stdout, encoding="utf-8")
    (out / "router.stderr.log").write_text(proc.stderr, encoding="utf-8")
    values = parse_kv(proc.stdout)
    config = args.kernel_config.read_text(encoding="utf-8")
    options = {
        name: config_value(config, name)
        for name in (
            "CONFIG_BRIDGE", "CONFIG_VLAN_8021Q", "CONFIG_IP_MULTICAST",
            "CONFIG_IP_MROUTE", "CONFIG_BRIDGE_IGMP_SNOOPING",
        )
    }
    vlan_count = nonnegative_int(values.get("VLAN_DEVICE_COUNT"))
    region = "ES" if values.get("RADIO5_REGION_CODE") == "21317" else values.get("RADIO5_REGION_CODE", "")
    frequency = values.get("RADIO5_FREQUENCY_GHZ", "")
    dfs_frequency = frequency in {"5.26", "5.28", "5.3", "5.30", "5.32", "5.5", "5.50", "5.52", "5.54", "5.56"}
    result = {
        "schema": "openmitrastar.network-capabilities-audit/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "host": args.host,
        "read_only": True,
        "kernel": values.get("KERNEL", ""),
        "kernel_config": {
            "path": str(args.kernel_config),
            "sha256": sha256(args.kernel_config),
        },
        "boot_state": values.get("BOOT_STATE", ""),
        "kernel_options": options,
        "bridge_members": [item for item in values.get("BRIDGE_MEMBERS", "").split(",") if item],
        "vlan": {
            "status": "SUPPORTED_UNCONFIGURED" if options["CONFIG_VLAN_8021Q"] == "y" and vlan_count == 0 else "ACTIVE" if vlan_count else "UNSUPPORTED",
            "configured_devices": vlan_count,
            "gvrp": config_value(config, "CONFIG_VLAN_8021Q_GVRP"),
            "mvrp": config_value(config, "CONFIG_VLAN_8021Q_MVRP"),
        },
        "multicast": {
            "ipv4_kernel": options["CONFIG_IP_MULTICAST"],
            "ip_mroute": options["CONFIG_IP_MROUTE"],
            "bridge_igmp_snooping": options["CONFIG_BRIDGE_IGMP_SNOOPING"],
            "igmp_v4_groups": nonnegative_int(values.get("IGMP_V4_GROUPS")),
            "igmp_v6_groups": nonnegative_int(values.get("IGMP_V6_GROUPS")),
            "bridge_knobs": {
                "snooping": values.get("BRIDGE_MULTICAST_SNOOPING", "unavailable"),
                "querier": values.get("BRIDGE_MULTICAST_QUERIER", "unavailable"),
                "router": values.get("BRIDGE_MULTICAST_ROUTER", "unavailable"),
            },
        },
        "dfs": {
            "radio_state": values.get("RADIO5_STATE", ""),
            "region": region,
            "frequency_ghz": frequency,
            "currently_on_dfs_frequency": dfs_frequency,
            "cac_test": "NOT_RUN",
            "radar_test": "NOT_RUN",
        },
        "classification": {
            "vlan": "READY_FOR_TRAFFIC_TEST" if options["CONFIG_VLAN_8021Q"] == "y" else "KERNEL_BLOCKED",
            "igmp": "READY_FOR_TRAFFIC_TEST" if options["CONFIG_IP_MULTICAST"] == "y" and options["CONFIG_BRIDGE_IGMP_SNOOPING"] == "y" else "KERNEL_CONFIG_BLOCKED",
            "dfs": "REGION_READY_TEST_PENDING" if region == "ES" else "REGION_UNPROVEN",
        },
        "privacy": {"client_identifiers": "not_collected", "wireless_keys": "not_collected"},
    }
    (out / "audit.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if proc.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
