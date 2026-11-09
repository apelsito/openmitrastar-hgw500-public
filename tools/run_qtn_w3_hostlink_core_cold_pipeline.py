#!/usr/bin/env python3
"""Fresh cold-cycle -> switch commit -> qdrv hostlink core/cmd19 pipeline."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys

from run_qtn_w3_5g_autopilot import has_exact_marker, run_stage


ROOT = Path(__file__).resolve().parents[1]
ACK = "OPENMITRASTAR_QTN_W3_HOSTLINK_CORE_COLD_PIPELINE_RAM_ONLY"
SWITCH_ACK = "OPENMITRASTAR_QTN_W3_SWITCH_EMAC_HANDOFF_RAM_ONLY"
CORE_ACK = "OPENMITRASTAR_QTN_W3_QDRV_HOSTLINK_CORE_RAM_ONLY"
SWITCH_PASS = "W3_SWITCH_EMAC_HANDOFF_EXPERIMENT_PASS=1"
CORE_PASS = "W3_QDRV_HOSTLINK_CORE_EXPERIMENT_PASS=1"


def preflight() -> bool:
    stages = (
        ([sys.executable, "tools/run_qtn_w3_switch_emac_handoff.py"],
         "W3_SWITCH_EMAC_HANDOFF_DRY_RUN_PASS=1", "switch"),
        ([sys.executable, "tools/run_qtn_w3_qdrv_hostlink_core.py"],
         "W3_QDRV_HOSTLINK_CORE_DRY_RUN_PASS=1", "hostlink-core"),
    )
    for command, marker, label in stages:
        result = subprocess.run(command, cwd=ROOT, text=True, capture_output=True,
                                timeout=240, check=False)
        if result.returncode != 0 or not has_exact_marker(result.stdout, marker):
            print(f"OMHLPIPE preflight={label} state=fail rc={result.returncode}", file=sys.stderr)
            return False
        print(f"OMHLPIPE preflight={label} state=pass", flush=True)
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--cold-wait-seconds", type=int, default=1800)
    args = parser.parse_args()
    if not 60 <= args.cold_wait_seconds <= 1800:
        raise SystemExit("--cold-wait-seconds must be 60..1800")
    if not preflight():
        return 1
    if not args.execute:
        print("W3_HOSTLINK_CORE_COLD_PIPELINE_DRY_RUN_PASS=1 flash=0 vap=0 rf=0")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")

    print("W3_HOSTLINK_CORE_COLD_PIPELINE_START=1 flash=0 vap=0 rf=0", flush=True)
    switch = [
        sys.executable, "tools/run_qtn_w3_switch_emac_handoff.py",
        "--execute", "--ack", SWITCH_ACK,
        "--host", args.host, "--server-ip", args.server_ip, "--port", args.port,
        "--rollback-seconds", "75", "--timeout", str(args.cold_wait_seconds + 300),
        "--wait-for-cold-power-cycle", "--autoboot-wait-seconds", str(args.cold_wait_seconds),
    ]
    if not run_stage(switch, SWITCH_PASS, "hostlink-switch-cold",
                     args.cold_wait_seconds + 900,
                     ready_marker="RAMSSH_CYCLE_START"):
        print("W3_HOSTLINK_CORE_COLD_PIPELINE_FAIL=1 stage=switch", file=sys.stderr)
        return 1

    core = [
        sys.executable, "tools/run_qtn_w3_qdrv_hostlink_core.py",
        "--execute", "--ack", CORE_ACK, "--host", args.host, "--port", args.port,
    ]
    if not run_stage(core, CORE_PASS, "hostlink-core", 600):
        print("W3_HOSTLINK_CORE_COLD_PIPELINE_FAIL=1 stage=core", file=sys.stderr)
        return 1

    print("W3_HOSTLINK_CORE_COLD_PIPELINE_PASS=1 cmd19=complete vap=0 rf=0 flash=0", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
