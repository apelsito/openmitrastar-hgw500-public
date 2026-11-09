#!/usr/bin/env python3
"""Compatibility wrapper adding persistent host-key policy to the 2.4 GHz runner."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

import aelita_ssh_policy as ssh_policy
import run_aelita_2g_wpa2_runtime_psk_once as runner


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    ssh_policy.add_policy_arguments(parser)
    policy_args, remaining = parser.parse_known_args()
    router_known_hosts = Path(runner.ROUTER_KNOWN_HOSTS)
    if "--router-known-hosts" in remaining:
        index = remaining.index("--router-known-hosts")
        router_known_hosts = Path(remaining[index + 1])
    ssh_policy.install_wpa_policy(
        runner,
        policy_args,
        router_known_hosts=router_known_hosts,
    )
    sys.argv = [sys.argv[0], *remaining]
    return runner.main()


if __name__ == "__main__":
    raise SystemExit(main())
