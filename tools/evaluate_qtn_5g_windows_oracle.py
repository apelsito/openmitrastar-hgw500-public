#!/usr/bin/env python3
"""Evaluate Windows-oracle and router telemetry for the 5 GHz RAM-only gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(windows: dict, router: dict, *, duration_min: int = 600,
             mbps_min: float = 5.0, ratio_min: float = 0.5,
             bytes_min: int = 8 * 1024 * 1024) -> dict:
    failures: list[str] = []
    test = windows.get("test", {})
    restore = windows.get("restore", {})
    ipv4 = test.get("ipv4") or {}
    download = test.get("ap_to_client") or {}
    upload = test.get("client_to_ap") or {}
    internet = test.get("internet_https") or {}
    soak = test.get("soak") or {}

    def need(value: bool, name: str) -> None:
        if not value:
            failures.append(name)

    need(windows.get("execution_error") in (None, ""), "windows_execution_error")
    need(test.get("connected") is True, "windows_test_ssid_connected")
    if windows.get("expected_bssid"):
        need(test.get("bssid_match") is True, "windows_bssid_match")
    need(test.get("dhcp") is True, "windows_dhcp")
    need(ipv4.get("dhcp_enabled") is True, "windows_dhcp_enabled")
    need(bool(ipv4.get("ipv4")), "windows_ipv4")
    need(bool(ipv4.get("gateway")), "windows_gateway")
    need(bool(ipv4.get("dns_servers")), "windows_dns_servers")
    need((test.get("router_ping") or {}).get("pass") is True, "windows_router_ping")
    controller_reachable = (
        (test.get("controller_ping") or {}).get("pass") is True
        or download.get("pass") is True
        or upload.get("pass") is True
    )
    need(controller_reachable, "windows_controller_reachability")
    need(test.get("dns_ok") is True, "windows_dns")
    need(internet.get("pass") is True, "windows_internet_https")
    need(int(internet.get("bytes", 0)) > 0, "windows_internet_bytes")
    need(restore.get("connected") is True, "windows_primary_network_restored")
    need(bool((restore.get("ipv4") or {}).get("ipv4")), "windows_restore_ipv4")

    down_mbps = float(download.get("mbps", 0.0))
    up_mbps = float(upload.get("mbps", 0.0))
    ratio = min(down_mbps, up_mbps) / max(down_mbps, up_mbps) if down_mbps > 0 and up_mbps > 0 else 0.0
    need(download.get("pass") is True, "ap_to_client_http")
    need(int(download.get("bytes", 0)) >= bytes_min, "ap_to_client_bytes")
    need(down_mbps >= mbps_min, "ap_to_client_mbps")
    need(upload.get("pass") is True, "client_to_ap_http")
    need(int(upload.get("bytes", 0)) >= bytes_min, "client_to_ap_bytes")
    need(up_mbps >= mbps_min, "client_to_ap_mbps")
    need(ratio >= ratio_min, "directional_ratio")

    requested = int(soak.get("requested_seconds", 0))
    samples = int(soak.get("samples", 0))
    connected_samples = int(soak.get("connected_samples", 0))
    need(requested >= duration_min, "windows_soak_duration")
    need(samples > 0 and connected_samples == samples, "windows_soak_continuity")
    need(int(soak.get("disconnects", 1)) == 0, "windows_disconnects")

    need(router.get("complete") is True, "router_monitor_complete")
    need(router.get("management_lost") is False, "router_management_continuity")
    need(router.get("health_failure") is False, "router_health")
    need(router.get("association_observed") is True, "router_association")
    need(float(router.get("duration_observed_seconds", 0)) >= duration_min * 0.95,
         "router_soak_duration")
    need(int(router.get("irq8_delta", 0)) > 0, "router_irq8_progress")
    need(int(router.get("irq20_delta", 0)) > 0, "router_irq20_progress")

    ap_to_client = (
        download.get("pass") is True
        and int(router.get("wifi_tx_delta", 0)) > 0
        and int(router.get("eth_rx_delta", 0)) > 0
    )
    client_to_ap = (
        upload.get("pass") is True
        and int(router.get("wifi_rx_delta", 0)) > 0
        and int(router.get("eth_tx_delta", 0)) > 0
    )
    need(ap_to_client, "ap_to_client_router_correlation")
    need(client_to_ap, "client_to_ap_router_correlation")

    result = {
        "schema": "openmitrastar.qtn-5g-windows-oracle-evaluation/v1",
        "status": "PASS" if not failures else "FAIL",
        "failures": sorted(set(failures)),
        "directions": {
            "ap_to_client": ap_to_client,
            "client_to_ap": client_to_ap,
        },
        "observed": {
            "download_mbps": down_mbps,
            "upload_mbps": up_mbps,
            "directional_ratio": round(ratio, 6),
            "windows_samples": samples,
            "router_samples": int(router.get("samples_observed", 0)),
            "wifi_rx_delta": int(router.get("wifi_rx_delta", 0)),
            "wifi_tx_delta": int(router.get("wifi_tx_delta", 0)),
            "eth_rx_delta": int(router.get("eth_rx_delta", 0)),
            "eth_tx_delta": int(router.get("eth_tx_delta", 0)),
        },
        "thresholds": {
            "duration_seconds_min": duration_min,
            "per_direction_mbps_min": mbps_min,
            "per_direction_bytes_min": bytes_min,
            "directional_ratio_min": ratio_min,
            "disconnects": 0,
            "restore_required": True,
        },
        "claims": {
            "dhcp": test.get("dhcp") is True,
            "dns": test.get("dns_ok") is True,
            "internet_https": internet.get("pass") is True,
            "performance": down_mbps >= mbps_min and up_mbps >= mbps_min and ratio >= ratio_min,
            "primary_network_restored": restore.get("connected") is True,
            "controller_reachable": controller_reachable,
            "flash": False,
            "dfs": "UNVERIFIED",
            "wpa2": "UNVERIFIED",
        },
    }
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("windows", type=Path)
    parser.add_argument("router", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration-min", type=int, default=600)
    parser.add_argument("--mbps-min", type=float, default=5.0)
    parser.add_argument("--ratio-min", type=float, default=0.5)
    parser.add_argument("--bytes-min", type=int, default=8 * 1024 * 1024)
    args = parser.parse_args()
    result = evaluate(
        json.loads(args.windows.read_text(encoding="utf-8-sig")),
        json.loads(args.router.read_text(encoding="utf-8-sig")),
        duration_min=args.duration_min,
        mbps_min=args.mbps_min,
        ratio_min=args.ratio_min,
        bytes_min=args.bytes_min,
    )
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
