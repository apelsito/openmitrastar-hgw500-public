#!/usr/bin/env python3
"""Verify product readiness over an already authenticated RAMSSH channel."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
COMMAND = r'''set +e
state=$(cat /run/openmitrastar/boot-state 2>/dev/null || true)
carrier=$(cat /sys/class/net/eth0/carrier 2>/dev/null || true)
printf 'OMPRODUCT_STATE=%s\n' "$state"
printf 'OMPRODUCT_ETH0_CARRIER=%s\n' "$carrier"
case "$state" in ready|degraded) ;; *) exit 20 ;; esac
[ "$carrier" = 1 ] || exit 21
'''


def probe(host: str, timeout: int) -> tuple[bool, str]:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "tools/ramssh_exec.py"),
            COMMAND,
            "--host",
            host,
            "--timeout",
            str(timeout),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout + 10,
    )
    output = (result.stdout + result.stderr).strip()
    return result.returncode == 0, output


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--timeout", type=int, default=45)
    args = parser.parse_args()
    if not 1 <= args.timeout <= 180:
        raise SystemExit("--timeout must be 1..180")

    deadline = time.monotonic() + args.timeout
    last = "product-state-not-yet-readable"
    while time.monotonic() < deadline:
        remaining = max(1, int(deadline - time.monotonic()))
        try:
            ok, output = probe(args.host, min(10, remaining))
        except (subprocess.SubprocessError, OSError) as exc:
            ok, output = False, f"probe-error={type(exc).__name__}"
        if ok:
            print(output)
            state = "degraded" if "OMPRODUCT_STATE=degraded" in output else "ready"
            print(f"OMPRODUCT_READY_SSH_GATE_PASS state={state} carrier=1")
            return 0
        if output:
            last = output
        time.sleep(1)

    print(f"OMPRODUCT_READY_SSH_GATE_FAIL last={last}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
