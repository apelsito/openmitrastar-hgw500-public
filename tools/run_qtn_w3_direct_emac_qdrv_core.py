#!/usr/bin/env python3
"""RAM-only direct-EMAC-preserving Quantenna dependency + qdrv core ladder."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
ACK = "OPENMITRASTAR_QTN_W3_DIRECT_EMAC_QDRV_CORE_RAM_ONLY"


def run(command: list[str], timeout: int) -> None:
    subprocess.run(command, cwd=ROOT, check=True, timeout=timeout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--rollback-seconds", type=int, default=120)
    args = parser.parse_args()
    if not args.execute:
        print({
            "mode": "dry-run",
            "host": args.host,
            "switch_emac": "symbols-only",
            "direct_emac": "preserved",
            "qdrv": "core-start",
            "rf": False,
            "vap": False,
            "flash": False,
        })
        print("W3_DIRECT_EMAC_QDRV_CORE_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")

    run([
        sys.executable, "tools/run_qtn_w3_switch_emac_handoff.py",
        "--preserve-direct-emac", "--skip-ioss-reset-pulse",
        "--use-current-no-watchdog-boot", "--execute", "--ack",
        "OPENMITRASTAR_QTN_W3_SWITCH_EMAC_HANDOFF_RAM_ONLY",
        "--host", args.host, "--management-host", args.host,
        "--server-ip", args.server_ip, "--port", args.port,
        "--preserve-2g", "--no-uart-reboot-on-failure",
        "--tqe-ring-entries", "256",
        "--rollback-seconds", str(args.rollback_seconds), "--timeout", "600",
    ], 750)
    run([
        sys.executable, "tools/run_qtn_w3_qdrv_hostlink_core.py",
        "--preserve-direct-emac", "--no-hw-watchdog", "--execute", "--ack",
        "OPENMITRASTAR_QTN_W3_QDRV_HOSTLINK_CORE_RAM_ONLY",
        "--host", args.host, "--port", args.port,
    ], 500)
    print(
        "W3_DIRECT_EMAC_QDRV_CORE_EXPERIMENT_PASS=1 "
        f"management={args.host} direct=eth0 switch_emac=symbols-only "
        "qdrv=loaded rf=blocked vap=absent radio2g=preserved flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
