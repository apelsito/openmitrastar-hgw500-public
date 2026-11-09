"""Offline F321 executor review, artifact pins and fail-closed writer evidence.

This module has no device/network API. The only subprocess it launches is the
existing writer WITHOUT --execute for its local backup/Bootbase validation.
The executor-review manifest resolves one recorded blocker; it is neither a
cryptographic signature nor a grant of physical authorization.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import xml.etree.ElementTree as ET
import zlib

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
HOST = "192.168.1.90"
PNP = r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000"
MANIFEST_SHA = "2b8b2f2b2e2b845c1fe660b7f89feb34da113b60ad43c6c42f312f3621dc87ff"
PACKAGE_SHA = "4c2a8b9536e28a55fc051a66f7a98df85b0417b90a3274d9f9d3c0c040a8626e"
PACKAGE = ROOT / "outputs/frontend/lyoko-classic-tsx-72dd5d1877544af9"
REHEARSAL = ROOT / "outputs/recovery/f319-f314-rehearsal-detached-20260907T111355Z/run/result.json"
SLOT_BYTES, ERASE_BYTES, ROOTFS_OFFSET = 0x7A0000, 0x5E0000, 0x180000
WRITER = ROOT / "tools/f321_mtd4_one_shot.py"
BACKEND = ROOT / "tools/f321_mtd4_bootbase_flash.ps1"
F321 = {
    "name": "f321", "directory": str(DEVICE / "f321-f314-device-bound"),
    "base": "openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH",
    "sha256": "eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18", "bytes": 5337088,
    "full_slot_crc32": "6ed8e483", "full_slot_sha256": "076afb4ba70b511947d1bd6f78eb5b3b62378889a4e20930a7b5c8022589cbc8",
    "version": "lyoko-foundation-6.8.5-f321-classic-ui-f314-device", "known_hosts": "known_hosts.f321",
    "ack": "OPENMITRASTAR_F321_MTD4_EB8E23AC",
}
F314 = {
    "name": "f314", "directory": str(DEVICE / "f314-device-bound"),
    "base": "openmitrastar-linux510-f314-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH",
    "sha256": "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11", "bytes": 5292032,
    "full_slot_crc32": "d6b13baa", "full_slot_sha256": "bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989",
    "version": "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device", "known_hosts": "known_hosts.f314",
    "ack": "OPENMITRASTAR_F321_ROLLBACK_TO_F314_A0C7350A",
}
EXECUTOR_FILES = (
    "tools/promote_f321_mtd4_direct.ps1", "tools/rollback_f321_to_f314_mtd4.ps1", "tools/f321_mtd4_runtime.ps1",
    "tools/f321_execution_contract.py", "tools/post_flash_f321_ui_gate.py", "tools/test_f321_executor.py", "tools/f321_mtd4_bootbase_flash.ps1",
    "tools/f321_process_job.cs", "tools/f321_native_job_launcher.ps1",
    "tools/f321_ssh_guard.ps1", "tools/f321_mtd4_one_shot.py", "tools/f321_uart_ymodem_load.py",
    "tools/f319_uart_guard.ps1", "tools/f319_recovery_guard.ps1", "tools/f319_flash_fallback.py",
    "tools/reboot_to_topaz_prompt_sysrq.ps1", "tools/uart_ymodem_load.py", "tools/post_flash_f214_device_gate.py",
    "tools/run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py",
    "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1",
)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def image_path(image: dict) -> Path:
    return Path(image["directory"]) / (image["base"] + ".webformat.bin")


def read_json(path: Path) -> dict:
    value = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(value, dict):
        raise ValueError("object required: " + str(path))
    return value


def environment(image: dict, current: dict) -> dict[str, str]:
    directory = Path(image["directory"])
    sidecar = lambda suffix: str(directory / (image["base"] + suffix))
    return {
        "OM_Q3_FLASH_ACK": image["ack"], "OM_Q3_FLASH_BUILD_DIR": str(directory),
        "OM_Q3_FLASH_CANDIDATE": str(image_path(image)), "OM_Q3_FLASH_BOOTBASE_CONTRACT": str(directory / "bootbase-contract.json"),
        "OM_Q3_FLASH_MANIFEST": str(directory / "manifest.json"), "OM_Q3_FLASH_INITRAMFS": sidecar(".kernel.raw.bin"),
        "OM_Q3_FLASH_KCONFIG": sidecar(".config"), "OM_Q3_FLASH_LAYOUT_MODE": "squashfs-split",
        "OM_Q3_FLASH_ROOTFS_IMAGE": sidecar(".rootfs.squashfs"), "OM_Q3_FLASH_DTB": sidecar(".dtb"),
        "OM_Q3_FLASH_ROOTFS_OFFSET": "0x180000", "OM_Q3_FLASH_EXPECTED_SHA256": image["sha256"],
        "OM_Q3_FLASH_EXPECTED_BYTES": str(image["bytes"]), "OM_Q3_FLASH_POWERSHELL_BACKEND": str(BACKEND),
        "OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32": current["full_slot_crc32"],
        "OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256": current["full_slot_sha256"],
        # The old backup proves protected partitions; current mtd4 is reread
        # by Bootbase. Never pretend that old linux_live backup is current.
        "OM_Q3_F45_REQUIRE_BACKUP_LIVE_SLOT_MATCH": "0",
    }


def validate_image(image: dict) -> None:
    data = image_path(image).read_bytes()
    if len(data) != image["bytes"] or hashlib.sha256(data).hexdigest() != image["sha256"]:
        raise ValueError(image["name"] + " exact image mismatch")
    if len(data) > ERASE_BYTES:
        raise ValueError("candidate overlaps the preserved store")
    padded = data + b"\xff" * (SLOT_BYTES - len(data))
    if hashlib.sha256(padded).hexdigest() != image["full_slot_sha256"] or f"{zlib.crc32(padded) & 0xffffffff:08x}" != image["full_slot_crc32"]:
        raise ValueError("local full-slot hash/CRC mismatch")
    manifest = read_json(Path(image["directory"]) / "manifest.json")
    if manifest["artifacts"]["webformat"]["sha256"] != image["sha256"] or manifest["artifacts"]["full_slot"]["sha256"] != image["full_slot_sha256"]:
        raise ValueError("manifest image identity mismatch")
    if not (Path(image["directory"]) / image["known_hosts"]).is_file():
        raise ValueError("pinned known_hosts missing")


def validate_sealed_inputs() -> dict:
    candidate_manifest = Path(F321["directory"]) / "manifest.json"
    if digest(candidate_manifest) != MANIFEST_SHA or digest(PACKAGE / "manifest.json") != PACKAGE_SHA:
        raise ValueError("sealed F321/package manifest drift")
    manifest = read_json(candidate_manifest)
    if manifest.get("schema") != "openmitrastar.f321-classic-ui-candidate/v1" or manifest.get("source", {}).get("candidate_sha256") != F314["sha256"]:
        raise ValueError("F321 must be built from the exact F314")
    # These false values are never silently interpreted as eligibility. A
    # separate reviewed executor manifest is mandatory for the execute path.
    for flag in ("candidate_eligible", "flash_supported", "release_eligible"):
        if manifest.get(flag) is not False:
            raise ValueError("sealed candidate flag changed: " + flag)
    if manifest.get("physical_validation", {}).get("authorized") is not False:
        raise ValueError("artifact must not assert physical authorization")
    if manifest["safety"]["protected_partitions"] != ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"]:
        raise ValueError("protected partition contract changed")
    for image in (F321, F314):
        validate_image(image)
    if digest(Path(F321["directory"]) / F321["known_hosts"]) != digest(Path(F314["directory"]) / F314["known_hosts"]):
        raise ValueError("UI-only candidate changed pinned SSH identity")
    for item in read_json(PACKAGE / "manifest.json")["files"]:
        path = item["path"]
        if not re.fullmatch(r"[A-Za-z0-9_./-]+", path) or ".." in Path(path).parts or path.startswith("/"):
            raise ValueError("unsafe packaged asset path")
        file = PACKAGE / "overlay" / path
        if file.stat().st_size != item["bytes"] or digest(file) != item["sha256"]:
            raise ValueError("packaged asset changed: " + path)
    return manifest


def generic_preflight(image: dict, current: dict) -> dict:
    env = {key: value for key, value in os.environ.items() if not key.startswith(("OM_Q3_FLASH_", "OM_Q3_F45_"))}
    env.update(environment(image, current))
    result = subprocess.run([sys.executable, str(WRITER), "--transport", "uart-ymodem", "--erase-bytes", "0x5e0000"],
                            env=env, cwd=ROOT, capture_output=True, text=True, timeout=90, check=False)
    if result.returncode:
        raise ValueError("local writer preflight failed: " + (result.stderr or result.stdout)[-2000:])
    report, _ = json.JSONDecoder().raw_decode(result.stdout)
    if report.get("mode") != "dry-run" or report.get("candidate_sha256") != image["sha256"] or report.get("expected_full_slot_sha256") != image["full_slot_sha256"]:
        raise ValueError("writer preflight identity mismatch")
    return report


def file_bindings() -> list[dict]:
    return [{"path": path, "sha256": digest(ROOT / path)} for path in EXECUTOR_FILES]


def validate_executor_review(path: Path, expected_sha: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or digest(path) != expected_sha:
        raise ValueError("exact executor-review manifest hash required")
    review = read_json(path)
    if (review.get("schema") != "openmitrastar.f321-executor-review/v1" or review.get("status") != "PASS_OFFLINE_EXECUTOR_REVIEW"
            or review.get("candidate_manifest_sha256") != MANIFEST_SHA or review.get("candidate_sha256") != F321["sha256"]
            or review.get("physical_authorization") is not False or review.get("hardware_actions_performed") is not False
            or review.get("resolved_requirement") != "reviewed F321 promotion and rollback executor"
            or review.get("sealed_candidate_flags") != {"candidate_eligible": False, "flash_supported": False, "release_eligible": False}
            or review.get("files") != file_bindings()):
        raise ValueError("executor review is missing, stale or overclaims its authority")
    qualification = review["qualification"]
    if digest(Path(qualification["path"])) != qualification["sha256"]:
        raise ValueError("executor qualification evidence drift")
    return review


def qualify_report(path: Path) -> int:
    tree = ET.parse(path)
    cases = tree.findall(".//testcase")
    if len(cases) < 10 or tree.findall(".//failure") or tree.findall(".//error") or tree.findall(".//skipped"):
        raise ValueError("executor focused tests must all pass, without skipped cases")
    names = {case.attrib.get("name") for case in cases}
    if not {"test_dry_run_does_not_open_hardware", "test_wrong_ack_stops_before_hardware", "test_ambiguous_writer_never_rolls_back", "test_postgate_failure_restores_exact_f314",
            "test_uart_tx_queue_timeout_is_bounded", "test_uart_prompt_retry_stops_at_prompt", "test_uart_progress_records_real_callback",
            "test_uart_modem_propagates_tx_timeout_without_retry"}.issubset(names):
        raise ValueError("qualification lacks required behavior gates")
    return len(cases)


def create_review(path: Path, qualification: Path) -> dict:
    validate_sealed_inputs()
    generic_preflight(F321, F314)
    generic_preflight(F314, F321)
    count = qualify_report(qualification)
    report = {
        "schema": "openmitrastar.f321-executor-review/v1", "status": "PASS_OFFLINE_EXECUTOR_REVIEW",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "candidate_sha256": F321["sha256"],
        "candidate_manifest_sha256": MANIFEST_SHA, "resolved_requirement": "reviewed F321 promotion and rollback executor",
        "sealed_candidate_flags": {"candidate_eligible": False, "flash_supported": False, "release_eligible": False},
        "physical_authorization": False, "hardware_actions_performed": False, "files": file_bindings(),
        "qualification": {"path": str(qualification.resolve()), "sha256": digest(qualification), "passed": count},
        "still_required": ["exact user authorization", "fresh pinned SSH/UART binding and exclusive lease", "current Bootbase protected/current-slot CRC checks", "physical boot and UI/platform verification"],
        "scope": "Resolves the executor-review blocker only. Hashes are integrity bindings, not signatures or user approval.",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="ascii") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    return report


def plan(direction: str, review_path: Path | None = None, review_sha: str = "") -> dict:
    validate_sealed_inputs()
    image, current = (F321, F314) if direction == "promote" else (F314, F321)
    preflight = generic_preflight(image, current)
    generic_preflight(current, image)
    reviewed = False
    if review_path is not None:
        validate_executor_review(review_path, review_sha)
        reviewed = True
    return {
        "schema": "openmitrastar.f321-mtd4-plan/v1", "mode": "dry-run", "direction": direction,
        "target_model": "HGW-500BNA-QCv2 A2", "target_host": HOST, "port": "COM3", "uart_pnp_device_id": PNP,
        "image": image, "current": current, "candidate": str(image_path(image)), "write_target": "mtd4/linux_live",
        "offset": "0x007e0000", "slot_bytes": SLOT_BYTES, "erase_bytes": ERASE_BYTES, "transport": "uart-ymodem",
        "protected_partitions": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"], "store_tail_preserved": True,
        "local_preflight_pass": True, "executor_review_verified": reviewed, "physical_authorization": False,
        "hardware_actions_performed": False, "physical_ready": False,
        "status": "OFFLINE_REVIEWED_PHYSICAL_AUTHORIZATION_AND_FRESH_GATES_PENDING" if reviewed else "NO_GO_EXECUTOR_REVIEW_PENDING",
        "required_ack": image["ack"], "recovery_rehearsal": str(REHEARSAL),
        "physical_lock": str(ROOT / "outputs/locks/f301-physical-radio.lock"),
        "readback_provenance": {"full_slot_sha256": "expected local padded image, not a digest read from hardware", "full_slot_crc32": "fresh Bootbase read required before erase and after write", "candidate_prefix": "full byte count cmp.b must match image size"},
        "rollback": {"image": F314, "automatic": "only after verified writer PASS then failed platform/UI gate", "ambiguous_flash": "STOP; no retry and no automatic rollback", "hard_lockup": "manual owner power-cycle may still be required; no automatic-recovery guarantee"},
        "duration": {"typical_minutes": "10-20 per image; rollback adds a second transfer", "flash_timeout_seconds": 1800, "postflash_wait_seconds": 360},
        "environment": environment(image, current), "protected_baseline_sha256": preflight["protected_partition_sha256"],
        "protected_baseline_crc32": preflight["protected_partition_crc32"],
    }


def verify_writer_result(directory: Path, image: dict, current: dict) -> dict:
    result = read_json(directory / "result.json")
    write, readback = result.get("physical_write", {}), result.get("readback", {})
    if (result.get("status") != "PASS" or result.get("candidate_sha256") != image["sha256"]
            or write != {"offset": 0x7E0000, "erase_size": ERASE_BYTES, "candidate_size": image["bytes"], "slot_size": SLOT_BYTES, "partition": "mtd4/linux_live"}
            or readback.get("full_slot_crc32") != image["full_slot_crc32"] or readback.get("candidate_prefix_compare") != "PASS"
            or result.get("protected_partitions", {}).get("status") != "PASS"):
        raise ValueError("writer outcome is ambiguous or differs from the exact plan")
    expected_files = {"bootbase-flash-uart.log", "backend.log", "uart-ymodem.log", "uart-ymodem-status.json", "uart-ymodem-console.log"}
    evidence = result.get("evidence", [])
    verified = set()
    for item in evidence:
        path = Path(item["path"])
        if not path.is_absolute():
            path = ROOT / path
        path = path.resolve()
        if path.parent != directory.resolve() or path.name not in expected_files or digest(path) != item["sha256"]:
            raise ValueError("writer transcript binding mismatch")
        verified.add(path.name)
    if verified != expected_files or len(evidence) != len(expected_files):
        raise ValueError("writer is missing exact UART/YMODEM evidence")
    trace = (directory / "bootbase-flash-uart.log").read_text(encoding="utf-8", errors="replace")
    backend = (directory / "backend.log").read_text(encoding="utf-8", errors="replace")
    counts = re.findall(r"Total of ([0-9]+) bytes? were the same", trace)
    if counts != [str(image["bytes"])]:
        raise ValueError("full candidate-prefix comparison count not proved")
    for marker in (
        "MTD4_PREWRITE_PHYSICAL_RECHECK_PASS=1 rollback_crc=", "current_live_crc=" + current["full_slot_crc32"],
        "PROTECTED_PARTITION_CRC_PASS=1", "MTD4_BOOTBASE_READBACK_PASS=1 full_slot_crc=" + image["full_slot_crc32"] + " prefix=identical",
        "MTD4_FLASH_AND_READBACK_PASS=1 candidate=" + image["sha256"], "candidate_transport=uart-ymodem",
        "OMF321_ERASED_PREFIX_CRC_PASS=1 bytes=6160384 crc=aa86bf2e",
    ):
        if marker not in backend:
            raise ValueError("writer did not prove marker: " + marker)
    for command in re.findall(r"spi_flash\s+(erase|write)\s+(0x[0-9a-fA-F]+)\s+([^\r\n]+)", trace):
        if int(command[1], 16) != 0x7E0000:
            raise ValueError("writer transcript contains an out-of-scope physical write")
    return {"status": "PASS_VERIFIED_WRITER", "candidate_sha256_expected": image["sha256"],
            "full_slot_sha256_expected_local": image["full_slot_sha256"], "full_slot_sha256_observed": None,
            "full_slot_crc32_observed": image["full_slot_crc32"], "current_prewrite_crc32_observed": current["full_slot_crc32"],
            "candidate_prefix_compared_bytes": image["bytes"], "protected_partitions_crc_verified": True}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--direction", choices=("promote", "rollback"), default="promote")
    parser.add_argument("--executor-review", type=Path)
    parser.add_argument("--executor-review-sha256", default="")
    parser.add_argument("--create-review", type=Path)
    parser.add_argument("--reviewed-executor", action="store_true")
    parser.add_argument("--qualification", type=Path)
    parser.add_argument("--verify-writer", type=Path)
    args = parser.parse_args()
    if args.create_review:
        if not args.reviewed_executor or not args.qualification:
            parser.error("review creation requires explicit executor review and focused test evidence")
        result = create_review(args.create_review, args.qualification)
    elif args.verify_writer:
        image, current = (F321, F314) if args.direction == "promote" else (F314, F321)
        result = verify_writer_result(args.verify_writer, image, current)
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
