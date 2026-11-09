"""File-only F322 promotion/restore contract; no device API or execute mode.

Reuses the corrected F321 UART writer, containment and evidence verifier. A
separate exact review is required; sealed firmware manifests remain unchanged.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET

import f321_execution_contract as previous

ROOT, HOST, PNP = previous.ROOT, previous.HOST, previous.PNP
SLOT_BYTES, ERASE_BYTES = previous.SLOT_BYTES, previous.ERASE_BYTES
digest, read_json, image_path = previous.digest, previous.read_json, previous.image_path
MANIFEST_SHA = "e53a3b5e7224a57c26ce0ae8bf149ffe427bc259957402dd093791a6f902d48b"
INVENTORY_SHA = "33da391c780e50edbf1d2668709d67081ee16befb60dc27c217c3d5d3d99c232"
ACCEPTANCE = ROOT / "outputs/postflash/f321-acceptance-20260911T091500Z/result.json"
ACCEPTANCE_SHA = "7795bda97bc87e597677b779715bc0acede2e78ddbdd6fee370a376ce09f8f21"
BACKEND_SOURCE_SHA = "017032af5357afc7798d49d77529ef599a645f1f1b6aa54a94e1740907a8345f"
BACKEND = ROOT / "tools/f322_mtd4_bootbase_flash.ps1"
WRITER = previous.WRITER
F322 = {
    "name": "f322", "directory": str(previous.DEVICE / "f322-f321-shadow-device-bound"),
    "base": "openmitrastar-linux510-f322-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH",
    "sha256": "55145f55f904beb342dd67b39578a79fbc8a4d0bc68bae944402cab80e5f7f1a", "bytes": 5320704,
    "full_slot_crc32": "1f34e4df", "full_slot_sha256": "2249c56824f495517af4945e5e5fff4d6c365198b97b88e51a0769549a40074f",
    "version": "lyoko-foundation-6.9.1-f322-shadow-f321-device", "known_hosts": "known_hosts.f322",
    "ack": "OPENMITRASTAR_F322_MTD4_55145F55_UNARMED",
}
F321 = dict(previous.F321, ack="OPENMITRASTAR_F322_RESTORE_F321_EB8E23AC")
F314 = dict(previous.F314, ack="OPENMITRASTAR_F322_FALLBACK_F314_A0C7350A")
DIRECTIONS = {"promote": (F322, F321), "rollback": (F321, F322), "fallback": (F314, F322)}
EXECUTOR_FILES = tuple(dict.fromkeys((*previous.EXECUTOR_FILES,
    "tools/f322_execution_contract.py", "tools/f322_mtd4_runtime.ps1", "tools/f322_mtd4_bootbase_flash.ps1",
    "tools/promote_f322_mtd4_direct.ps1", "tools/f322_restore_mtd4.ps1", "tools/f322_ui_gate.py",
    "tools/test_f322_executor.py", "tools/verify_f321_authenticated_http.py",
    "tools/run_f322_shadow_acquisition_gate.py", "tools/f322_shadow_gate.py", "tools/test_f322_shadow_gate.py",
)))


def images(direction: str) -> tuple[dict, dict]:
    if direction not in DIRECTIONS:
        raise ValueError("unsupported F322 direction")
    return DIRECTIONS[direction]


def validate_acceptance(path: Path = ACCEPTANCE, expected_sha: str = ACCEPTANCE_SHA) -> dict:
    if digest(path) != expected_sha:
        raise ValueError("F321 acceptance evidence drift")
    proof = read_json(path)
    physical = proof.get("physical_evidence", {})
    gates = proof.get("postboot_gates", {})
    if (proof.get("schema") != "openmitrastar.f321-independent-postboot-acceptance/v1"
            or proof.get("status") != "PASS_F321_INDEPENDENT_POSTBOOT_VALIDATION"
            or proof.get("candidate_sha256") != F321["sha256"] or proof.get("target_host") != HOST
            or proof.get("product_version") != F321["version"]
            or physical.get("candidate_prefix_compared_bytes") != F321["bytes"]
            or physical.get("full_slot_crc32_observed") != F321["full_slot_crc32"]
            or physical.get("full_slot_sha256_observed") is not None
            or physical.get("mtd4_boot_chain") != "PASS"
            or gates.get("platform", {}).get("status") != "PASS"
            or gates.get("installed_ui_and_public_http", {}).get("status") != "PASS_UI_FILE_API_AND_PUBLIC_HTTP"):
        raise ValueError("F321 physical acceptance incomplete")
    evidence = proof.get("evidence", [])
    if not evidence:
        raise ValueError("F321 acceptance lacks underlying evidence")
    private_inputs = {image_path(F321).resolve(), (Path(F321["directory"]) / "manifest.json").resolve()}
    for row in evidence:
        file = Path(row["path"]).resolve()
        if (not file.is_relative_to(ROOT.resolve()) and file not in private_inputs) or file.stat().st_size != row["bytes"] or digest(file) != row["sha256"]:
            raise ValueError("F321 acceptance underlying evidence drift")
    return proof


def validate_sealed_inputs() -> dict:
    previous.validate_sealed_inputs()
    path = Path(F322["directory"]) / "manifest.json"
    if digest(path) != MANIFEST_SHA:
        raise ValueError("sealed F322 manifest drift")
    manifest = read_json(path)
    if manifest.get("schema") != "openmitrastar.f322-shadow-candidate/v1" or manifest.get("source", {}).get("candidate_sha256") != F321["sha256"]:
        raise ValueError("F322 lineage mismatch")
    for flag in ("candidate_eligible", "flash_supported", "release_eligible"):
        if manifest.get(flag) is not False:
            raise ValueError("sealed F322 eligibility changed")
    shadow = manifest.get("shadow", {})
    for flag in ("authoritative_enable", "automatic_arm", "dfs_tx_authorized", "radar_get_status", "radar_start", "shadow_arm_on_boot", "weather_enable"):
        if shadow.get(flag) is not False:
            raise ValueError("F322 must remain unarmed without DFS authority")
    if shadow.get("callbacks") != 0 or manifest.get("safety", {}).get("protected_partitions") != ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"]:
        raise ValueError("F322 shadow/protected partition contract drift")
    previous.validate_image(F322)
    if digest(Path(F322["directory"]) / F322["known_hosts"]) != digest(Path(F321["directory"]) / F321["known_hosts"]):
        raise ValueError("F322 pinned SSH identity differs from F321")
    if digest(Path(F322["directory"]) / "rootfs-inventory.json") != INVENTORY_SHA:
        raise ValueError("F322 rootfs inventory drift")
    if digest(previous.BACKEND) != BACKEND_SOURCE_SHA:
        raise ValueError("corrected F321 backend changed; review a new adapter")
    validate_acceptance()
    return manifest


def environment(image: dict, current: dict) -> dict[str, str]:
    env = previous.environment(image, current)
    env["OM_Q3_FLASH_POWERSHELL_BACKEND"] = str(BACKEND)
    return env


def generic_preflight(image: dict, current: dict) -> dict:
    # The unchanged writer exits before serial/network setup without --execute.
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OM_Q3_FLASH_", "OM_Q3_F45_"))}
    env.update(environment(image, current))
    proc = subprocess.run([sys.executable, str(WRITER), "--transport", "uart-ymodem", "--erase-bytes", "0x5e0000"],
                          cwd=ROOT, env=env, capture_output=True, text=True, timeout=90, check=False)
    if proc.returncode:
        raise ValueError("file-only F322 preflight failed: " + (proc.stderr or proc.stdout)[-1500:])
    report, _ = json.JSONDecoder().raw_decode(proc.stdout)
    if report.get("mode") != "dry-run" or report.get("candidate_sha256") != image["sha256"] or report.get("expected_full_slot_sha256") != image["full_slot_sha256"]:
        raise ValueError("F322 preflight image identity mismatch")
    return report


def file_bindings() -> list[dict]:
    return [{"path": path, "sha256": digest(ROOT / path)} for path in EXECUTOR_FILES]


def qualify_report(path: Path) -> int:
    root = ET.parse(path)
    cases = root.findall(".//testcase")
    required = {"test_f322_dry_run_never_opens_hardware", "test_f322_wrong_ack_stops_before_hardware",
                "test_f322_ambiguous_writer_never_restores", "test_f322_postgate_failure_restores_exact_f321",
                "test_f322_containment_failure_retains_lease", "test_f322_adapter_changes_only_image_pins",
                "test_f322_baseline_failure_prevents_acceptance", "test_f322_no_automatic_acquisition"}
    if len(cases) < 20 or root.findall(".//failure") or root.findall(".//error") or root.findall(".//skipped") or not required.issubset({case.get("name") for case in cases}):
        raise ValueError("F322 qualification missing required all-pass behavior gates")
    return len(cases)


def validate_executor_review(path: Path, expected_sha: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or digest(path) != expected_sha:
        raise ValueError("exact F322 executor-review hash required")
    review = read_json(path)
    if (review.get("schema") != "openmitrastar.f322-executor-review/v1" or review.get("status") != "PASS_OFFLINE_EXECUTOR_REVIEW"
            or review.get("candidate_sha256") != F322["sha256"] or review.get("candidate_manifest_sha256") != MANIFEST_SHA
            or review.get("f321_acceptance_sha256") != ACCEPTANCE_SHA or review.get("files") != file_bindings()
            or review.get("physical_authorization") is not False or review.get("hardware_actions_performed") is not False
            or review.get("acquisition_authorized") is not False or review.get("restore_image_sha256") != F321["sha256"]
            or review.get("fallback_image_sha256") != F314["sha256"]):
        raise ValueError("F322 executor review stale, incomplete or overclaims authority")
    qualification = review["qualification"]
    if digest(Path(qualification["path"])) != qualification["sha256"] or qualify_report(Path(qualification["path"])) != qualification["passed"]:
        raise ValueError("F322 qualification evidence drift")
    return review


def create_review(path: Path, qualification: Path) -> dict:
    validate_sealed_inputs()
    for image, current in DIRECTIONS.values():
        generic_preflight(image, current)
    count = qualify_report(qualification)
    result = {"schema": "openmitrastar.f322-executor-review/v1", "status": "PASS_OFFLINE_EXECUTOR_REVIEW",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "candidate_sha256": F322["sha256"],
        "candidate_manifest_sha256": MANIFEST_SHA, "f321_acceptance_sha256": ACCEPTANCE_SHA,
        "restore_image_sha256": F321["sha256"], "fallback_image_sha256": F314["sha256"],
        "physical_authorization": False, "hardware_actions_performed": False, "acquisition_authorized": False,
        "qualification": {"path": str(qualification.resolve()), "sha256": digest(qualification), "passed": count},
        "files": file_bindings(), "scope": "Exact F322 unarmed installation and F321 restoration only; F314 is a separately invoked contingency",
        "still_required": ["owner authorization for exact action", "fresh pinned SSH/UART binding and exclusive lease",
            "fresh Bootbase current/protected CRC before erase", "writer readback then platform/UI/unarmed baseline",
            "shadow acquisition NO_GO: disarm does not restore the acquisition hardware state"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="ascii") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    return result


def plan(direction: str, review_path: Path | None = None, review_sha: str = "") -> dict:
    validate_sealed_inputs()
    image, current = images(direction)
    preflight = generic_preflight(image, current)
    generic_preflight(F321, F322)
    reviewed = review_path is not None
    if reviewed:
        validate_executor_review(review_path, review_sha)
    return {"schema": "openmitrastar.f322-mtd4-plan/v1", "mode": "dry-run", "direction": direction,
        "target_model": "HGW-500BNA-QCv2 A2", "target_host": HOST, "port": "COM3", "uart_pnp_device_id": PNP,
        "image": image, "current": current, "candidate": str(image_path(image)), "write_target": "mtd4/linux_live",
        "offset": "0x007e0000", "slot_bytes": SLOT_BYTES, "erase_bytes": ERASE_BYTES, "transport": "uart-ymodem",
        "protected_partitions": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"], "store_tail_preserved": True,
        "required_ack": image["ack"], "local_preflight_pass": True, "executor_review_verified": reviewed,
        "physical_authorization": False, "hardware_actions_performed": False, "physical_ready": False,
        "acquisition_authorized": False, "acquisition_status": "NO_GO_ARM_CLEANUP_CONTRACT",
        "status": "OFFLINE_REVIEWED_FRESH_GATES_PENDING" if reviewed else "NO_GO_EXECUTOR_REVIEW_PENDING",
        "f321_acceptance": {"path": str(ACCEPTANCE), "sha256": ACCEPTANCE_SHA},
        "recovery_rehearsal": str(previous.REHEARSAL),
        "physical_lock": str(ROOT / "outputs/locks/f301-physical-radio.lock"),
        "rollback": {"image": F321, "automatic": "only after verified writer PASS then failed postflash gate in the same lease",
            "source_evidence": "F321 physical write/readback/boot plus independent acceptance; not an F322-to-F321 rehearsal",
            "fallback": F314, "fallback_automatic": False,
            "ambiguous_flash": "STOP; no retry, no chained restore; fresh physical evidence required",
            "hard_lockup": "owner power-cycle may be required; no unattended recovery guarantee"},
        "readback_provenance": {"full_slot_sha256": "expected local padded image; hardware SHA-256 not measured",
            "full_slot_crc32": "fresh Bootbase full-slot read", "candidate_prefix": "all candidate bytes cmp.b"},
        "environment": environment(image, current),
        "protected_baseline_sha256": preflight["protected_partition_sha256"],
        "protected_baseline_crc32": preflight["protected_partition_crc32"]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direction", choices=tuple(DIRECTIONS), default="promote")
    parser.add_argument("--executor-review", type=Path)
    parser.add_argument("--executor-review-sha256", default="")
    parser.add_argument("--create-review", type=Path)
    parser.add_argument("--reviewed-executor", action="store_true")
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--verify-writer", type=Path)
    args = parser.parse_args()
    if args.create_review:
        if not args.reviewed_executor or not args.qualification:
            parser.error("review creation requires explicit review and focused test evidence")
        result = create_review(args.create_review, args.qualification)
    elif args.verify_writer:
        result = previous.verify_writer_result(args.verify_writer, *images(args.direction))
    else:
        result = plan(args.direction, args.executor_review, args.executor_review_sha256)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, TypeError, subprocess.SubprocessError) as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc), "hardware_actions_performed": False}), file=sys.stderr)
        raise SystemExit(1)
