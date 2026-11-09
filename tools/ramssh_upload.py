#!/usr/bin/env python3
"""Upload one file over an authenticated Dropbear exec channel using cat."""
from __future__ import annotations

import argparse
import io
from pathlib import Path
import shlex
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


def run_paramiko(args: argparse.Namespace, payload: bytes) -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    destination = shlex.quote(args.destination)
    mode = shlex.quote(args.mode)
    try:
        client.connect(
            args.host,
            username="root",
            pkey=load_private_key(),
            look_for_keys=False,
            allow_agent=False,
            timeout=5,
            banner_timeout=8,
            auth_timeout=8,
        )
        stdin, stdout, stderr = client.exec_command(
            f"cat > {destination} && chmod {mode} {destination}", timeout=30
        )
        stdin.channel.sendall(payload)
        stdin.channel.shutdown_write()
        out = stdout.read()
        err = stderr.read()
        status = stdout.channel.recv_exit_status()
        if out:
            sys.stdout.buffer.write(out)
        if err:
            sys.stderr.buffer.write(err)
        if status == 0:
            print(f"RAMSSH_UPLOAD_OK bytes={len(payload)} destination={args.destination}")
        return status
    finally:
        client.close()


def run_openssh_stream(args: argparse.Namespace, payload: bytes) -> int:
    ssh = Path(__import__("os").environ["WINDIR"]) / "System32" / "OpenSSH" / "ssh.exe"
    known_hosts = ROOT / "outputs" / "recovery" / "ssh-management" / "openmitrastar_510_known_hosts"
    known_hosts.parent.mkdir(parents=True, exist_ok=True)
    destination = shlex.quote(args.destination)
    mode = shlex.quote(args.mode)
    remote = f"cat > {destination} && chmod {mode} {destination}"
    proc = subprocess.run(
        [
            str(ssh),
            "-i", str(Path.home() / ".ssh" / "id_ed25519"),
            "-o", "IdentitiesOnly=yes",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"UserKnownHostsFile={known_hosts}",
            "-o", "HostKeyAlgorithms=+ssh-rsa",
            "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
            "-o", "LogLevel=ERROR",
            f"root@{args.host}",
            remote,
        ],
        cwd=ROOT,
        input=payload,
        capture_output=True,
        timeout=args.timeout,
        check=False,
    )
    if proc.stdout:
        sys.stdout.buffer.write(proc.stdout)
    if proc.stderr:
        sys.stderr.buffer.write(proc.stderr)
    if proc.returncode == 0:
        print(f"RAMSSH_UPLOAD_OK bytes={len(payload)} destination={args.destination}")
    return proc.returncode


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination")
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--mode", default="0700")
    parser.add_argument("--timeout", type=int, default=60)
    parser.add_argument(
        "--auth",
        choices=("auto", "ramssh", "openssh-wrapper"),
        default="auto",
        help="SSH credential path. auto tries RAM Paramiko first, then the 5.10 OpenSSH key.",
    )
    args = parser.parse_args()
    payload = args.source.read_bytes()

    if args.auth == "openssh-wrapper":
        return run_openssh_stream(args, payload)
    if args.auth == "ramssh":
        return run_paramiko(args, payload)
    try:
        return run_paramiko(args, payload)
    except Exception as exc:
        print(
            f"OMRAMSSH_UPLOAD_PARAMIKO_FALLBACK reason={type(exc).__name__}",
            file=sys.stderr,
        )
        return run_openssh_stream(args, payload)


if __name__ == "__main__":
    raise SystemExit(main())
