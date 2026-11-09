#!/usr/bin/env python3
"""Shared SSH host-key policy for AELITA Wi-Fi runners.

The default ``compat`` mode reuses an existing host entry and discovers it only
when missing. ``pinned`` never performs network discovery. ``refresh`` is an
explicit key-rotation operation. Returned metadata never contains public-key
material or private credential paths.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import asdict, dataclass
import hashlib
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from typing import Callable


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/pydeps"))

import paramiko  # noqa: E402


VALID_MODES = ("compat", "pinned", "refresh")
VALID_KEY_TYPES = {
    "ssh-ed25519",
    "ssh-rsa",
    "ecdsa-sha2-nistp256",
    "ecdsa-sha2-nistp384",
    "ecdsa-sha2-nistp521",
}
_LOCK = threading.RLock()


class HostKeyPolicyError(RuntimeError):
    pass


@dataclass(frozen=True)
class HostKeyResult:
    host: str
    mode: str
    status: str
    known_hosts_path: str
    key_types: tuple[str, ...]
    fingerprint_enforced: bool

    def public_dict(self) -> dict[str, object]:
        return asdict(self)


def normalize_fingerprint(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    if not normalized.startswith("SHA256:"):
        normalized = "SHA256:" + normalized
    payload = normalized.removeprefix("SHA256:")
    if not re.fullmatch(r"[A-Za-z0-9+/]{43}=?", payload):
        raise HostKeyPolicyError("host-key fingerprint must be an OpenSSH SHA256 fingerprint")
    return "SHA256:" + payload.rstrip("=")


def fingerprint_for_line(line: str) -> str:
    fields = line.split()
    if len(fields) < 3 or fields[1] not in VALID_KEY_TYPES:
        raise HostKeyPolicyError("invalid known_hosts entry")
    try:
        key_blob = base64.b64decode(fields[2], validate=True)
    except Exception as exc:
        raise HostKeyPolicyError("invalid known_hosts key encoding") from exc
    digest = base64.b64encode(hashlib.sha256(key_blob).digest()).decode("ascii").rstrip("=")
    return "SHA256:" + digest


def _host_matches(field: str, host: str) -> bool:
    if field.startswith("|"):
        return False
    candidates = {host, f"[{host}]:22"}
    return any(item in candidates for item in field.split(","))


def matching_lines(text: str, host: str) -> list[str]:
    result: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        fields = line.split()
        if len(fields) >= 3 and fields[1] in VALID_KEY_TYPES and _host_matches(fields[0], host):
            result.append(line)
    return result


def parse_keyscan_lines(text: str, host: str) -> list[str]:
    result: list[str] = []
    for line in matching_lines(text, host):
        fingerprint_for_line(line)
        if line not in result:
            result.append(line)
    return result


def _ssh_keyscan_command() -> str:
    windir = os.environ.get("WINDIR")
    if windir:
        candidate = Path(windir) / "System32/OpenSSH/ssh-keyscan.exe"
        if candidate.is_file():
            return str(candidate)
    return "ssh-keyscan"


def scan_host_key(host: str, timeout: int = 5) -> str:
    proc = subprocess.run(
        [_ssh_keyscan_command(), "-T", str(timeout), "-t", "ed25519,ecdsa,rsa", host],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        timeout=timeout + 2,
        check=False,
    )
    return proc.stdout or ""


def paramiko_scan_line(host: str, timeout: int = 5) -> str | None:
    sock = None
    transport = None
    try:
        sock = socket.create_connection((host, 22), timeout=timeout)
        transport = paramiko.Transport(sock)
        transport.start_client(timeout=timeout)
        key = transport.get_remote_server_key()
        if key is None:
            return None
        return f"{host} {key.get_name()} {key.get_base64()}"
    except Exception:
        return None
    finally:
        if transport is not None:
            transport.close()
        elif sock is not None:
            sock.close()


def _verify_fingerprint(lines: list[str], expected: str) -> None:
    wanted = normalize_fingerprint(expected)
    if not wanted:
        return
    actual = {fingerprint_for_line(line) for line in lines}
    if wanted not in actual:
        raise HostKeyPolicyError("host-key fingerprint mismatch")


def _atomic_replace_host(path: Path, host: str, replacement: list[str]) -> None:
    existing = path.read_text(encoding="ascii") if path.is_file() else ""
    kept: list[str] = []
    for raw in existing.splitlines():
        fields = raw.strip().split()
        if fields and _host_matches(fields[0], host):
            continue
        kept.append(raw)
    payload = "\n".join([*kept, *replacement]).rstrip("\n") + "\n"
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f".tmp-{os.getpid()}-{threading.get_ident()}")
    try:
        temporary.write_text(payload, encoding="ascii", newline="\n")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def ensure_known_host(
    host: str,
    known_hosts: Path,
    *,
    mode: str = "compat",
    expected_fingerprint: str = "",
    scan_timeout: int = 5,
    scanner: Callable[[str, int], str] = scan_host_key,
    fallback: Callable[[str, int], str | None] = paramiko_scan_line,
) -> HostKeyResult:
    if mode not in VALID_MODES:
        raise HostKeyPolicyError(f"unsupported host-key mode: {mode}")
    if str(known_hosts).upper() == "NUL":
        raise HostKeyPolicyError("known_hosts cannot be NUL")
    if not 1 <= scan_timeout <= 30:
        raise HostKeyPolicyError("scan timeout must be 1..30 seconds")

    with _LOCK:
        text = known_hosts.read_text(encoding="ascii") if known_hosts.is_file() else ""
        current = matching_lines(text, host)
        if current and mode != "refresh":
            _verify_fingerprint(current, expected_fingerprint)
            return HostKeyResult(
                host=host,
                mode=mode,
                status="reused",
                known_hosts_path=str(known_hosts),
                key_types=tuple(sorted({line.split()[1] for line in current})),
                fingerprint_enforced=bool(expected_fingerprint),
            )
        if mode == "pinned":
            raise HostKeyPolicyError("pinned host key is missing")

        try:
            scanned = scanner(host, scan_timeout)
        except (OSError, subprocess.SubprocessError):
            scanned = ""
        discovered = parse_keyscan_lines(scanned, host)
        if not discovered:
            fallback_line = fallback(host, scan_timeout)
            if fallback_line:
                discovered = parse_keyscan_lines(fallback_line, host)
        if not discovered:
            raise HostKeyPolicyError("host-key discovery failed")
        _verify_fingerprint(discovered, expected_fingerprint)
        _atomic_replace_host(known_hosts, host, discovered)
        return HostKeyResult(
            host=host,
            mode=mode,
            status="refreshed" if current else "discovered",
            known_hosts_path=str(known_hosts),
            key_types=tuple(sorted({line.split()[1] for line in discovered})),
            fingerprint_enforced=bool(expected_fingerprint),
        )


def connect_paramiko(
    *,
    host: str,
    user: str,
    key_path: Path,
    known_hosts: Path,
    mode: str = "compat",
    expected_fingerprint: str = "",
    connect_timeout: int = 8,
    attempts: int = 2,
) -> paramiko.SSHClient:
    ensure_known_host(
        host,
        known_hosts,
        mode=mode,
        expected_fingerprint=expected_fingerprint,
    )
    last_error: Exception | None = None
    for attempt in range(1, attempts + 1):
        client = paramiko.SSHClient()
        client.load_host_keys(str(known_hosts))
        client.set_missing_host_key_policy(paramiko.RejectPolicy())
        try:
            key = paramiko.RSAKey.from_private_key_file(str(key_path))
            client.connect(
                host,
                username=user,
                pkey=key,
                look_for_keys=False,
                allow_agent=False,
                timeout=connect_timeout,
                banner_timeout=connect_timeout + 2,
                auth_timeout=connect_timeout + 2,
            )
            transport = client.get_transport()
            if transport is not None:
                transport.set_keepalive(15)
            return client
        except (OSError, EOFError, paramiko.SSHException) as exc:
            client.close()
            last_error = exc
            if attempt < attempts:
                time.sleep(1)
    assert last_error is not None
    raise last_error


def add_policy_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--aelita-known-hosts", type=Path)
    parser.add_argument("--aelita-host-key-mode", choices=VALID_MODES, default="compat")
    parser.add_argument("--aelita-host-key-sha256", default="")
    parser.add_argument("--aelita-ssh-connect-timeout", type=int, default=8)


def install_wpa_policy(
    wpa: object,
    args: argparse.Namespace,
    *,
    router_known_hosts: Path | None = None,
    router_mode: str = "compat",
    router_fingerprint: str = "",
) -> dict[str, object]:
    known_hosts = args.aelita_known_hosts or Path(getattr(wpa, "KNOWN_HOSTS"))
    mode = args.aelita_host_key_mode
    fingerprint = args.aelita_host_key_sha256
    timeout = args.aelita_ssh_connect_timeout
    if not 2 <= timeout <= 30:
        raise HostKeyPolicyError("AELITA SSH connect timeout must be 2..30 seconds")
    setattr(wpa, "KNOWN_HOSTS", known_hosts)
    if router_known_hosts is not None:
        setattr(wpa, "ROUTER_KNOWN_HOSTS", router_known_hosts)

    def ensure_oracle(host: str) -> None:
        ensure_known_host(host, known_hosts, mode=mode, expected_fingerprint=fingerprint)

    def oracle_connect(host: str, user: str):
        getattr(wpa, "validate_oracle_target")(host, user)
        key_path = Path(getattr(wpa, "ORACLE_KEY"))
        if not key_path.is_file():
            raise SystemExit("missing configured AELITA SSH key")
        return connect_paramiko(
            host=host,
            user=user,
            key_path=key_path,
            known_hosts=known_hosts,
            mode=mode,
            expected_fingerprint=fingerprint,
            connect_timeout=timeout,
        )

    def ensure_router(host: str) -> None:
        target = Path(getattr(wpa, "ROUTER_KNOWN_HOSTS"))
        ensure_known_host(
            host,
            target,
            mode=router_mode,
            expected_fingerprint=router_fingerprint,
        )

    setattr(wpa, "refresh_oracle_known_hosts", ensure_oracle)
    setattr(wpa, "refresh_router_known_hosts", ensure_router)
    setattr(wpa, "oracle_connect", oracle_connect)
    return {
        "mode": mode,
        "known_hosts_path": str(known_hosts),
        "fingerprint_enforced": bool(fingerprint),
        "connect_timeout_seconds": timeout,
        "router_known_hosts_path": str(getattr(wpa, "ROUTER_KNOWN_HOSTS")),
    }
