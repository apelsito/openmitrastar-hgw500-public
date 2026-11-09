#!/usr/bin/env python3
"""Provision one private Dropbear Ed25519 host key outside the workspace."""
from __future__ import annotations

import argparse
import csv
import json
import os
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ROOT = Path.home() / ".openmitrastar/devices"
DEFAULT_TOOL = "/home/user/openmitrastar-ssh-lab/dropbear-native/dropbearkey"
DEVICE_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$")


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    if not resolved.drive:
        raise ValueError("device identity path must be on a Windows drive")
    return f"/mnt/{resolved.drive[0].lower()}/{resolved.as_posix()[3:]}"


def current_user_sid() -> str:
    proc = subprocess.run(
        ["whoami.exe", "/user", "/fo", "csv", "/nh"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or "whoami failed")
    row = next(csv.reader([proc.stdout.strip()]))
    if len(row) < 2 or not row[1].startswith("S-1-"):
        raise RuntimeError("could not resolve current Windows SID")
    return row[1]


def restrict_acl(path: Path, directory: bool) -> None:
    sid = current_user_sid()
    grant = f"*{sid}:{'(OI)(CI)' if directory else ''}F"
    system = f"*S-1-5-18:{'(OI)(CI)' if directory else ''}F"
    proc = subprocess.run(
        ["icacls.exe", str(path), "/inheritance:r", "/grant:r", grant, system],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if proc.returncode:
        raise RuntimeError(proc.stderr.strip() or "icacls failed")


def inspect_key_material(distro: str, tool: str, key: Path) -> tuple[str, str]:
    proc = subprocess.run(
        ["wsl.exe", "-d", distro, "-u", "root", "-e", tool, "-y", "-f", wsl_path(key)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if proc.returncode:
        raise RuntimeError("dropbearkey rejected the device host key")
    fingerprint = next((line.split(":", 1)[1].strip() for line in proc.stdout.splitlines() if line.startswith("Fingerprint:")), "")
    public_key = next((line.strip() for line in proc.stdout.splitlines() if line.startswith("ssh-ed25519 ")), "")
    if not fingerprint or not public_key:
        raise RuntimeError("dropbearkey returned incomplete public identity")
    return fingerprint, public_key


def inspect_key(distro: str, tool: str, key: Path) -> str:
    return inspect_key_material(distro, tool, key)[0]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="hgw500bna-qcv2-a2-primary")
    parser.add_argument("--identity-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--dropbearkey", default=DEFAULT_TOOL)
    args = parser.parse_args()
    if not DEVICE_RE.fullmatch(args.device_id):
        raise SystemExit("invalid --device-id")

    identity_root = args.identity_root.resolve()
    try:
        identity_root.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise SystemExit("device private identities must be stored outside the workspace")

    device_dir = identity_root / args.device_id
    key = device_dir / "dropbear_ed25519_host_key"
    metadata = device_dir / "identity.json"
    device_dir.mkdir(parents=True, exist_ok=True)
    restrict_acl(device_dir, directory=True)
    created = False
    if not key.exists():
        proc = subprocess.run(
            ["wsl.exe", "-d", args.distro, "-u", "root", "-e", args.dropbearkey, "-t", "ed25519", "-f", wsl_path(key)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if proc.returncode:
            raise RuntimeError("dropbearkey generation failed")
        created = True
    restrict_acl(key, directory=False)
    fingerprint, public_key = inspect_key_material(args.distro, args.dropbearkey, key)
    public_path = device_dir / "dropbear_ed25519_host_key.pub"
    public_path.write_text(public_key + "\n", encoding="ascii")
    restrict_acl(public_path, directory=False)
    payload = {
        "schema": "openmitrastar.device-ssh-identity/v1",
        "device_id": args.device_id,
        "algorithm": "ed25519",
        "dropbear_format": True,
        "fingerprint": fingerprint,
        "public_key_file": public_path.name,
        "private_key_bytes": key.stat().st_size,
        "created": created,
        "workspace_embedded": False,
    }
    metadata.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    restrict_acl(metadata, directory=False)
    print(json.dumps({"status": "PASS", "created": created, "device_id": args.device_id, "fingerprint": fingerprint, "metadata": str(metadata)}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
