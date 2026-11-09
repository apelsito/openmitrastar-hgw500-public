#!/usr/bin/env python3
"""Persistent-host-key wrapper for the 2.4 GHz speed/telemetry runner."""
from __future__ import annotations

import argparse
from pathlib import Path
import subprocess as real_subprocess
import sys

import aelita_ssh_policy as ssh_policy
import run_aelita_2g_wpa2_runtime_psk_once as wpa
import run_aelita_2g_wpa2_speed_router_probe as runner


RUNTIME_V2 = Path(__file__).with_name("run_aelita_2g_wpa2_runtime_psk_once_ssh_v2.py")


class _SubprocessProxy:
    def __init__(self, policy_args: argparse.Namespace) -> None:
        self._policy_args = policy_args

    def __getattr__(self, name: str):
        return getattr(real_subprocess, name)

    def run(self, command, *args, **kwargs):
        if (
            isinstance(command, list)
            and len(command) > 1
            and str(command[1]).endswith("run_aelita_2g_wpa2_runtime_psk_once.py")
        ):
            command = list(command)
            command[1] = str(RUNTIME_V2)
            command.extend(policy_cli(self._policy_args))
        return real_subprocess.run(command, *args, **kwargs)


def policy_cli(args: argparse.Namespace) -> list[str]:
    result = [
        "--aelita-host-key-mode", args.aelita_host_key_mode,
        "--aelita-ssh-connect-timeout", str(args.aelita_ssh_connect_timeout),
    ]
    if args.aelita_known_hosts:
        result.extend(("--aelita-known-hosts", str(args.aelita_known_hosts)))
    if args.aelita_host_key_sha256:
        result.extend(("--aelita-host-key-sha256", args.aelita_host_key_sha256))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(add_help=False)
    ssh_policy.add_policy_arguments(parser)
    policy_args, remaining = parser.parse_known_args()
    router_known_hosts = Path(runner.ROUTER_KNOWN_HOSTS)
    if "--router-known-hosts" in remaining:
        index = remaining.index("--router-known-hosts")
        router_known_hosts = Path(remaining[index + 1])
    policy = ssh_policy.install_wpa_policy(
        wpa,
        policy_args,
        router_known_hosts=router_known_hosts,
    )
    runner.ROUTER_KNOWN_HOSTS = router_known_hosts
    runner.oracle_ps = wpa.oracle_ps
    runner.refresh_router_known_hosts = wpa.refresh_router_known_hosts
    runner.subprocess = _SubprocessProxy(policy_args)
    sys.argv = [sys.argv[0], *remaining]
    result = runner.main()
    del policy
    return result


if __name__ == "__main__":
    raise SystemExit(main())
