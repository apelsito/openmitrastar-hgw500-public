#!/usr/bin/env python3
"""Recover compact, secret-free F285 client evidence from AELITA."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
TARGET_SSID = "Lyoko-5G-Material-Test"
RESTORED_ROUTER_SSID = "MOVISTAR_PLUS_55CB"
EXPECTED_VERSION = "lyoko-foundation-6.3.9-f285-qtn-convergent-verify-device"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


assoc = load_module("f285_assoc_salvage", ROOT / "tools/run_f285_material_aelita_assoc.py")
wpa = assoc.wpa


def parse_key_values(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in text.splitlines():
        key, separator, value = line.partition("=")
        if separator and key.replace("_", "").isalnum():
            values[key] = value.strip()
    return values


def client_passed(oracle: dict) -> bool:
    test = oracle.get("test", {})
    restore = oracle.get("restore", {})
    authentication = str(test.get("authentication") or "").upper()
    cipher = str(test.get("cipher") or "").upper()
    band = str(test.get("band") or "")
    channel = str(test.get("channel") or "")
    return bool(
        oracle.get("execution_error") is None
        and test.get("connected") is True
        and test.get("ssid") == TARGET_SSID
        and ("5 GHZ" in band.upper() or channel == "36")
        and "WPA2" in authentication
        and cipher == "CCMP"
        and test.get("ipv4")
        and test.get("router_ping") is True
        and restore.get("connected") is True
        and oracle.get("profile_deleted") is True
        and oracle.get("secret_blob_deleted") is True
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oracle-host", default="192.168.1.63")
    parser.add_argument("--oracle-user", default="AELITA")
    parser.add_argument("--router-host", default="192.168.1.90")
    parser.add_argument("--remote-result", required=True)
    parser.add_argument("--material-result", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    wpa.validate_oracle_target(args.oracle_host, args.oracle_user)
    raw_oracle = wpa.read_remote_json(args.oracle_host, args.oracle_user, args.remote_result)
    oracle = assoc.compact_oracle(raw_oracle)
    material = json.loads(args.material_result.read_text(encoding="ascii"))

    command = r'''set +e
printf 'FIRMWARE='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'SSID='; /usr/sbin/om-qtnctl get ssid 2>/dev/null
printf 'CHANNEL='; /usr/sbin/om-qtnctl get channel 2>/dev/null
printf 'BANDWIDTH='; /usr/sbin/om-qtnctl get bandwidth 2>/dev/null
grep -q '"verified":true' /run/openmitrastar/qtn-material-trial/restore.log 2>/dev/null; printf 'RESTORE_VERIFIED=%s\n' "$?"
grep -q '"backend":"no-op"' /run/openmitrastar/qtn-material-trial/watchdog-restore.log 2>/dev/null; printf 'WATCHDOG_NOOP=%s\n' "$?"
fatal_count=$(dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|qdrv.*fatal|muc.*fatal|auc.*fatal' || true)
printf 'FATAL_COUNT=%s\n' "$fatal_count"
'''
    rc, stdout, stderr = wpa.router_ssh(args.router_host, command, timeout=20)
    if rc:
        raise SystemExit(f"router read-only recovery check failed rc={rc}: {stderr[:160]}")
    router = parse_key_values(stdout)
    router_recovered = bool(
        router.get("FIRMWARE") == EXPECTED_VERSION
        and router.get("SSID") == RESTORED_ROUTER_SSID
        and router.get("CHANNEL") == "36"
        and router.get("BANDWIDTH") == "80"
        and router.get("RESTORE_VERIFIED") == "0"
        and router.get("WATCHDOG_NOOP") == "0"
        and router.get("FATAL_COUNT") == "0"
    )
    association_pass = client_passed(oracle)
    status = "PASS" if association_pass and router_recovered else "FAIL"
    result = {
        "schema": "openmitrastar.f285-material-aelita-sanitized/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": status,
        "firmware": EXPECTED_VERSION,
        "association": {
            "status": "PASS" if association_pass else "FAIL",
            "ssid": oracle.get("test", {}).get("ssid"),
            "band": oracle.get("test", {}).get("band"),
            "channel": oracle.get("test", {}).get("channel"),
            "radio_type": oracle.get("test", {}).get("radio_type"),
            "authentication": oracle.get("test", {}).get("authentication"),
            "cipher": oracle.get("test", {}).get("cipher"),
            "signal": oracle.get("test", {}).get("signal"),
            "rssi_dbm": oracle.get("test", {}).get("rssi"),
            "receive_phy_mbps": oracle.get("test", {}).get("receive_mbps"),
            "transmit_phy_mbps": oracle.get("test", {}).get("transmit_mbps"),
            "dhcp_ipv4": bool(oracle.get("test", {}).get("ipv4")),
            "gateway_present": bool(oracle.get("test", {}).get("gateway")),
            "router_ping": oracle.get("test", {}).get("router_ping"),
        },
        "client_restore": {
            "status": "PASS" if oracle.get("restore", {}).get("connected") is True else "FAIL",
            "ssid": oracle.get("restore", {}).get("ssid"),
            "temporary_profile_deleted": oracle.get("profile_deleted"),
            "secret_blob_deleted": oracle.get("secret_blob_deleted"),
        },
        "router_restore": {
            "status": "PASS" if router_recovered else "FAIL",
            "ssid": router.get("SSID"),
            "channel": router.get("CHANNEL"),
            "bandwidth": router.get("BANDWIDTH"),
            "restore_apply_verified": router.get("RESTORE_VERIFIED") == "0",
            "watchdog_found_no_change": router.get("WATCHDOG_NOOP") == "0",
            "fatal_count": int(router.get("FATAL_COUNT", "-1")),
        },
        "material_gate": {
            "original_status": material.get("status"),
            "target_applied": material.get("target_marker"),
            "classification": "RESTORED_AFTER_READBACK_FALSE_NEGATIVE" if router_recovered else "UNRESOLVED",
        },
        "traffic_scope": "association-dhcp-router-ping-only",
        "secrets_logged": False,
        "client_macs_logged": False,
        "flash": False,
        "mtd_writes": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
