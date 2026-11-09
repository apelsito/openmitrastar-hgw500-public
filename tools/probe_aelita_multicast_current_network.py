#!/usr/bin/env python3
"""Probe controller-to-AELITA multicast without changing router or Wi-Fi state."""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import time
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import run_f310_multicast_igmp_physical as wrapper  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--controller-ip", default="192.168.1.43")
    parser.add_argument("--oracle-host", default="192.168.1.63")
    parser.add_argument("--oracle-user", default="AELITA")
    args = parser.parse_args()
    required_ack = "OPENMITRASTAR_AELITA_MULTICAST_BASELINE"
    args.output_dir = args.output_dir.resolve()
    args.output_dir.mkdir(parents=True, exist_ok=False)

    wrapper.configure_base()
    policy_args = wrapper.parser().parse_args([
        "--aelita-host-key-mode", "pinned",
        "--output-dir", str(args.output_dir / "policy-dry-run"),
    ])
    plan = {
        "schema": "openmitrastar.aelita-multicast-current-network-plan/v1",
        "mode": "execute" if args.execute else "dry-run",
        "group": wrapper.base.GROUP,
        "port": 33990,
        "packets": wrapper.base.PACKET_COUNT,
        "payload_bytes": wrapper.base.PACKET_BYTES,
        "router_mutations": False,
        "wifi_mutations": False,
        "flash": False,
        "mtd_writes": False,
    }
    (args.output_dir / "plan.json").write_text(
        json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    if not args.execute:
        print(json.dumps(plan, indent=2, sort_keys=True))
        return 0
    if args.ack != required_ack:
        raise SystemExit("exact --ack is required")

    state = wrapper.base.oracle_wifi_state(args.oracle_host, args.oracle_user)
    if state.get("connected") is not True or not state.get("ipv4"):
        raise SystemExit("AELITA Wi-Fi is not connected")
    wrapper.base.wait_oracle_powershell_ready(args.oracle_host, args.oracle_user)
    token = uuid.uuid4().hex
    with ThreadPoolExecutor(max_workers=1) as executor:
        future = executor.submit(
            wrapper.base.oracle_ps,
            args.oracle_host,
            args.oracle_user,
            wrapper.base.remote_receiver_script(
                wrapper.base.GROUP, 33990, token, str(state["ipv4"]), 20
            ),
            timeout=50,
        )
        time.sleep(wrapper.base.RECEIVER_SETTLE_SECONDS)
        sent = wrapper.base.send_local(
            args.controller_ip,
            wrapper.base.GROUP,
            33990,
            token,
            wrapper.base.PACKET_COUNT,
            wrapper.base.PACKET_BYTES,
        )
        received = wrapper.base.wpa.parse_powershell_json(future.result())

    ratio = received["received_packets"] / sent["sent_packets"]
    result = {
        "schema": "openmitrastar.aelita-multicast-current-network/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if ratio >= 0.90 else "FAIL",
        "ssid": state.get("ssid"),
        "profile_name": state.get("profile_name"),
        "sent_packets": sent["sent_packets"],
        "received_packets": received["received_packets"],
        "delivery_ratio": round(ratio, 4),
        "router_mutations": False,
        "wifi_mutations": False,
        "flash": False,
        "mtd_writes": False,
    }
    (args.output_dir / "result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
