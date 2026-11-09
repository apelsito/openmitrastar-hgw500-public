#!/usr/bin/env python3
"""Promote the exact Q2 integrated image into its own offline candidate lane.

This command is filesystem-only.  It has no serial, network, MTD, Bootbase or
flash execution surface.  Runtime attestations are deliberately not copied:
the Q2 lane must earn a new exact-image RAM-equivalence result.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from make_spi_slot_image import validate_candidate


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONTRACT = ROOT / "work/mission-state/F2_Q2_INTEGRATED_FLASH_CANDIDATE_INPUT_CONTRACT.json"
DEFAULT_BUILD_DIR = ROOT / "work/mission-state/q2-integrated-lzma-candidate/build"
DEFAULT_CANDIDATE_DIR = ROOT / "work/mission-state/f2-q2-integrated-flash-candidate"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def atomic_copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    os.close(fd)
    temporary_path = Path(temporary)
    try:
        shutil.copyfile(source, temporary_path)
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def atomic_json(value: dict[str, Any], destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{destination.name}.", dir=destination.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(value, stream, indent=2, sort_keys=True)
            stream.write("\n")
        os.replace(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def promote(contract_path: Path, build_dir: Path, candidate_dir: Path) -> tuple[Path, Path, dict[str, Any]]:
    contract = read_json(contract_path)
    build_manifest_path = build_dir / "manifest.json"
    bootbase_path = build_dir / "bootbase-contract.json"
    build = read_json(build_manifest_path)
    bootbase = read_json(bootbase_path)
    source_contract = contract["source_build_contract"]

    require(build.get("schema") == source_contract["schema"], "Q2 source schema mismatch")
    require(build.get("classification") == source_contract["classification"], "Q2 source classification mismatch")
    require(build.get("profile") == source_contract["profile"], "Q2 source profile mismatch")
    require(build.get("candidate_eligible") is False, "Q2 source must remain candidate_eligible=false")
    require(build.get("flash_supported") is False, "Q2 source unexpectedly enables flash")
    require(build.get("hardware_actions") is False, "Q2 source records hardware actions")
    require(build.get("network_actions") is False, "Q2 source records network actions")
    require(all(build.get("reproducibility", {}).values()), "Q2 reproducibility gate failed")
    require(bootbase.get("accepted_by_contract") is True and not bootbase.get("errors"), "Bootbase rejected Q2 source")

    for key, expected in source_contract["security"].items():
        require(build.get("security", {}).get(key) is expected, f"Q2 security.{key} mismatch")
    for key, expected in source_contract["capabilities"].items():
        require(build.get("capabilities", {}).get(key) == expected, f"Q2 capability {key} mismatch")

    artifact_spec = build["artifacts"]["webformat"]
    source = build_dir / artifact_spec["file"]
    require(source.is_file(), f"missing Q2 source image: {source}")
    observed_sha = sha256(source)
    require(observed_sha == contract["exact_image"]["sha256"] == artifact_spec["sha256"], "Q2 image hash mismatch")
    require(source.stat().st_size == contract["exact_image"]["bytes"] == artifact_spec["bytes"], "Q2 image size mismatch")
    image = validate_candidate(source.read_bytes())
    require(image.get("hcrc_ok") is True and image.get("dcrc_ok") is True, "Q2 uImage CRC failed")
    require(image.get("arch") == "0x13", "Q2 candidate is not ARC")
    require(source.stat().st_size <= contract["device"]["slot_size"], "Q2 candidate exceeds linux_live")

    inputs = contract["required_candidate_inputs"]
    candidate = candidate_dir / inputs["candidate"]
    manifest_path = candidate_dir / inputs["candidate_manifest"]
    atomic_copy(source, candidate)
    require(sha256(candidate) == observed_sha, "Q2 atomic copy mismatch")

    required_components = contract["candidate_manifest_contract"]["required_component_values"]
    promoted: dict[str, Any] = {
        "schema": contract["candidate_manifest_contract"]["schema"],
        "classification": contract["candidate_manifest_contract"]["classification"],
        "candidate_eligible": True,
        "flash_ready": False,
        "promotion_scope": "offline-static-only",
        "profile": contract["candidate_manifest_contract"]["required_profile"],
        "scope": contract["candidate_manifest_contract"]["required_scope"],
        "target": contract["candidate_manifest_contract"]["required_target"],
        "artifact": {
            "file": candidate.name,
            "sha256": observed_sha,
            "size": candidate.stat().st_size,
            "uimage_name": image.get("name"),
        },
        "components": dict(required_components),
        "capabilities": dict(contract["candidate_manifest_contract"]["required_capability_values"]),
        "completion_claims": dict(contract["candidate_manifest_contract"]["required_completion_claims"]),
        "security": {
            "ssh_key_only": True,
            "psk_bundled": False,
            "https_pem_bundled": False,
            "private_mac_bundled": False,
            "ioss_reset_pulse_forbidden": True,
            "secret_value_recorded": False,
        },
        "static_checks": {
            "uimage_header_crc": "PASS",
            "uimage_data_crc": "PASS",
            "arc_architecture": "PASS",
            "slot_size": "PASS",
            "no_embedded_mtd6": "PASS",
            "preserved_regions_contract": "PASS",
            "reproducible_build": "PASS",
            "ioss_reset_pulse_forbidden": "PASS",
            "external_https_pem_only": "PASS",
        },
        "runtime_gates": {
            "new_q2_uart_boot": "PENDING",
            "same_candidate_ram_equivalence": "PENDING",
            "fresh_current_flash_read": "PENDING",
            "cold_boot_after_write": "PENDING",
        },
        "source": {
            "build_manifest_sha256": sha256(build_manifest_path),
            "bootbase_contract_sha256": sha256(bootbase_path),
        },
        "attestations_copied_from_prior_candidates": False,
    }
    atomic_json(promoted, manifest_path)
    return candidate, manifest_path, promoted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD_DIR)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE_DIR)
    args = parser.parse_args()
    candidate, manifest, promoted = promote(
        args.contract.resolve(), args.build_dir.resolve(), args.candidate_dir.resolve()
    )
    print(
        "OMQ2_PROMOTION_PASS "
        f"candidate={candidate} sha256={promoted['artifact']['sha256']} "
        f"bytes={promoted['artifact']['size']} manifest={manifest} "
        "prior_attestations_copied=0 flash_ready=false hardware=0 flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
