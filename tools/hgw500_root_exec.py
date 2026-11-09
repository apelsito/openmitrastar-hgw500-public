#!/usr/bin/env python3
"""Execute read/maintenance commands through the HGW-500BNA cmdsh root escape.

The device exposes SSH as user ``1234`` with restricted ``cmdsh``.  The
firmware's cmdsh has a hidden top-level ``sh`` command which prompts for an
internal support password and then launches ``/bin/sh -l`` as uid 0.

This helper does not store the device password.  Use HGW500_PASS or type it
when prompted.
"""
from __future__ import annotations

import argparse
import getpass
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import paramiko  # type: ignore  # noqa: E402


DEFAULT_COMMANDS = [
    "id",
    "uname -a",
    "cat /proc/cpuinfo",
    "cat /proc/cmdline",
    "cat /proc/mtd",
    "cat /proc/mounts",
    "ifconfig -a",
    "route -n",
    "ps",
    "call_qcsapi get_bootcfg_param bootselect 2>&1",
]

HIDDEN_CMD = "sh"


def recv_some(chan: paramiko.Channel, timeout: float = 1.0) -> str:
    deadline = time.time() + timeout
    data = b""
    while time.time() < deadline:
        if chan.recv_ready():
            data += chan.recv(65535)
            time.sleep(0.08)
        else:
            time.sleep(0.05)
    return data.decode("utf-8", "replace")


def send(chan: paramiko.Channel, command: str, timeout: float = 1.0) -> str:
    chan.send(command + "\n")
    return recv_some(chan, timeout)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default=os.environ.get("HGW500_HOST", "192.168.1.97"))
    parser.add_argument("--user", default=os.environ.get("HGW500_USER", "1234"))
    parser.add_argument("--password", default=os.environ.get("HGW500_PASS"))
    parser.add_argument(
        "--support-password",
        default=os.environ.get("HGW500_SUPPORT_PASS"),
        help="Internal support-shell password; defaults to HGW500_SUPPORT_PASS.",
    )
    parser.add_argument("--command-timeout", default=2.0, type=float)
    parser.add_argument(
        "commands",
        nargs="*",
        help="Commands to run after root shell. Defaults to a read-only inventory.",
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass(f"SSH password for {args.user}@{args.host}: ")
    support_password = args.support_password or getpass.getpass(
        "Internal support-shell password: "
    )
    commands = args.commands or DEFAULT_COMMANDS

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        args.host,
        username=args.user,
        password=password,
        timeout=8,
        banner_timeout=8,
        auth_timeout=12,
        look_for_keys=False,
        allow_agent=False,
    )

    try:
        chan = client.invoke_shell(width=220, height=120)
        recv_some(chan, 1.5)
        send(chan, HIDDEN_CMD, 0.8)
        send(chan, support_password, 1.2)
        probe = send(chan, "id", 1.0)
        if "uid=0" not in probe:
            print(probe, end="")
            raise RuntimeError("root shell escape did not return uid=0")
        print(probe, end="")

        for command in commands:
            print(f"\n### {command}")
            print(send(chan, command, args.command_timeout), end="")
    finally:
        client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
