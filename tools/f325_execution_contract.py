"""File-only F325 promotion/restore contract; no device API or execute mode.

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
MANIFEST_SHA = "0795f398d09de8346ce29468633e9f90a264f2fbba676b09d554089a20c0d1a9"
INVENTORY_SHA = "c658c7e048e23030c1631d3aea697b029b272e85af27c11b76b137f1b490cf24"
ACCEPTANCE = ROOT / "outputs/postflash/f321-acceptance-20260911T091500Z/result.json"
ACCEPTANCE_SHA = "7795bda97bc87e597677b779715bc0acede2e78ddbdd6fee370a376ce09f8f21"
BACKEND_SOURCE_SHA = "017032af5357afc7798d49d77529ef599a645f1f1b6aa54a94e1740907a8345f"
BACKEND = ROOT / "tools/f325_mtd4_bootbase_flash.ps1"
WRITER = ROOT / 'tools/f325_mtd4_one_shot.py'
PACKAGE = previous.PACKAGE
PACKAGE_SHA = previous.PACKAGE_SHA
verify_writer_result = previous.verify_writer_result
F325 = {
    "name": "f334", "directory": str(previous.DEVICE / "f334-f321-radar-once-device-bound"),
    "base": "openmitrastar-linux510-f334-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH",
    "sha256": "e18b221dda9a61bd1066c155c0cd7b44aef0d0fe06b1a1752a7e759e7730c7ec", "bytes": 5332992,
    "full_slot_crc32": "cc7d1938", "full_slot_sha256": "6f9596e3025d9aaa50fd4996561d2102622104080ed33c50e6d3dab5c744b55d",
    "version": "lyoko-foundation-6.9.5-f334-radar-once-f321-device", "known_hosts": "known_hosts.f334",
    "ack": "OPENMITRASTAR_F334_MTD4_E18B221D",
}
F321 = dict(previous.F321, ack="OPENMITRASTAR_F325_RESTORE_F321_EB8E23AC")
F314 = dict(previous.F314, ack="OPENMITRASTAR_F325_FALLBACK_F314_A0C7350A")
DIRECTIONS = {"promote": (F325, F321), "rollback": (F321, F325), "fallback": (F314, F325)}
EXECUTOR_FILES = tuple(dict.fromkeys((*previous.EXECUTOR_FILES,
    "tools/f325_execution_contract.py", "tools/f325_mtd4_runtime.ps1", "tools/f325_mtd4_bootbase_flash.ps1",
    "tools/promote_f325_mtd4_direct.ps1", "tools/f325_restore_mtd4.ps1", "tools/f325_ui_gate.py",
    "tools/test_f325_executor.py", "tools/verify_f321_authenticated_http.py",
    "tools/f325_hardware_context.ps1", "tools/f325_ssh_guard.ps1", "tools/test_f325_hardware_guards.py",
    "tools/f325_mtd4_one_shot.py", "tools/f325_assert_physical_context.ps1", "tools/f325_reboot_to_topaz_prompt.ps1",
    "tools/test_f325_ui_gate.py", "tools/build_f334_shadow_from_f321.py", "tools/f334_shadow_contract.py", "tools/f334_shadow_rootfs_worker.py", "tools/test_f334_artifact_catalog.py", "tools/package_lyoko_web_next.py",
    "tools/lyoko_web_rootfs_worker.py", "tools/lyoko_frontend_identity.py", "work/lyoko-web-next/src/classic/controller.js",
    "tools/f325_uart_ymodem_load.py", "tools/test_f325_uart_ymodem_load.py",
    "work/pydeps/ymodem/__init__.py", "work/pydeps/ymodem/Socket.py", "work/pydeps/ymodem/Protocol.py",
    "work/pydeps/ymodem/CRC.py", "work/pydeps/ymodem/Platform.py", "work/pydeps/ymodem/Version.py",
    "work/pydeps/serial/__init__.py", "work/pydeps/serial/serialutil.py", "work/pydeps/serial/serialwin32.py", "work/pydeps/serial/win32.py",
    "work/pydeps/ordered_set/__init__.py",
)))

REQUIRED_BEHAVIOR_GATES = {
    "test_f325_dry_run_never_opens_hardware", "test_f325_wrong_ack_stops_before_hardware",
    "test_f325_ambiguous_writer_never_restores", "test_f325_postgate_failure_restores_exact_f321",
    "test_f325_containment_failure_retains_lease", "test_f325_adapter_changes_only_image_pins",
    "test_f325_backend_requires_live_context", "test_f325_ssh_uncertainty_retains_lease",
    "test_f325_adapter_real_dry_run_uses_correct_workspace", "test_f325_reboot_source_binds_guard_path_without_changing_behavior",
    "test_negative_response_resends_same_block_without_advancing_progress",
    "test_late_ack_before_ten_seconds_does_not_resend",
    "test_terminal_observed_sequence_aborts_on_first_unexpected_byte_without_more_tx",
    "test_receiver_cancel_and_rx_error_stop_without_retransmission",
    "test_silence_keeps_ten_attempts_with_finite_absolute_waits",
    "test_persistent_crc_requests_keep_retry_limit_without_timeout_stalls",
    "test_tx_error_propagates_without_retry", "test_main_restores_previous_class_and_writes_events_once",
    "test_f325_writer_selects_receiver_driven_loader_and_restores_it",
    "test_f325_context_ps5_to_pwsh7_roundtrip", "test_f325_context_pwsh7_to_ps5_roundtrip",
    "test_f325_context_malformed_dates_rejected_in_both_shells",
    "test_f325_context_expired_dates_rejected_in_both_shells",
    "test_f325_context_non_utc_dates_rejected_in_both_shells",
    "test_f325_serial_api_constructs_without_opening_port",
}


def images(direction: str) -> tuple[dict, dict]:
    if direction not in DIRECTIONS:
        raise ValueError("unsupported F325 direction")
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
    path = Path(F325["directory"]) / "manifest.json"
    if digest(path) != MANIFEST_SHA:
        raise ValueError("sealed F325 manifest drift")
    manifest = read_json(path)
    if manifest.get("schema") != "openmitrastar.f334-shadow-candidate/v1" or manifest.get("source", {}).get("candidate_sha256") != F321["sha256"]:
        raise ValueError("F325 lineage mismatch")
    for flag in ("candidate_eligible", "flash_supported", "release_eligible"):
        if manifest.get(flag) is not False:
            raise ValueError("sealed F325 eligibility changed")
    if (manifest.get("storage", {}).get("persistent_writes_enabled") is not False
            or manifest.get("safety", {}).get("protected_partitions") != ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"]):
        raise ValueError("F325 physical/radio/storage authority drift")
    if digest(PACKAGE / "manifest.json") != PACKAGE_SHA:
        raise ValueError("F325 UI package manifest drift")
    shadow = manifest.get("shadow", {})
    for flag in ("shadow_arm_on_boot", "automatic_arm", "radar_start", "radar_get_status", "dfs_tx_authorized", "authoritative_enable", "weather_enable", "hardware_restore_proven"):
        if shadow.get(flag) is not False:
            raise ValueError("F325 must boot unarmed without DFS authority")
    if (shadow.get("single_arm_per_boot") is not True or shadow.get("sample_window_ms") != 20000
            or shadow.get("module_self_pin_after_configuration") is not True
            or shadow.get("recovery_after_arm") != "FULL_BOOT_AND_EXACT_F321_RESTORE"):
        raise ValueError("F325 diagnostic lifecycle mismatch")
    previous.validate_image(F325)
    if digest(Path(F325["directory"]) / F325["known_hosts"]) != digest(Path(F321["directory"]) / F321["known_hosts"]):
        raise ValueError("F325 pinned SSH identity differs from F321")
    if digest(Path(F325["directory"]) / "rootfs-inventory.json") != INVENTORY_SHA:
        raise ValueError("F325 rootfs inventory drift")
    inventory = read_json(Path(F325["directory"]) / "rootfs-inventory.json")
    catalogue = manifest.get("artifact_catalog")
    if not isinstance(catalogue, dict) or inventory.get("catalog_verification") != catalogue:
        raise ValueError("F326 catalogue verification evidence missing or inconsistent")
    for phase in ("source", "before_pack", "after_unpack"):
        row = catalogue.get(phase, {})
        if (row.get("status") != "PASS" or row.get("all_entries_verified") is not True
                or type(row.get("entries")) is not int or row["entries"] <= 0):
            raise ValueError("F326 complete catalogue verification did not pass")
    expected_catalogue_sha = inventory["expected_changes"]["usr/share/openmitrastar/radio5g/artifacts.sha256"]["sha256"]
    if (catalogue["before_pack"]["entries"] != catalogue["after_unpack"]["entries"]
            or catalogue["before_pack"]["catalog_sha256"] != expected_catalogue_sha
            or catalogue["after_unpack"]["catalog_sha256"] != expected_catalogue_sha):
        raise ValueError("F326 packed catalogue does not match the verified file tree")
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
        raise ValueError("file-only F325 preflight failed: " + (proc.stderr or proc.stdout)[-1500:])
    report, _ = json.JSONDecoder().raw_decode(proc.stdout)
    if report.get("mode") != "dry-run" or report.get("candidate_sha256") != image["sha256"] or report.get("expected_full_slot_sha256") != image["full_slot_sha256"]:
        raise ValueError("F325 preflight image identity mismatch")
    return report


def file_bindings() -> list[dict]:
    return [{"path": path, "sha256": digest(ROOT / path)} for path in EXECUTOR_FILES]


def qualify_report(path: Path) -> int:
    root = ET.parse(path)
    cases = root.findall(".//testcase")
    # Pytest includes parameter values in JUnit names; bind the named behavior
    # while still requiring every concrete case to pass without skips.
    names = {(case.get("name") or "").split("[", 1)[0] for case in cases}
    if len(cases) < 20 or root.findall(".//failure") or root.findall(".//error") or root.findall(".//skipped") or not REQUIRED_BEHAVIOR_GATES.issubset(names):
        raise ValueError("F325 qualification missing required all-pass behavior gates")
    return len(cases)


def validate_executor_review(path: Path, expected_sha: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha) or digest(path) != expected_sha:
        raise ValueError("exact F325 executor-review hash required")
    review = read_json(path)
    if (review.get("schema") != "openmitrastar.f325-executor-review/v1" or review.get("status") != "PASS_OFFLINE_EXECUTOR_REVIEW"
            or review.get("candidate_sha256") != F325["sha256"] or review.get("candidate_manifest_sha256") != MANIFEST_SHA
            or review.get("f321_acceptance_sha256") != ACCEPTANCE_SHA or review.get("files") != file_bindings()
            or review.get("physical_authorization") is not False or review.get("hardware_actions_performed") is not False
            or review.get("radio_actions_authorized") is not False or review.get("restore_image_sha256") != F321["sha256"]
            or review.get("fallback_image_sha256") != F314["sha256"]):
        raise ValueError("F325 executor review stale, incomplete or overclaims authority")
    qualification = review["qualification"]
    if digest(Path(qualification["path"])) != qualification["sha256"] or qualify_report(Path(qualification["path"])) != qualification["passed"]:
        raise ValueError("F325 qualification evidence drift")
    return review


def create_review(path: Path, qualification: Path) -> dict:
    validate_sealed_inputs()
    for image, current in DIRECTIONS.values():
        generic_preflight(image, current)
    count = qualify_report(qualification)
    result = {"schema": "openmitrastar.f325-executor-review/v1", "status": "PASS_OFFLINE_EXECUTOR_REVIEW",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(), "candidate_sha256": F325["sha256"],
        "candidate_manifest_sha256": MANIFEST_SHA, "f321_acceptance_sha256": ACCEPTANCE_SHA,
        "restore_image_sha256": F321["sha256"], "fallback_image_sha256": F314["sha256"],
        "physical_authorization": False, "hardware_actions_performed": False, "radio_actions_authorized": False,
        "qualification": {"path": str(qualification.resolve()), "sha256": digest(qualification), "passed": count},
        "files": file_bindings(), "scope": "Exact F325 unarmed diagnostic installation and F321 restoration only; F314 is a separately invoked contingency",
        "still_required": ["owner authorization for exact action", "fresh pinned SSH/UART binding and exclusive lease",
            "fresh Bootbase current/protected CRC before erase", "writer readback then platform/UI HTTP checks",
            "independent browser JavaScript and radio/client acceptance remain required"]}
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="ascii") as stream:
        stream.write(json.dumps(result, indent=2) + "\n")
    return result


def plan(direction: str, review_path: Path | None = None, review_sha: str = "") -> dict:
    validate_sealed_inputs()
    image, current = images(direction)
    preflight = generic_preflight(image, current)
    generic_preflight(F321, F325)
    reviewed = review_path is not None
    if reviewed:
        validate_executor_review(review_path, review_sha)
    return {"schema": "openmitrastar.f325-mtd4-plan/v1", "mode": "dry-run", "direction": direction,
        "target_model": "HGW-500BNA-QCv2 A2", "target_host": HOST, "port": "COM3", "uart_pnp_device_id": PNP,
        "image": image, "current": current, "candidate": str(image_path(image)), "write_target": "mtd4/linux_live",
        "offset": "0x007e0000", "slot_bytes": SLOT_BYTES, "erase_bytes": ERASE_BYTES, "transport": "uart-ymodem",
        "protected_partitions": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"], "store_tail_preserved": True,
        "required_ack": image["ack"], "local_preflight_pass": True, "executor_review_verified": reviewed,
        "physical_authorization": False, "hardware_actions_performed": False, "physical_ready": False,
        "radio_actions_authorized": False,
        "status": "OFFLINE_REVIEWED_FRESH_GATES_PENDING" if reviewed else "NO_GO_EXECUTOR_REVIEW_PENDING",
        "f321_acceptance": {"path": str(ACCEPTANCE), "sha256": ACCEPTANCE_SHA},
        "recovery_rehearsal": str(previous.REHEARSAL),
        "physical_lock": str(ROOT / "outputs/locks/f301-physical-radio.lock"),
        "rollback": {"image": F321, "automatic": "only after verified writer PASS then failed postflash gate in the same lease",
            "source_evidence": "F321 physical write/readback/boot plus independent acceptance; not an F325-to-F321 rehearsal",
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
