#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    data = json.loads(args.evidence.read_text(encoding="utf-8"))

    required_true = (
        "associated",
        "authorized",
        "dhcp_lease",
        "dns_ok",
        "internet_https_ok",
        "bridge_eth0_wlan0",
        "irq28_progress",
        "hostapd_stable",
        "no_kernel_oops",
    )
    failures = [key for key in required_true if data.get(key) is not True]
    duration = int(data.get("duration_seconds", 0))
    down = float(data.get("download_mbps", 0))
    up = float(data.get("upload_mbps", 0))
    queue_max = int(data.get("be_queue_max", 512))
    disconnects = int(data.get("disconnects", 1))
    errors = int(data.get("netdev_errors_delta", 1))
    ratio = min(down, up) / max(down, up) if down > 0 and up > 0 else 0.0

    if duration < 600:
        failures.append("duration_seconds")
    if down < 5.0:
        failures.append("download_mbps")
    if up < 5.0:
        failures.append("upload_mbps")
    if ratio < 0.5:
        failures.append("directional_ratio")
    if queue_max >= 384:
        failures.append("be_queue_max")
    if disconnects != 0:
        failures.append("disconnects")
    if errors != 0:
        failures.append("netdev_errors_delta")

    result = {
        "schema": "openmitrastar.w2-2g-client-gate/v1",
        "status": "PASS" if not failures else "FAIL",
        "failures": sorted(set(failures)),
        "thresholds": {
            "duration_seconds_min": 600,
            "download_mbps_min": 5.0,
            "upload_mbps_min": 5.0,
            "directional_ratio_min": 0.5,
            "be_queue_max_exclusive": 384,
            "disconnects": 0,
            "netdev_errors_delta": 0,
        },
        "observed": {
            "duration_seconds": duration,
            "download_mbps": down,
            "upload_mbps": up,
            "directional_ratio": round(ratio, 6),
            "be_queue_max": queue_max,
            "disconnects": disconnects,
            "netdev_errors_delta": errors,
        },
        "secrets_recorded": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
