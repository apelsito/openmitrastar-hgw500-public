from __future__ import annotations

import argparse
import base64
from hashlib import sha256
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import aelita_ssh_policy as policy  # noqa: E402


def key_line(host: str, payload: bytes = b"fixture-host-key") -> str:
    return f"{host} ssh-ed25519 {base64.b64encode(payload).decode('ascii')}"


def fingerprint(payload: bytes = b"fixture-host-key") -> str:
    return "SHA256:" + base64.b64encode(sha256(payload).digest()).decode("ascii").rstrip("=")


def test_compat_reuses_existing_pin_without_scanning(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(key_line("192.168.1.63") + "\n", encoding="ascii")
    calls = []
    result = policy.ensure_known_host(
        "192.168.1.63",
        known_hosts,
        scanner=lambda host, timeout: calls.append((host, timeout)) or "",
        fallback=lambda host, timeout: None,
    )
    assert result.status == "reused"
    assert calls == []


def test_compat_discovers_once_then_reuses(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    calls = []

    def scanner(host: str, timeout: int) -> str:
        calls.append((host, timeout))
        return key_line(host)

    first = policy.ensure_known_host("192.168.1.63", known_hosts, scanner=scanner)
    second = policy.ensure_known_host("192.168.1.63", known_hosts, scanner=scanner)
    assert first.status == "discovered"
    assert second.status == "reused"
    assert len(calls) == 1


def test_pinned_mode_never_discovers_missing_host(tmp_path: Path) -> None:
    calls = []
    with pytest.raises(policy.HostKeyPolicyError, match="pinned host key is missing"):
        policy.ensure_known_host(
            "192.168.1.63",
            tmp_path / "known_hosts",
            mode="pinned",
            scanner=lambda host, timeout: calls.append((host, timeout)) or key_line(host),
        )
    assert calls == []


def test_fingerprint_match_and_mismatch_are_checked_offline(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(key_line("192.168.1.63") + "\n", encoding="ascii")
    result = policy.ensure_known_host(
        "192.168.1.63",
        known_hosts,
        mode="pinned",
        expected_fingerprint=fingerprint(),
    )
    assert result.fingerprint_enforced is True
    with pytest.raises(policy.HostKeyPolicyError, match="fingerprint mismatch"):
        policy.ensure_known_host(
            "192.168.1.63",
            known_hosts,
            mode="pinned",
            expected_fingerprint=fingerprint(b"other-key"),
        )


def test_refresh_preserves_other_hosts_and_never_logs_key_material(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text(key_line("192.168.1.35", b"other") + "\n", encoding="ascii")
    result = policy.ensure_known_host(
        "192.168.1.63",
        known_hosts,
        mode="refresh",
        scanner=lambda host, timeout: key_line(host),
    )
    text = known_hosts.read_text(encoding="ascii")
    assert "192.168.1.35" in text and "192.168.1.63" in text
    assert "fixture-host-key" not in str(result.public_dict())
    assert set(result.public_dict()) == {
        "host", "mode", "status", "known_hosts_path", "key_types", "fingerprint_enforced"
    }


def test_policy_arguments_keep_compatibility_defaults() -> None:
    parser = argparse.ArgumentParser()
    policy.add_policy_arguments(parser)
    args = parser.parse_args([])
    assert args.aelita_known_hosts is None
    assert args.aelita_host_key_mode == "compat"
    assert args.aelita_host_key_sha256 == ""
    assert args.aelita_ssh_connect_timeout == 8
