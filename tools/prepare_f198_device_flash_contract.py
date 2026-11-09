#!/usr/bin/env python3
"""Prepare a non-executing F198 mtd4 promotion contract."""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DEVICE_ROOT = Path.home() / ".openmitrastar/devices"
F170_FLASH_RESULT = ROOT / "work/mission-state/q3-persistent-composite-f170-lyoko-foundation-runtime-fix/build/flash-one-shot-20260901T111746Z/result.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def openssh_fingerprint(public_line: str) -> str:
    parts = public_line.strip().split()
    if len(parts) < 2 or parts[0] != "ssh-ed25519":
        raise ValueError("invalid Ed25519 public key")
    raw = base64.b64decode(parts[1], validate=True)
    digest = base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
    return f"SHA256:{digest}"


def newest_recovery_proof(root: Path) -> tuple[Path | None, dict]:
    candidates = sorted(root.glob("outputs/recovery/**/result.json"), key=lambda path: path.stat().st_mtime, reverse=True)
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("schema") == "openmitrastar.mtd3-recovery-proof/v1":
            return path, payload
    return None, {}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="hgw500bna-qcv2-a2-primary")
    parser.add_argument("--router-host", default="192.168.1.90")
    parser.add_argument("--device-root", type=Path, default=DEFAULT_DEVICE_ROOT)
    args = parser.parse_args()

    device_dir = args.device_root.resolve() / args.device_id
    firmware_dir = device_dir / "firmware/f198-device-bound"
    identity = json.loads((device_dir / "identity.json").read_text(encoding="utf-8"))
    public_line = (device_dir / identity["public_key_file"]).read_text(encoding="ascii").strip()
    fingerprint = openssh_fingerprint(public_line)
    if fingerprint != identity["fingerprint"]:
        raise SystemExit("public key fingerprint mismatch")
    manifest_path = firmware_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    candidate = firmware_dir / manifest["artifacts"]["webformat"]["file"]
    if sha256(candidate) != manifest["artifacts"]["webformat"]["sha256"]:
        raise SystemExit("F198 candidate hash mismatch")
    if manifest["device_identity"]["fingerprint"] != fingerprint:
        raise SystemExit("F198 manifest fingerprint mismatch")

    f170 = json.loads(F170_FLASH_RESULT.read_text(encoding="utf-8"))
    proof_path, proof = newest_recovery_proof(ROOT)
    recovery_pass = bool(
        proof_path
        and proof.get("status") == "PASS"
        and proof.get("slot") == "mtd3/linux_safety"
        and proof.get("bootenv_written") is False
        and proof.get("power_cycle_returned_to_f170") is True
    )
    known_hosts = firmware_dir / "known_hosts.f198"
    known_hosts.write_text(f"{args.router_host} {public_line}\n", encoding="ascii")
    contract = {
        "schema": "openmitrastar.f198-device-flash-contract/v1",
        "status": "READY_FOR_EXPLICIT_AUTHORIZATION" if recovery_pass else "BLOCKED_RECOVERY_UNPROVEN",
        "flash_authorized": False,
        "device_id": args.device_id,
        "router_host": args.router_host,
        "target": "mtd4/linux_live",
        "candidate": candidate.name,
        "candidate_bytes": candidate.stat().st_size,
        "candidate_sha256": sha256(candidate),
        "expected_current_live_crc32": f170["readback"]["full_slot_crc32"],
        "expected_postflash_fingerprint": fingerprint,
        "known_hosts_file": known_hosts.name,
        "recovery_proof": str(proof_path.relative_to(ROOT)) if proof_path else None,
        "recovery_pass": recovery_pass,
        "protected_partitions": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"],
        "scope": "LAB_PROMOTION_ONLY_NOT_RELEASE",
        "acknowledgement": f"OPENMITRASTAR_Q3_F198_DEVICE_FLASH_{sha256(candidate)[:8].upper()}",
    }
    (firmware_dir / "promotion-contract.json").write_text(json.dumps(contract, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(contract, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
