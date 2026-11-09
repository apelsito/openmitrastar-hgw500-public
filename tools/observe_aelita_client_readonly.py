#!/usr/bin/env python3
"""Bounded client reachability evidence; no SSH trust/network/radio mutations.

This probe deliberately stops at TCP. A live SSH connection requires the exact
existing host pin and an independently reviewed read-only platform command.
Legacy AELITA connect wrappers refresh known_hosts and are not used here.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import time

ROOT = Path(__file__).resolve().parents[1]
SOURCE = "192.168.1.49"
TARGETS = ("apelsito.local", "192.168.1.63")
CANONICAL_KNOWN_HOSTS = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/known_hosts"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def pinned_metadata() -> dict:
    text = CANONICAL_KNOWN_HOSTS.read_text(encoding="ascii")
    result = {}
    for target in TARGETS:
        types = set()
        for line in text.splitlines():
            fields = line.split()
            if len(fields) < 3 or line.startswith("#"):
                continue
            if target in fields[0].split(",") or f"[{target}]:22" in fields[0].split(","):
                types.add(fields[1])
        result[target] = sorted(types)
    return {"source": str(CANONICAL_KNOWN_HOSTS.relative_to(ROOT)),
            "sha256": digest(CANONICAL_KNOWN_HOSTS), "target_key_types": result}


def probe_ip(address: str) -> dict:
    started = time.monotonic()
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.settimeout(3.5)
    try:
        client.bind((SOURCE, 0))
        client.connect((address, 22))
        return {"target": address, "port": 22, "source": SOURCE,
                "connected": True, "elapsed_ms": round((time.monotonic()-started)*1000, 2)}
    except OSError as exc:
        return {"target": address, "port": 22, "source": SOURCE,
                "connected": False, "error_type": type(exc).__name__,
                "error_code": getattr(exc, "winerror", None) or exc.errno,
                "elapsed_ms": round((time.monotonic()-started)*1000, 2)}
    finally:
        client.close()


def main() -> None:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    out = ROOT / "outputs/client-readonly" / ("aelita-reachability-" + timestamp)
    out.mkdir(parents=True, exist_ok=False)
    before = pinned_metadata()
    # A hostname lookup through OS DNS could exceed the wall-clock budget.
    # No unresolved name is promoted to a target or added to a trust store.
    ip_result = probe_ip("192.168.1.63")
    after = pinned_metadata()
    result = {
        "schema": "openmitrastar.aelita-client-readonly/v1",
        "utc": datetime.now(timezone.utc).isoformat(),
        "classification": ("TCP_REACHABLE_IDENTITY_UNVERIFIED" if ip_result["connected"]
                           else "CLIENT_CONTROL_UNAVAILABLE_NO_WIFI_RESULT"),
        "tcp": [ip_result],
        "ssh": "UNRUN", "wifi_visibility": "UNRUN", "client_association": "UNRUN",
        "traffic": "UNRUN", "host_trust_before": before, "host_trust_after": after,
        "host_trust_unchanged": before == after,
        "wrappers_reviewed_not_executed": {
            "tools/connect_aelita_auto.ps1": {
                "sha256": digest(ROOT / "tools/connect_aelita_auto.ps1"),
                "reason": "unconditional Refresh-KnownHosts and StrictHostKeyChecking=accept-new"},
            "tools/status_f65_ops.ps1": {
                "sha256": digest(ROOT / "tools/status_f65_ops.ps1"),
                "reason": "calls unsafe connect wrapper; optional scan may expose MACs"}},
        "next_gate": "fresh reachable independently verified pinned SSH client; then read-only platform/WiFi identity before any association",
        "router_changes": False, "client_changes": False, "network_changes": False,
        "trust_changes": False, "scan": False, "secrets_logged": False, "client_macs_logged": False
    }
    result_path = out / "result.json"
    result_path.write_text(json.dumps(result, indent=2)+"\n", encoding="utf-8")
    print(json.dumps({"result": str(result_path), "sha256": digest(result_path),
                      "classification": result["classification"], "tcp": result["tcp"],
                      "host_trust_unchanged": result["host_trust_unchanged"]}, indent=2))


if __name__ == "__main__":
    main()
