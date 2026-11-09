#!/usr/bin/env python3
"""Shared offline contract for the F310 post-promotion physical gates."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
from typing import Any

import aelita_ssh_policy as ssh_policy
import openmitrastar_f301_hardware_lock as hardware_lock


ROOT = Path(__file__).resolve().parents[1]
DEVICE = "hgw500bna-qcv2-a2-primary"
BUILD = Path.home() / f".openmitrastar/devices/{DEVICE}/firmware/f310-device-bound"
MANIFEST = BUILD / "manifest.json"
KNOWN_HOSTS = BUILD / "known_hosts.f310"
AELITA_KNOWN_HOSTS = ROOT / "outputs/kernel-port/realtek-loop/wifi-oracle-control/known_hosts"
EXPECTED_VERSION = "lyoko-foundation-6.7.5-f310-canonical-frontend-identity-device"
EXPECTED_SHA256 = "df451d720d8a959ff79ae6a2377940f6f9c3253f22d00f4b15752827e55ba330"
LOCK_DIR = hardware_lock.LOCK_DIR


def read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="ascii"))
    if not isinstance(payload, dict):
        raise RuntimeError(f"expected JSON object: {path}")
    return payload


def add_ssh_v2_arguments(parser: argparse.ArgumentParser) -> None:
    ssh_policy.add_policy_arguments(parser)


def install_ssh_v2(wpa: object, args: argparse.Namespace) -> dict[str, object]:
    if args.aelita_known_hosts is None:
        args.aelita_known_hosts = AELITA_KNOWN_HOSTS
    args.aelita_known_hosts = args.aelita_known_hosts.resolve()
    return ssh_policy.install_wpa_policy(
        wpa,
        args,
        router_known_hosts=KNOWN_HOSTS,
        router_mode="pinned",
    )


def active_soak_evidence(state_root: Path | None = None) -> dict[str, Any]:
    """Fail-closed inventory of F301/F306/F310 physical workflows."""
    root = (state_root or (ROOT / "outputs")).resolve()
    command = r'''
$patterns = @(
  'run_f301_sequential_dual_radio_soak(?:_ssh_v2)?[.]py',
  'f306_soak_runner[.]py',
  'f310_soak_runner[.]py'
)
$items = Get-CimInstance Win32_Process -ErrorAction Stop |
  Where-Object {
    $_.ProcessId -ne $PID -and $_.CommandLine -and
    ($patterns | Where-Object { $_.CommandLine -match $_ } | Select-Object -First 1)
  } |
  Select-Object ProcessId, Name
@($items | ForEach-Object {
  [ordered]@{pid=[int]$_.ProcessId;name=[string]$_.Name;kind='soak'}
}) | ConvertTo-Json -Compress
'''
    processes: list[dict[str, Any]] = []
    errors: list[str] = []
    try:
        proc = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", command],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,
            check=False,
        )
        if proc.returncode:
            raise RuntimeError(proc.stderr.strip()[:300] or f"rc={proc.returncode}")
        decoded = json.loads(proc.stdout.strip() or "[]")
        if isinstance(decoded, dict):
            decoded = [decoded]
        if not isinstance(decoded, list):
            raise RuntimeError("unexpected process inventory")
        processes = [item for item in decoded if isinstance(item, dict)]
    except Exception as exc:
        errors.append(f"process_inventory: {type(exc).__name__}: {str(exc)[:240]}")

    checkpoints: list[dict[str, Any]] = []
    soak_root = root / "soak"
    if soak_root.is_dir():
        for path in sorted(soak_root.rglob("checkpoint.json")):
            try:
                payload = read_json(path)
            except Exception as exc:
                errors.append(f"checkpoint:{path}: {type(exc).__name__}")
                continue
            schema = str(payload.get("schema") or "")
            if payload.get("status") == "IN_PROGRESS" and schema.startswith(
                ("openmitrastar.f301-", "openmitrastar.f306-", "openmitrastar.f310-")
            ):
                checkpoints.append(
                    {
                        "path": str(path),
                        "schema": schema,
                        "updated_at": payload.get("updated_at"),
                        "cycles_completed": payload.get("cycles_completed"),
                    }
                )

    return {
        "active": bool(processes or checkpoints),
        "processes": processes,
        "in_progress_checkpoints": checkpoints,
        "detection_error": " | ".join(errors),
        "shared_lock_present": LOCK_DIR.exists(),
        "fail_closed": True,
    }


def soak_guard_clear(evidence: dict[str, Any], *, ignore_lock: bool = False) -> bool:
    return bool(
        evidence.get("active") is False
        and not evidence.get("detection_error")
        and (ignore_lock or evidence.get("shared_lock_present") is False)
    )
