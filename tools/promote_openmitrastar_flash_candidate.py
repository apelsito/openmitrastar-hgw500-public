#!/usr/bin/env python3
"""Promote one verified RAM artifact into the offline F2 candidate directory.

This tool performs filesystem-only validation and copying.  It never opens a
serial port, a network socket, an MTD device, or writes router flash.  Hardware
RAM-equivalence and the fresh current-flash read remain separate mandatory
gates in ``openmitrastar_flash_candidate_readiness.py``.
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


DEFAULT_CONTRACT = Path("work/mission-state/F2_FLASH_CANDIDATE_INPUT_CONTRACT.json")
DEFAULT_BUILD = Path("work/mission-state/f3-product-minihttpd-private-nowdt/build")
DEFAULT_BASENAME = "openmitrastar-linux510-product-minihttpd-posix-private-nowdt-v1"


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


def resolve(workspace: Path, path: Path | str) -> Path:
    value = Path(path)
    return value if value.is_absolute() else workspace / value


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


def promote(
    workspace: Path,
    contract_path: Path,
    build_dir: Path,
    basename: str,
    candidate_dir: Path | None = None,
) -> tuple[Path, Path, dict[str, Any]]:
    contract = read_json(contract_path)
    manifest_path = build_dir / "manifest.json"
    bootbase_path = build_dir / "bootbase-contract.json"
    build_manifest = read_json(manifest_path)
    bootbase = read_json(bootbase_path)

    source_contract = contract.get("source_build_contract", {})
    expected_source_classification = source_contract.get(
        "classification", "RAM-EQUIVALENT-PRODUCT-CANDIDATE-NO-FLASH"
    )
    require(build_manifest.get("classification") == expected_source_classification,
            "source build classification does not match the selected profile")
    for key in ("profile", "scope"):
        if key in source_contract:
            require(build_manifest.get(key) == source_contract[key],
                    f"source build {key} does not match the selected profile")
    require(build_manifest.get("candidate_eligible") is False,
            "source build must remain candidate_eligible=false")
    require(build_manifest.get("flash_supported") is False,
            "source build unexpectedly enables flash")
    expected_private = source_contract.get("private_build", True)
    require(build_manifest.get("private_build") is expected_private,
            "source build private_build policy does not match the selected profile")
    security = build_manifest.get("security", {})
    expected_security = source_contract.get(
        "security",
        {
            "ssh_key_only": True,
            "psk_bundled": True,
            "missing_psk_fail_closed": True,
        },
    )
    for key, expected in expected_security.items():
        require(security.get(key) is expected,
                f"source build security.{key} does not match the selected profile")
    expected_capabilities = source_contract.get("capabilities", {})
    source_capabilities = build_manifest.get("capabilities", {})
    for key, expected in expected_capabilities.items():
        require(source_capabilities.get(key) == expected,
                f"source build capabilities.{key} does not match the selected profile")
    require(all(build_manifest.get("reproducibility", {}).values()), "reproducibility gate failed")
    kernel_gates = build_manifest.get("kernel_integration_gates", {})
    require(kernel_gates.get("posix_timers") is True, "POSIX timers missing")
    require(kernel_gates.get("product_watchdog_canary") is False,
            "product watchdog canary must be disabled for this checkpoint")
    require(bootbase.get("accepted_by_contract") is True and not bootbase.get("errors"),
            "Bootbase slot contract rejected source")

    artifact_spec = build_manifest.get("artifacts", {}).get("webformat", {})
    source = build_dir / artifact_spec.get("file", f"{basename}.webformat.bin")
    require(artifact_spec.get("file") == f"{basename}.webformat.bin",
            "basename does not select the manifest-pinned webformat artifact")
    require(source.is_file(), f"missing source webformat: {source}")
    source_sha = sha256(source)
    require(source_sha == artifact_spec.get("sha256"), "source webformat hash differs from build manifest")
    require(source.stat().st_size == artifact_spec.get("bytes"), "source webformat size differs from build manifest")

    image_info = validate_candidate(source.read_bytes())
    require(image_info.get("hcrc_ok") is True, "uImage header CRC failed")
    require(image_info.get("dcrc_ok") is True, "uImage data CRC failed")
    require(image_info.get("arch") == "0x13", "candidate architecture is not ARC (0x13)")
    require(source.stat().st_size <= contract["device"]["slot_size"], "candidate exceeds linux_live slot")

    required_values = contract["candidate_manifest_contract"]["required_component_values"]
    require(source_sha == required_values["kernel_runtime_artifact_sha256"],
            "contract kernel artifact hash is stale")
    require(build_manifest.get("source_rootfs", {}).get("sha256") == required_values["rootfs_sha256"],
            "contract rootfs hash is stale")
    realtek_manifest = resolve(workspace, contract["current_components"]["realtek_bundle"]["manifest"])
    require(realtek_manifest.is_file(), f"missing Realtek manifest: {realtek_manifest}")
    realtek_sha = sha256(realtek_manifest)
    require(realtek_sha == required_values["realtek_bundle_manifest_sha256"],
            "contract Realtek manifest hash is stale")

    inputs = contract["required_candidate_inputs"]
    destination_root = candidate_dir or resolve(workspace, inputs["directory"])
    candidate_path = destination_root / inputs["candidate"]
    promoted_manifest_path = destination_root / inputs["candidate_manifest"]
    atomic_copy(source, candidate_path)
    require(sha256(candidate_path) == source_sha, "atomic candidate copy hash mismatch")

    manifest_contract = contract["candidate_manifest_contract"]
    promoted = {
        "schema": manifest_contract["schema"],
        "classification": manifest_contract["classification"],
        "candidate_eligible": True,
        "flash_ready": False,
        "promotion_scope": "offline-static-only",
        "target": contract["candidate_manifest_contract"]["required_target"],
        "artifact": {
            "file": candidate_path.name,
            "sha256": source_sha,
            "size": candidate_path.stat().st_size,
            "uimage_name": image_info.get("name"),
        },
        "components": {
            "kernel_runtime_artifact_sha256": source_sha,
            "rootfs_sha256": build_manifest["source_rootfs"]["sha256"],
            "realtek_bundle_manifest_sha256": realtek_sha,
        },
        "static_checks": {
            "uimage_header_crc": "PASS",
            "uimage_data_crc": "PASS",
            "arc_architecture": "PASS",
            "slot_size": "PASS",
            "no_embedded_mtd6": "PASS",
            "preserved_regions_contract": "PASS",
            "reproducible_build": "PASS",
            "watchdog_canary_disabled": "PASS",
        },
        "runtime_gates": {
            "same_candidate_ram_equivalence": "PENDING",
            "fresh_current_flash_read": "PENDING",
            "cold_boot_after_write": "PENDING",
        },
        "source": {
            "build_manifest_sha256": sha256(manifest_path),
            "bootbase_contract_sha256": sha256(bootbase_path),
        },
        "security": {
            "ssh_key_only": security.get("ssh_key_only") is True,
            "psk_bundled": security.get("psk_bundled") is True,
            "secret_value_recorded": False,
        },
    }
    if "required_profile" in manifest_contract:
        promoted["profile"] = manifest_contract["required_profile"]
    if "required_scope" in manifest_contract:
        promoted["scope"] = manifest_contract["required_scope"]
    if "required_capability_values" in manifest_contract:
        promoted["capabilities"] = dict(manifest_contract["required_capability_values"])
    if "required_completion_claims" in manifest_contract:
        promoted["completion_claims"] = dict(manifest_contract["required_completion_claims"])
    atomic_json(promoted, promoted_manifest_path)
    return candidate_path, promoted_manifest_path, promoted


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--build-dir", type=Path, default=DEFAULT_BUILD)
    parser.add_argument("--basename", default=DEFAULT_BASENAME)
    parser.add_argument("--candidate-dir", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    contract = resolve(workspace, args.contract)
    build_dir = resolve(workspace, args.build_dir)
    candidate_dir = resolve(workspace, args.candidate_dir) if args.candidate_dir else None
    candidate, manifest, promoted = promote(workspace, contract, build_dir, args.basename, candidate_dir)
    print(
        "OMF2_PROMOTION_PASS "
        f"candidate={candidate} sha256={promoted['artifact']['sha256']} "
        f"bytes={promoted['artifact']['size']} manifest={manifest} "
        "flash_ready=false"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
