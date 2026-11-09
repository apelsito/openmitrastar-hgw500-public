#!/usr/bin/env python3
"""Evaluate the AELITA 2.4 GHz WPA2 runtime oracle result."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


def evaluate(result: dict, *, duration_min: int = 600, http_bytes_min: int = 1) -> dict:
    failures: list[str] = []
    test = result.get("test") or {}
    restore = result.get("restore") or {}
    ipv4 = test.get("ipv4") or {}
    ping = test.get("router_ping") or {}
    download = test.get("controller_download")
    soak = test.get("soak") or {}

    def need(condition: bool, name: str) -> None:
        if not condition:
            failures.append(name)

    need(result.get("execution_error") in (None, ""), "execution_error")
    need(result.get("router_mutations") is False, "router_mutations")
    need(result.get("flash") is False, "flash")
    need(result.get("secret_blob_deleted") is True, "secret_blob_deleted")
    need(result.get("profile_deleted") is True, "profile_deleted")

    need(test.get("connected") is True, "test_ssid_connected")
    need(bool(ipv4.get("ipv4")), "test_ipv4")
    need(bool(ipv4.get("gateway")), "test_gateway")
    need(ping.get("pass") is True, "router_ping")

    if download is not None:
        need(download.get("pass") is True, "controller_download")
        need(int(download.get("bytes", 0)) >= http_bytes_min, "controller_download_bytes")

    requested = int(soak.get("requested_seconds", 0))
    samples = int(soak.get("samples", 0))
    connected_samples = int(soak.get("connected_samples", 0))
    disconnects = int(soak.get("disconnects", 1))
    need(requested >= duration_min, "soak_duration")
    need(samples > 0, "soak_samples")
    need(connected_samples == samples, "soak_continuity")
    need(disconnects == 0, "soak_disconnects")

    need(restore.get("attempted") is True, "restore_attempted")
    need(restore.get("connected") is True, "restore_connected")
    need(bool((restore.get("ipv4") or {}).get("ipv4")), "restore_ipv4")

    status = "PASS" if not failures else "FAIL"
    return {
        "schema": "openmitrastar.aelita-2g-wpa2-runtime-evaluation/v1",
        "status": status,
        "failures": sorted(set(failures)),
        "observed": {
            "test_ipv4": ipv4.get("ipv4"),
            "restore_ipv4": (restore.get("ipv4") or {}).get("ipv4"),
            "router_ping": ping.get("pass") is True,
            "controller_http_code": (download or {}).get("http_code"),
            "controller_bytes": int((download or {}).get("bytes", 0)),
            "soak_requested_seconds": requested,
            "soak_samples": samples,
            "soak_connected_samples": connected_samples,
            "soak_disconnects": disconnects,
        },
        "claims": {
            "wpa2_association": test.get("connected") is True,
            "bidirectional_basic_ip": ping.get("pass") is True and bool(ipv4.get("ipv4")),
            "management_http": download is not None and download.get("pass") is True,
            "primary_network_restored": restore.get("connected") is True,
            "flash": False,
            "throughput": "UNVERIFIED",
            "oem_complete": False,
        },
        "thresholds": {
            "duration_seconds_min": duration_min,
            "http_bytes_min": http_bytes_min,
            "disconnects": 0,
            "restore_required": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("result", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--duration-min", type=int, default=600)
    parser.add_argument("--http-bytes-min", type=int, default=1)
    args = parser.parse_args()

    payload = json.loads(args.result.read_text(encoding="utf-8-sig"))
    evaluation = evaluate(payload, duration_min=args.duration_min, http_bytes_min=args.http_bytes_min)
    rendered = json.dumps(evaluation, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if evaluation["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
