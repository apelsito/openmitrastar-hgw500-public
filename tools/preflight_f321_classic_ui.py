"""File-only F321 review plan. There is no execute mode or hardware operation."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import zlib

import build_f321_classic_ui_candidate as build
from audit_lyoko_full_liberation import verify_recorded_bootbase_rehearsal
from lyoko_web_rootfs_worker import sha256


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-dir", required=True, type=Path)
    parser.add_argument("--candidate-sha256", required=True)
    parser.add_argument("--package-manifest-sha256", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    directory = args.candidate_dir.resolve()
    manifest = json.loads((directory / "manifest.json").read_text(encoding="ascii"))
    if manifest.get("schema") != "openmitrastar.f321-classic-ui-candidate/v1":
        raise ValueError("not a reviewed F321 UI candidate")
    candidate = directory / (build.BASE + ".webformat.bin")
    data = candidate.read_bytes()
    if sha256(candidate) != args.candidate_sha256 or manifest["artifacts"]["webformat"]["sha256"] != args.candidate_sha256:
        raise ValueError("F321 candidate hash mismatch")
    if manifest["frontend"]["manifest_sha256"] != args.package_manifest_sha256:
        raise ValueError("F321 UI package identity mismatch")
    package, _ = build.validate_package(Path(manifest["frontend"]["package"]), args.package_manifest_sha256)
    if package["build_id"] != manifest["frontend"]["build_id"]:
        raise ValueError("F321 UI build identity mismatch")
    source_hash = manifest["source"]["candidate_sha256"]
    base = next((name for name, digest in build.BASE_CANDIDATE_HASHES.items() if digest == source_hash), None)
    if base is None:
        raise ValueError("F321 source is not an accepted pinned image")
    build.validate_base(base)
    source_dir, source_base = build.source_paths(base)
    source_data = (source_dir / (source_base + ".webformat.bin")).read_bytes()
    if data[64:build.ROOTFS_OFFSET] != source_data[64:build.ROOTFS_OFFSET]:
        raise ValueError("F321 changed bytes outside the header and rootfs")
    rootfs = directory / (build.BASE + ".rootfs.squashfs")
    if data[build.ROOTFS_OFFSET:] != rootfs.read_bytes() or sha256(rootfs) != manifest["artifacts"]["rootfs_squashfs"]["sha256"]:
        raise ValueError("F321 rootfs does not match the exact candidate")
    if len(data) > build.STORE_OFFSET or len(data) != manifest["artifacts"]["webformat"]["bytes"]:
        raise ValueError("F321 image overlaps store or has changed size")
    full_slot = data + b"\xff" * (build.SLOT_BYTES - len(data))
    if hashlib.sha256(full_slot).hexdigest() != manifest["artifacts"]["full_slot"]["sha256"]:
        raise ValueError("F321 full-slot digest mismatch")
    recovery_path = Path(manifest["recovery"]["candidate"])
    if sha256(recovery_path) != build.EXPECTED_F314:
        raise ValueError("exact F314 rollback artifact changed")
    recovery = verify_recorded_bootbase_rehearsal(Path(manifest["recovery"]["record"]))
    if recovery.get("verified") is not True:
        raise ValueError("F314 historical Bootbase recovery proof failed validation")
    # This existing tool reads candidate/backup files only; it has no device I/O.
    contract = subprocess.run([sys.executable, str(build.compose.f71.BOOTBASE), "--candidate-slot", str(candidate),
                               "--candidate-name", "linux_live-f321-classic-ui-" + base,
                               "--parts-dir", str(build.compose.f71.PARTS_DIR)],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False, timeout=60)
    if contract.returncode:
        raise ValueError("F321 final-path Bootbase contract failed")
    bootbase = json.loads(contract.stdout)
    if bootbase.get("result") != "PASS":
        raise ValueError("F321 Bootbase did not report PASS")
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "bootbase-contract.json").write_text(json.dumps(bootbase, indent=2) + "\n", encoding="ascii")
    report = {
        "schema": "openmitrastar.f321-classic-ui-preflight/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "PASS_OFFLINE_PLAN_NO_GO_PHYSICAL", "base": base.upper(), "candidate": str(candidate),
        "candidate_sha256": args.candidate_sha256, "candidate_bytes": len(data),
        "full_slot_sha256": hashlib.sha256(full_slot).hexdigest(), "full_slot_crc32": f"{zlib.crc32(full_slot) & 0xffffffff:08x}",
        "ui_build_id": package["build_id"], "ui_manifest_sha256": args.package_manifest_sha256,
        "contracts": {"bootbase": "PASS", "slot_fit": True, "kernel_unchanged": True, "rootfs_identity": True, "store_untouched": True},
        "recovery": {"artifact": str(recovery_path), "sha256": build.EXPECTED_F314, "full_slot_crc32": "d6b13baa", "recorded_proof_revalidated": recovery},
        "physical": {"hardware_actions_performed": False, "executor_implemented": False, "authorization": "NOT_GRANTED_FOR_THIS_HASH",
                     "current_slot_readback": "NOT_RUN", "current_backup": "NOT_RUN", "fresh_uart_binding": "NOT_RUN",
                     "new_candidate_boot": "NOT_RUN", "new_candidate_ui_and_radio_regression": "NOT_RUN"},
        "next_gate": "Implement and review an F321-specific guarded promoter and exact-F314 rollback, then bind authorization to this candidate hash and fresh hardware gates; F319 acknowledgements do not apply",
    }
    (args.output_dir / "plan.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
