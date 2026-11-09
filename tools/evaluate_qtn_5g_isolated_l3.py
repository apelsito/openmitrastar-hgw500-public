#!/usr/bin/env python3
"""Evaluate the isolated-L3 Quantenna 5 GHz gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(windows: dict, router: dict, duration_min: int = 120) -> dict:
    failures: list[str] = []
    test = windows.get("test", {})
    restore = windows.get("restore", {})
    soak = test.get("soak", {})

    def need(ok: bool, name: str) -> None:
        if not ok:
            failures.append(name)

    need(windows.get("execution_error") in (None, ""), "windows_execution_error")
    need(test.get("mode") == "isolated-l3-static", "windows_mode")
    need(test.get("connected") is True, "windows_association")
    need(test.get("static_ipv4_applied") is True, "windows_static_ipv4")
    need((test.get("ipv4") or {}).get("ipv4") == "192.168.77.2", "windows_static_readback")
    need((test.get("router_ping") or {}).get("pass") is True, "windows_router_ping")
    need(int(soak.get("requested_seconds", 0)) >= duration_min, "windows_soak_duration")
    need(int(soak.get("samples", 0)) > 0, "windows_soak_samples")
    need(int(soak.get("connected_samples", -1)) == int(soak.get("samples", 0)), "windows_soak_continuity")
    need(int(soak.get("disconnects", 1)) == 0, "windows_disconnects")
    need(restore.get("connected") is True, "windows_primary_restored")
    restore_ip = restore.get("ipv4") or {}
    need(restore_ip.get("dhcp_enabled") is True, "windows_dhcp_restored")
    need(bool(restore_ip.get("ipv4")) and restore_ip.get("ipv4") != "192.168.77.2", "windows_restore_ipv4")

    need(router.get("isolated_l3") is True, "router_mode")
    need(router.get("br_5g_expected") == 0, "router_bridge_expectation")
    need(router.get("complete") is True, "router_monitor_complete")
    need(router.get("management_lost") is False, "router_management_continuity")
    need(router.get("health_failure") is False, "router_health")
    need(router.get("association_observed") is True, "router_association")
    need(float(router.get("duration_observed_seconds", 0)) >= duration_min * 0.95, "router_soak_duration")
    need(int(router.get("wifi_rx_delta", 0)) > 0, "router_wifi_rx")
    need(int(router.get("wifi_tx_delta", 0)) > 0, "router_wifi_tx")
    need(int(router.get("irq8_delta", 0)) > 0, "router_irq8")
    need(int(router.get("irq20_delta", 0)) > 0, "router_irq20")
    last = router.get("last_sample") or {}
    need(last.get("br_eth") == 1 and last.get("br_2g") == 1, "router_main_bridge_preserved")
    need(last.get("br_5g") == 0, "router_wifi0_not_bridged")
    need(last.get("radio2g") == 1, "router_radio2_preserved")

    bidirectional = (
        (test.get("router_ping") or {}).get("pass") is True
        and int(router.get("wifi_rx_delta", 0)) > 0
        and int(router.get("wifi_tx_delta", 0)) > 0
    )
    need(bidirectional, "direct_bidirectional_icmp")
    result = {
        "schema": "openmitrastar.qtn-5g-isolated-l3-evaluation/v1",
        "status": "PASS" if not failures else "FAIL",
        "failures": sorted(set(failures)),
        "network": {
            "router_wifi0": "192.168.77.1/24",
            "client_wifi": "192.168.77.2/24",
            "wifi0_in_br0": False,
            "direct_bidirectional_icmp": bidirectional,
            "main_management_preserved": router.get("management_lost") is False,
            "windows_primary_restored": restore.get("connected") is True,
        },
        "claims": {
            "internet": "OUT_OF_SCOPE",
            "dhcp_during_test": "NOT_USED",
            "wpa2": "UNVERIFIED",
            "dfs": "UNVERIFIED",
            "flash": False,
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("windows", type=Path)
    parser.add_argument("router", type=Path)
    parser.add_argument("--duration-min", type=int, default=120)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.windows.read_text(encoding="utf-8-sig")),
        json.loads(args.router.read_text(encoding="utf-8-sig")),
        args.duration_min,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
