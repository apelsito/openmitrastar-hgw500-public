"""Exact preloaded-RAM F325/F321 writer; default is a file-only plan.

This entry never loads RAM or starts TFTP. The parent must first qualify the
native loader result and close its entire Job, then bind that fact to the live
physical context in OM_F325_ETHERNET_PRELOADED. No retry/recovery is performed.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from types import SimpleNamespace

import f325_ethernet_handoff as handoff
from f325_ethernet_guard_process import InheritedPhysicalGuard
from f325_ethernet_ram_gate import sanitize_server_result, verify_server_result


ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "tools/f325_mtd4_bootbase_flash.ps1"
PLAN_SCHEMA = "openmitrastar.f325-ethernet-plan/v1"
NATIVE_SCHEMA = "openmitrastar.f325-native-ethernet-load/v1"
PRELOADED_SCHEMA = "openmitrastar.f325-ethernet-preloaded/v1"
PRELOADED_ENV = "OM_F325_ETHERNET_PRELOADED"
CONTEXT_ENV = "OM_F325_PHYSICAL_CONTEXT"
RAM_FILE = "ethernet-ram-result.json"
SERVER_FILE = "ethernet-server-result.json"
NATIVE_FILE = "native-loader-result.json"


class WriterFailure(RuntimeError):
    pass


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def json_object(data: bytes | str) -> dict:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def reject_constant(_):
        raise ValueError("non-finite JSON")

    value = json.loads(data, object_pairs_hook=unique, parse_constant=reject_constant)
    if not isinstance(value, dict):
        raise ValueError("JSON object required")
    return value


def same_json(left, right) -> bool:
    return json.dumps(left, sort_keys=True, allow_nan=False) == json.dumps(right, sort_keys=True, allow_nan=False)


def checked_path(path: Path, *, must_exist: bool) -> Path:
    path = Path(path).absolute()
    for parent in (path, *path.parents):
        if parent.is_symlink() or getattr(parent, "is_junction", lambda: False)():
            raise WriterFailure("symlink_or_junction")
    return path.resolve(strict=must_exist)


def read_bounded(path: Path, maximum=65536) -> bytes:
    path = checked_path(path, must_exist=True)
    if not path.is_file():
        raise WriterFailure("regular_evidence_required")
    with path.open("rb") as stream:
        value = stream.read(maximum + 1)
    if len(value) > maximum:
        raise WriterFailure("evidence_size_limit")
    return value


def write_once(path: Path, value: dict) -> None:
    with path.open("x", encoding="ascii", newline="\n") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n")


def common_parser(description: str, output_flag: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description, allow_abbrev=False)
    parser.add_argument("--direction", choices=("promote", "rollback"), default="promote")
    parser.add_argument("--server-ip", default="192.168.1.49")
    parser.add_argument("--interface-index", type=int, default=18)
    parser.add_argument("--executor-review", type=Path)
    parser.add_argument("--executor-review-sha256", default="")
    parser.add_argument("--network-authorization", type=Path)
    parser.add_argument("--network-authorization-sha256", default="")
    parser.add_argument("--firewall-mode", choices=("temporary-scoped-rule", "existing-permission"), default="temporary-scoped-rule")
    parser.add_argument("--existing-permission", type=Path)
    parser.add_argument("--existing-permission-sha256", default="")
    parser.add_argument(output_flag, type=Path, required=True)
    parser.add_argument("--execute", action="store_true")
    return parser


def get_plan(args, contract=None) -> dict:
    contract = contract or importlib.import_module("f325_ethernet_execution_contract")
    plan = contract.plan(args.direction, review_path=args.executor_review,
                         review_sha=args.executor_review_sha256,
                         network_authorization_path=args.network_authorization,
                         network_authorization_sha=args.network_authorization_sha256,
                         server_ipv4=args.server_ip, interface_index=args.interface_index,
                         firewall_mode=args.firewall_mode, existing_permission_path=args.existing_permission,
                         existing_permission_sha=args.existing_permission_sha256)
    validate_plan(plan, execute=args.execute)
    if plan["network"]["server_ipv4"] != args.server_ip or plan["network"]["interface_index"] != args.interface_index:
        raise WriterFailure("requested_network_differs_from_plan")
    return plan


def validate_plan(plan: dict, *, execute: bool) -> None:
    if not isinstance(plan, dict) or plan.get("schema") != PLAN_SCHEMA or plan.get("transport") != "ethernet-tftp":
        raise WriterFailure("ethernet_plan_required")
    image, current = handoff.exact_pair(plan["direction"])
    for label, expected in (("image", image), ("current", current)):
        row = plan.get(label, {})
        for key in ("directory", "base", "sha256", "bytes", "full_slot_crc32", "full_slot_sha256", "ack"):
            if type(row.get(key)) is not type(expected[key]) or row[key] != expected[key]:
                raise WriterFailure("plan_image_mismatch")
    network = plan.get("network", {})
    handoff.exact_server(network["server_ipv4"])
    if (network.get("client_ipv4") != "192.168.1.90" or type(network.get("interface_index")) is not int
            or network["interface_index"] <= 0 or not isinstance(network.get("interface_alias"), str)
            or not 1 <= len(network["interface_alias"]) <= 128
            or any(ord(char) < 32 for char in network["interface_alias"])):
        raise WriterFailure("network_plan_mismatch")
    if plan.get("erase_bytes") != handoff.ERASE_BYTES or type(plan.get("erase_bytes")) is not int:
        raise WriterFailure("erase_scope_mismatch")
    if plan.get("slot_bytes") != handoff.SLOT_BYTES or type(plan.get("slot_bytes")) is not int:
        raise WriterFailure("slot_scope_mismatch")
    if execute and (plan.get("executor_review_verified") is not True or plan.get("network_authorization_verified") is not True):
        raise WriterFailure("review_and_network_authorization_required")
    preflight = plan.get("preflight", {})
    expected = {"mode": "dry-run", "candidate_sha256": image["sha256"], "candidate_bytes": image["bytes"],
                "candidate_crc32": handoff.CRCS[image["sha256"]], "current_live_sha256": current["full_slot_sha256"],
                "current_live_crc32": current["full_slot_crc32"], "expected_full_slot_sha256": image["full_slot_sha256"],
                "expected_full_slot_crc32": image["full_slot_crc32"], "target_bytes": handoff.SLOT_BYTES,
                "target_offset": "0x007e0000", "layout_mode": "squashfs-split"}
    if any(type(preflight.get(key)) is not type(value) or preflight[key] != value for key, value in expected.items()):
        raise WriterFailure("preflight_identity_mismatch")
    for key, width in (("protected_partition_sha256", 64), ("protected_partition_crc32", 8)):
        rows = preflight.get(key, {})
        if set(rows) != {"mtd0", "mtd1", "mtd2", "mtd3", "mtd5"} or any(
                not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{%d}" % width, value) for value in rows.values()):
            raise WriterFailure("protected_baseline_mismatch")
    if (preflight.get("rollback_sha256") != preflight["protected_partition_sha256"]["mtd3"]
            or preflight.get("rollback_crc32") != preflight["protected_partition_crc32"]["mtd3"]):
        raise WriterFailure("rollback_baseline_mismatch")
    if plan.get("protected_baseline_sha256") != preflight["protected_partition_sha256"] or plan.get("protected_baseline_crc32") != preflight["protected_partition_crc32"]:
        raise WriterFailure("plan_baseline_mismatch")
    env = plan.get("environment")
    if not isinstance(env, dict) or any(not isinstance(key, str) or not isinstance(value, str) for key, value in env.items()):
        raise WriterFailure("invalid_environment")
    candidate = str(Path(image["directory"]) / (image["base"] + ".webformat.bin"))
    required_env = {"OM_Q3_FLASH_ACK": image["ack"], "OM_Q3_FLASH_CANDIDATE": candidate,
                    "OM_Q3_FLASH_EXPECTED_SHA256": image["sha256"], "OM_Q3_FLASH_EXPECTED_BYTES": str(image["bytes"]),
                    "OM_Q3_FLASH_POWERSHELL_BACKEND": str(BACKEND),
                    "OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32": current["full_slot_crc32"],
                    "OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256": current["full_slot_sha256"],
                    "OM_Q3_F45_REQUIRE_BACKUP_LIVE_SLOT_MATCH": "0"}
    if any(env.get(key) != value for key, value in required_env.items()) or CONTEXT_ENV in env or PRELOADED_ENV in env:
        raise WriterFailure("environment_identity_mismatch")


def context_digest(environ) -> str:
    encoded = environ.get(CONTEXT_ENV)
    if not isinstance(encoded, str) or not encoded or len(encoded) > 16384:
        raise WriterFailure("physical_context_required")
    return digest(encoded.encode("utf-8"))


def validate_native_result(native: dict, plan: dict) -> dict:
    image = plan["image"]
    required = {"schema": NATIVE_SCHEMA, "status": "PASS_NATIVE_ETHERNET_RAM_LOAD",
                "candidate_sha256": image["sha256"], "candidate_bytes": image["bytes"],
                "target_host": "192.168.1.90", "server_ipv4": plan["network"]["server_ipv4"],
                "writer_ready": False, "ram_handoff_ready": True, "retain_lease_required": False,
                "flash_written": False, "rebooted": False, "host_network_or_firewall_changed": False,
                "loader_process_exit_observed_by_parent": False, "parent_execution_review_verified": True,
                "raw_uart_or_guard_output_logged": False, "native_cleanup_verified": True}
    if any(type(native.get(key)) is not type(value) or native[key] != value for key, value in required.items()):
        raise WriterFailure("native_result_contract")
    cleanup = native.get("cleanup")
    if not isinstance(cleanup, dict) or set(cleanup) != {"server", "uart", "guard_helpers"} or any(value is not True for value in cleanup.values()):
        raise WriterFailure("native_cleanup_contract")
    ram = native.get("ram_result")
    handoff.validate_ram_result(ram, direction=plan["direction"], server_ipv4=plan["network"]["server_ipv4"])
    checks = ("volatile_network_environment", "server_ready", "decimal_and_hex_transfer_count", "scoped_server_transfer", "filesize", "iminfo", "ram_crc32")
    if (ram.get("runtime_adapters_verified") is not False or ram.get("environment_saved") is not False
            or type(ram.get("tx_commands_issued")) is not int or ram["tx_commands_issued"] != 8
            or type(ram.get("tftp_commands_issued")) is not int or ram["tftp_commands_issued"] != 1
            or any(ram.get("checks", {}).get(key) is not True for key in checks)):
        raise WriterFailure("ram_core_contract")
    # Metadata-only view: image bytes have already been checked by the plan and
    # loader. Do not open/reload/serve firmware at this handoff boundary.
    identity = SimpleNamespace(source_path=Path(image["directory"]) / (image["base"] + ".webformat.bin"),
                               expected_sha256=image["sha256"], expected_bytes=image["bytes"])
    identity.metadata = lambda: {"path": str(identity.source_path), "sha256": identity.expected_sha256,
                                 "bytes": identity.expected_bytes, "blocks_including_terminal": image["bytes"] // 512 + 1}
    server = sanitize_server_result(ram["server_result"], identity, plan["network"]["server_ipv4"], "192.168.1.90")
    verify_server_result(server, identity, plan["network"]["server_ipv4"], "192.168.1.90")
    if not same_json(server, ram["server_result"]):
        raise WriterFailure("unsanitized_server_result")
    return ram


def validate_preloaded(plan: dict, directory: Path, environ) -> dict:
    directory = checked_path(directory, must_exist=True)
    if not directory.is_dir():
        raise WriterFailure("loader_evidence_directory_required")
    encoded = environ.get(PRELOADED_ENV)
    if not isinstance(encoded, str) or not 0 < len(encoded) <= 32768:
        raise WriterFailure("preloaded_receipt_required")
    receipt = json_object(encoded)
    required = {"schema": PRELOADED_SCHEMA, "direction": plan["direction"],
                "candidate_sha256": plan["image"]["sha256"], "loader_job_closed": True,
                "physical_context_sha256": context_digest(environ)}
    if any(type(receipt.get(key)) is not type(value) or receipt[key] != value for key, value in required.items()):
        raise WriterFailure("preloaded_receipt_binding")
    path = Path(receipt["native_result_path"])
    if not path.is_absolute() or checked_path(path, must_exist=True) != directory / NATIVE_FILE:
        raise WriterFailure("native_result_path_binding")
    native_bytes = read_bounded(path)
    if receipt.get("native_result_sha256") != digest(native_bytes):
        raise WriterFailure("native_result_hash")
    native = json_object(native_bytes)
    ram = validate_native_result(native, plan)
    ram_bytes, server_bytes = read_bounded(directory / RAM_FILE), read_bounded(directory / SERVER_FILE)
    if not same_json(json_object(ram_bytes), ram) or not same_json(json_object(server_bytes), ram["server_result"]):
        raise WriterFailure("ram_files_binding")
    for name in ("result.json", "backend.log", "bootbase-flash-uart.log"):
        if (directory / name).exists():
            raise WriterFailure("writer_evidence_already_exists")
    return {"directory": directory, "ram": ram, "native_sha256": digest(native_bytes),
            "context_sha256": required["physical_context_sha256"],
            "buffers": {NATIVE_FILE: native_bytes, RAM_FILE: ram_bytes, SERVER_FILE: server_bytes}}


def backend_command(plan: dict, directory: Path, *, timeout: int, program: str) -> list[str]:
    image, pre = plan["image"], plan["preflight"]
    fields = [("Ack", image["ack"]), ("Candidate", str(Path(image["directory"]) / (image["base"] + ".webformat.bin"))),
              ("ExpectedSha256", image["sha256"]), ("ExpectedBytes", image["bytes"]), ("Port", "COM3"),
              ("ServerIp", plan["network"]["server_ipv4"]), ("ClientIp", "192.168.1.90"), ("HostAddress", "192.168.1.90"),
              ("Transcript", str(directory / "bootbase-flash-uart.log")), ("RollbackSha256", pre["rollback_sha256"])]
    fields += [(f"ProtectedMtd{part}Sha256", pre["protected_partition_sha256"][f"mtd{part}"]) for part in (0, 1, 2, 5)]
    fields += [(f"ProtectedMtd{part}Crc32", pre["protected_partition_crc32"][f"mtd{part}"]) for part in (0, 1, 2, 5)]
    fields += [("RollbackCrc32", pre["rollback_crc32"]), ("CurrentLiveCrc32", pre["current_live_crc32"]),
               ("ExpectedCandidateCrc32", pre["candidate_crc32"]), ("ExpectedFullSlotSha256", pre["expected_full_slot_sha256"]),
               ("ExpectedFullSlotCrc32", pre["expected_full_slot_crc32"]), ("EraseBytes", handoff.ERASE_BYTES), ("TimeoutSeconds", timeout)]
    args = [program, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(BACKEND), "-Execute"]
    for key, value in fields:
        args.extend(("-" + key, str(value)))
    return args + ["-SkipReboot", "-SkipNetworkTransfer"]


def stop_owned_process(process, launch_requested: bool) -> bool:
    if process is None:
        return not launch_requested
    try:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        code = process.poll()
        waited = process.wait(timeout=0)
        return type(code) is int and type(waited) is int and code == waited
    except Exception:
        return False


def verified_writer_result(plan: dict, proof: dict, directory: Path) -> dict:
    image = plan["image"]
    buffers = {name: read_bounded(directory / name, 4 * 1024 * 1024) for name in ("backend.log", "bootbase-flash-uart.log")}
    for name, original in proof["buffers"].items():
        if read_bounded(directory / name) != original:
            raise WriterFailure("loader_evidence_changed")
    buffers.update({RAM_FILE: proof["buffers"][RAM_FILE], SERVER_FILE: proof["buffers"][SERVER_FILE]})
    result = {"schema": handoff.WRITER_SCHEMA, "status": "PASS", "candidate_sha256": image["sha256"],
              "backend_sha256": handoff.BACKEND_SHA256,
              "physical_write": {"offset": 0x7e0000, "erase_size": handoff.ERASE_BYTES, "candidate_size": image["bytes"],
                                 "slot_size": handoff.SLOT_BYTES, "partition": "mtd4/linux_live"},
              "flash": {"control_transport": "uart-bootbase", "network_transfer_performed": False,
                        "skip_reboot": True, "skip_network_transfer": True},
              "readback": {"full_slot_crc32": image["full_slot_crc32"], "candidate_prefix_compare": "PASS",
                           "full_slot_sha256_expected_local": image["full_slot_sha256"], "full_slot_sha256_observed": None},
              "protected_partitions": {"status": "PASS", "hardware_sha256_observed": None},
              "native_result_sha256": proof["native_sha256"], "physical_context_sha256": proof["context_sha256"],
              "evidence": [{"path": name, "sha256": digest(data)} for name, data in sorted(buffers.items())]}
    # The existing verifier requires a result.json. Verify an isolated draft
    # against byte-identical copies; never publish an unverified PASS in the
    # real attempt directory. No firmware is copied into this scratch tree.
    with tempfile.TemporaryDirectory(prefix=".ethernet-writer-verify-", dir=directory) as scratch:
        staged = Path(scratch)
        for name, data in buffers.items():
            with (staged / name).open("xb") as stream:
                stream.write(data)
        write_once(staged / "result.json", result)
        verified = handoff.verify_writer_result(staged, direction=plan["direction"], server_ipv4=plan["network"]["server_ipv4"], expected_ram_result=proof["ram"])
    result["verification"] = verified
    return result


def execute_writer(plan: dict, evidence_dir: Path, *, ack: str, timeout=900, environ=None,
                   guard_factory=InheritedPhysicalGuard, popen_factory=subprocess.Popen,
                   resolve_program=shutil.which) -> dict:
    env_source = os.environ if environ is None else environ
    result = {"schema": handoff.WRITER_SCHEMA, "status": "STOP_NO_AUTOMATIC_RETRY", "candidate_sha256": None,
              "backend_started": False, "backend_process_exited": False, "guard_helpers_closed": False,
              "retain_lease_required": False, "automatic_retry": False, "automatic_rollback": False,
              "generated_at_utc": datetime.now(timezone.utc).isoformat()}
    process = guard = log = None
    launch_requested = owned_log = False
    directory = None
    stage = "plan"
    successful = False
    try:
        validate_plan(plan, execute=True)
        image = plan["image"]
        result["candidate_sha256"] = image["sha256"]
        if ack != image["ack"] or type(timeout) is not int or not 600 <= timeout <= 1800:
            raise WriterFailure("exact_ack_and_timeout_required")
        stage = "preloaded-proof"
        proof = validate_preloaded(plan, evidence_dir, env_source)
        directory = proof["directory"]
        if digest(read_bounded(BACKEND, 262144)) != handoff.BACKEND_SHA256:
            raise WriterFailure("original_backend_hash")
        program = resolve_program("pwsh.exe")
        if not program or not Path(program).is_absolute():
            raise WriterFailure("powershell_program_required")
        stage = "physical-guard"
        guard = guard_factory(direction=plan["direction"], network_authorized=True)
        if guard() is not True:
            raise WriterFailure("physical_guard_unconfirmed")
        # Recheck the evidence/context and source after the live guard, before
        # any backend is launched. No image/RAM load occurs here.
        fresh = validate_preloaded(plan, directory, env_source)
        if fresh["native_sha256"] != proof["native_sha256"] or fresh["context_sha256"] != proof["context_sha256"]:
            raise WriterFailure("preloaded_binding_changed")
        if digest(read_bounded(BACKEND, 262144)) != handoff.BACKEND_SHA256:
            raise WriterFailure("original_backend_changed")
        environment = {key: value for key, value in env_source.items() if not key.startswith(("OM_Q3_FLASH_", "OM_Q3_F45_"))}
        environment.update(plan["environment"])
        command = backend_command(plan, directory, timeout=timeout, program=program)
        stage = "backend"
        log = (directory / "backend.log").open("xb", buffering=0)
        owned_log = True
        launch_requested = True
        process = popen_factory(command, cwd=str(ROOT), env=environment, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, shell=False, close_fds=True,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        result["backend_started"] = True
        code = process.wait(timeout=timeout + 300)
        if type(code) is not int or type(process.poll()) is not int or process.poll() != code or code != 0:
            raise WriterFailure("backend_did_not_exit_zero")
        successful = True
    except Exception as error:
        result["failed_stage"] = stage
        result["error_type"] = type(error).__name__
    finally:
        result["backend_process_exited"] = stop_owned_process(process, launch_requested)
        if log is not None:
            try:
                log.close()
            except Exception:
                result["backend_process_exited"] = False
        try:
            result["guard_helpers_closed"] = guard is None or guard.close_all() is True
        except Exception:
            result["guard_helpers_closed"] = False
        result["retain_lease_required"] = not (result["backend_process_exited"] and result["guard_helpers_closed"])
    if successful and not result["retain_lease_required"]:
        try:
            if digest(read_bounded(BACKEND, 262144)) != handoff.BACKEND_SHA256:
                raise WriterFailure("backend_source_changed")
            verified = verified_writer_result(plan, proof, directory)
            result.update(verified)
        except Exception as error:
            result["status"] = "STOP_NO_AUTOMATIC_RETRY"
            result["failed_stage"] = "writer-proof"
            result["error_type"] = type(error).__name__
    if owned_log:
        try:
            write_once(directory / "result.json", result)
        except Exception:
            result.update(status="STOP_NO_AUTOMATIC_RETRY", evidence_write_failed=True)
    return result


def dry_summary(plan: dict, role: str) -> dict:
    return {"schema": "openmitrastar.f325-ethernet-" + role + "-plan/v1", "status": "DRY_RUN", "mode": "dry-run",
            "direction": plan["direction"], "candidate_sha256": plan["image"]["sha256"], "candidate_bytes": plan["image"]["bytes"],
            "network": plan["network"], "executor_review_verified": plan.get("executor_review_verified") is True,
            "network_authorization_verified": plan.get("network_authorization_verified") is True,
            "hardware_actions_performed": False, "flash_written": False}


def main(argv=None, *, contract=None, writer=execute_writer) -> int:
    parser = common_parser(__doc__, "--evidence-dir")
    parser.add_argument("--ack", default="")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args(argv)
    try:
        if not 600 <= args.timeout <= 1800:
            raise WriterFailure("timeout_out_of_range")
        plan = get_plan(args, contract)
        result = writer(plan, args.evidence_dir, ack=args.ack, timeout=args.timeout) if args.execute else dry_summary(plan, "writer")
    except Exception as error:
        result = {"schema": handoff.WRITER_SCHEMA, "status": "REFUSED", "error_type": type(error).__name__, "hardware_actions_performed": False}
    print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
    return 0 if result.get("status") in {"DRY_RUN", "PASS"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
