"""File-only plan by default; execute only the qualified Ethernet RAM loader.

The parent retains its Job and physical lease, observes this process exiting,
and creates a separate preloaded receipt before invoking the flash writer.
"""
from __future__ import annotations

import json
import os

from f323_ethernet_guard_process import InheritedPhysicalGuard
from f323_ethernet_native_loader import run_native_ram_load
from f323_ethernet_writer import (checked_path, common_parser, context_digest, dry_summary,
                                 get_plan, json_object, read_bounded, same_json,
                                 validate_native_result, validate_plan, NATIVE_FILE, RAM_FILE, SERVER_FILE)


def execute_loader(plan, output_dir, *, native_loader=run_native_ram_load,
                   guard_factory=InheritedPhysicalGuard, environ=None) -> dict:
    source = os.environ if environ is None else environ
    guard = None
    native_called = False
    native_result = None
    result = {"schema": "openmitrastar.f323-native-ethernet-load-cli/v1", "status": "STOP_NO_AUTOMATIC_RETRY",
              "writer_ready": False, "ram_handoff_ready": False, "native_cleanup_verified": False,
              "retain_lease_required": False, "flash_written": False}
    stage = "plan"
    try:
        validate_plan(plan, execute=True)
        stage = "output-and-context"
        output = checked_path(output_dir, must_exist=False)
        if output.exists():
            raise ValueError("new_output_required")
        context_digest(source)
        stage = "inherited-physical-guard"
        guard = guard_factory(direction=plan["direction"], network_authorized=True)
        if guard() is not True or guard.close_all() is not True:
            raise ValueError("physical_guard_unconfirmed")
        stage = "native-loader"
        native_called = True
        native_result = native_loader(direction=plan["direction"], server_ipv4=plan["network"]["server_ipv4"], output_dir=output,
                                      execute=True, network_authorized=True, parent_review_verified=True)
        stage = "native-result"
        ram = validate_native_result(native_result, plan)
        if (not same_json(json_object(read_bounded(output / NATIVE_FILE)), native_result)
                or not same_json(json_object(read_bounded(output / RAM_FILE)), ram)
                or not same_json(json_object(read_bounded(output / SERVER_FILE)), ram["server_result"])):
            raise ValueError("native_evidence_mismatch")
        # Never echo arbitrary adapter dictionaries or raw UART/guard material.
        result = {"schema": native_result["schema"], "status": native_result["status"], "candidate_sha256": plan["image"]["sha256"],
                "candidate_bytes": plan["image"]["bytes"], "target_host": "192.168.1.90", "server_ipv4": plan["network"]["server_ipv4"],
                "writer_ready": False, "ram_handoff_ready": True, "native_cleanup_verified": True,
                "retain_lease_required": False, "flash_written": False, "rebooted": False,
                "loader_process_exit_observed_by_parent": False,
                "native_result_path": str(output / "native-loader-result.json"),
                "ram_crc32_observed": ram["candidate_crc32"], "raw_uart_or_guard_output_logged": False}
    except Exception as error:
        result.update(status="STOP_NO_AUTOMATIC_RETRY", failed_stage=stage, error_type=type(error).__name__,
                      writer_ready=False, ram_handoff_ready=False)
        if native_called and (not isinstance(native_result, dict)
                              or native_result.get("native_cleanup_verified") is not True
                              or native_result.get("retain_lease_required") is not False):
            result["retain_lease_required"] = True
    finally:
        if guard is not None:
            # This preliminary helper must never remain active alongside the
            # native loader. Native-loader cleanup is validated independently.
            try:
                closed = guard.close_all() is True
            except Exception:
                closed = False
            if not closed:
                result.update(status="STOP_NO_AUTOMATIC_RETRY", ram_handoff_ready=False, writer_ready=False,
                              native_cleanup_verified=False, retain_lease_required=True,
                              preliminary_guard_cleanup_failed=True)
    return result


def main(argv=None, *, contract=None, loader=execute_loader) -> int:
    parser = common_parser(__doc__, "--output-dir")
    args = parser.parse_args(argv)
    try:
        plan = get_plan(args, contract)
        result = loader(plan, args.output_dir) if args.execute else dry_summary(plan, "loader")
    except Exception as error:
        result = {"schema": "openmitrastar.f323-native-ethernet-load-cli/v1", "status": "REFUSED",
                  "error_type": type(error).__name__, "hardware_actions_performed": False}
    print(json.dumps(result, indent=2, ensure_ascii=True, allow_nan=False))
    passed = (result.get("status") == "PASS_NATIVE_ETHERNET_RAM_LOAD" and result.get("ram_handoff_ready") is True
              and result.get("writer_ready") is False and result.get("native_cleanup_verified") is True)
    return 0 if result.get("status") == "DRY_RUN" or passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
