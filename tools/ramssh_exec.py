#!/usr/bin/env python3
"""Run an authenticated command on an OpenMitraStar target.

The historical RAM boot path uses the WSL-held Ed25519 key through Paramiko.
Persistent Linux 5.10 uses the Windows OpenSSH key and the project known_hosts
wrapper.  Keep Paramiko first for RAM workflows, then fall back to the wrapper
so read-only product probes do not fail on stale RAM-only credentials.
"""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
import paramiko  # noqa: E402


def load_private_key() -> paramiko.Ed25519Key:
    key = subprocess.check_output(
        [
            "wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e",
            "cat", "/home/user/openmitrastar-ramssh-keys/client_ed25519",
        ],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return paramiko.Ed25519Key.from_private_key(io.StringIO(key))


def run_paramiko(args: argparse.Namespace) -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            args.host,
            port=args.port,
            username=args.user,
            pkey=load_private_key(),
            look_for_keys=False,
            allow_agent=False,
            timeout=5,
            banner_timeout=8,
            auth_timeout=8,
        )
        _, stdout, stderr = client.exec_command(args.command, timeout=args.timeout)
        out = stdout.read()
        err = stderr.read()
        if out:
            sys.stdout.buffer.write(out)
        if err:
            sys.stderr.buffer.write(err)
        return stdout.channel.recv_exit_status()
    finally:
        client.close()


def run_openssh_wrapper(args: argparse.Namespace) -> int:
    wrapper = ROOT / "tools" / "ssh_openmitrastar_510.ps1"
    if not wrapper.is_file():
        raise FileNotFoundError(wrapper)
    proc = subprocess.run(
        [
            "pwsh.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(wrapper),
            "-HostAddress",
            args.host,
            "-User",
            args.user,
            "-RemoteCommand",
            args.command,
        ],
        cwd=ROOT,
        text=False,
        capture_output=True,
        timeout=args.timeout + 20,
        check=False,
    )
    if proc.stdout:
        sys.stdout.buffer.write(proc.stdout)
    if proc.stderr:
        sys.stderr.buffer.write(proc.stderr)
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("command")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--user", default="root")
    parser.add_argument("--port", type=int, default=22)
    parser.add_argument("--timeout", type=int, default=20)
    parser.add_argument(
        "--auth",
        choices=("auto", "ramssh", "openssh-wrapper"),
        default="auto",
        help="SSH credential path. auto tries RAM Paramiko first, then the 5.10 OpenSSH wrapper.",
    )
    args = parser.parse_args()

    if args.auth == "openssh-wrapper":
        return run_openssh_wrapper(args)
    if args.auth == "ramssh":
        return run_paramiko(args)
    try:
        return run_paramiko(args)
    except Exception as exc:
        print(
            f"OMRAMSSH_PARAMIKO_FALLBACK reason={type(exc).__name__}",
            file=sys.stderr,
        )
        return run_openssh_wrapper(args)


if __name__ == "__main__":
    raise SystemExit(main())
