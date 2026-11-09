#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "work" / "mission-state"
HARDWARE_STATE = MISSION / "HARDWARE_STATE.json"
POST_TX7_RUNBOOK = MISSION / "POST_TX7_5G_HANG_RECOVERY_RUNBOOK_20260822.md"
RECOVERY_GATE = ROOT / "tools" / "verify_post_tx7_recovery.ps1"
RECOVERY_RESULT_VERIFIER = ROOT / "tools" / "verify_post_tx7_recovery_result.py"
RECOVERY_RESULT_VERIFIER_TEST = ROOT / "tools" / "test_post_tx7_recovery_result_verifier.py"
RESUME_GATE = ROOT / "tools" / "resume_post_tx7_5g_hang.ps1"
RESUME_RESULT_VERIFIER = ROOT / "tools" / "verify_resume_post_tx7_result.py"
RESUME_RESULT_VERIFIER_TEST = ROOT / "tools" / "test_resume_post_tx7_result_verifier.py"
LYOKO_REENTRY_GATE = ROOT / "tools" / "verify_router_lyoko_reentry.ps1"
TX7_GATE = ROOT / "tools" / "run_w2_2g_tx7_gate.ps1"
TX7_AUTO_GATE = ROOT / "tools" / "run_w2_2g_tx7_auto_gate.ps1"
TX7_CLIENT_WAITER = ROOT / "tools" / "wait_w2_2g_client.py"
TX11_GATE = ROOT / "tools" / "run_w2_2g_tx11_gate.ps1"
TX11_BOOT_COLLECTOR = ROOT / "tools" / "collect_w2_tx11_boot_evidence.ps1"
TX13_RAM_BOOT = ROOT / "tools" / "run_w2_tx13_ram_boot.ps1"
TX13_TRACE_COLLECTOR = ROOT / "tools" / "collect_w2_tx13_mgmt_trace.ps1"
TX13_TRACE_TEST = ROOT / "tools" / "test_w2_tx13_mgmt_trace.py"
TX9_GATE = ROOT / "tools" / "run_w2_2g_tx9_gate.ps1"
TX9_BOOT_VERIFIER = ROOT / "tools" / "verify_w2_tx9_boot_evidence.py"
TX9_GATE_TEST = ROOT / "tools" / "test_w2_tx9_gate.py"
AELITA_MEMORY_GUARD = ROOT / "tools" / "verify_router_lyoko_aelita_memory.py"
AELITA_MEMORY_GUARD_TEST = ROOT / "tools" / "test_router_lyoko_aelita_memory.py"
EVIDENCE_BINDINGS_GUARD = ROOT / "tools" / "validate_router_lyoko_evidence_bindings.py"
EVIDENCE_BINDINGS_GUARD_TEST = ROOT / "tools" / "test_router_lyoko_evidence_bindings.py"
TELEMETRY_CONTRACT_GUARD = ROOT / "tools" / "validate_router_lyoko_telemetry_contract.py"
TELEMETRY_CONTRACT_GUARD_TEST = ROOT / "tools" / "test_router_lyoko_telemetry_contract.py"
OBJECTIVE_COVERAGE_GUARD = ROOT / "tools" / "verify_router_lyoko_objective_coverage.py"
OBJECTIVE_COVERAGE_GUARD_TEST = ROOT / "tools" / "test_router_lyoko_objective_coverage.py"
CURRENT_OFFLINE_SUITE = ROOT / "tools" / "run_router_lyoko_current_offline_suite.py"
CURRENT_OFFLINE_SUITE_TEST = ROOT / "tools" / "test_router_lyoko_current_offline_suite.py"
SERVED_FILES_VERIFIER = ROOT / "tools" / "verify_router_lyoko_served_files.py"
SERVED_FILES_VERIFIER_TEST = ROOT / "tools" / "test_router_lyoko_served_files_verifier.py"
LYOKO_OVERLAY = MISSION / "router-lyoko-v0"
LYOKO_MANIFEST = LYOKO_OVERLAY / "manifest.json"
LYOKO_WEB_ROOT = LYOKO_OVERLAY / "rootfs" / "var" / "www"
LYOKO_PACKAGE = ROOT / "outputs" / "router-lyoko" / "router-lyoko-v0-overlay.tar.gz"
LYOKO_VALIDATION = LYOKO_OVERLAY / "VALIDATION.md"

EXPECTED_BOOT_STATE = "TX7_POST_5G_MISALIGNED_ACCESS_HUNG_WAITING_PHYSICAL_POWER_CYCLE"
EXPECTED_ACCESS_MARKER = "PHYSICAL_POWER_CYCLE_REQUIRED"
EXPECTED_LYOKO_SHA256 = "072d9d34962a55254ec4751fe0a33a94adcbb29f94a80f56e02861a20ec67beb"
EXPECTED_LYOKO_BYTES = 53432
RECOVERED_BOOT_STATES = {
    "TX7_RAM_RECOVERED_2G_CLIENT_GATE_ACTIVE",
    "TX7_RAM_RECOVERED_2G_NO_CLIENT_SOAK_COMPLETE",
    "TX11_RAM_BOOTED_2G_AP_ENABLED_AUTH_ASSOC_BLOCKED",
    "TX13_RAM_BOOTED_2G_AP_ENABLED_AUTH_TX_NO_ASSOC_REQ",
    "TX17_RAM_BOOTED_2G_AP_ENABLED_NO_CLIENT_RX0",
}

FORBIDDEN_SOURCE_TOKENS = (
    "flash_erase",
    "mtd_debug",
    "fw_setenv",
    "saveenv",
    "bootm",
    "ATGO",
    "mode COM",
    "om-radio5-start",
    "run_qtn_w3_tx7_client_traffic",
)


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    detail: str


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(read_text(path).lstrip("\ufeff"))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def powershell_plan(script: Path, *args: str, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            *args,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def parse_first_json(text: str) -> dict[str, Any]:
    stripped = text.lstrip()
    parsed, _ = json.JSONDecoder().raw_decode(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("first JSON value is not an object")
    return parsed


def mutation_flags_false(plan: dict[str, Any]) -> bool:
    mutations = plan.get("mutations")
    if isinstance(mutations, dict):
        return all(value is False for value in mutations.values())
    observed = [
        plan.get(key)
        for key in ("uart_opened", "module_reload", "network_reconfigure", "reboot", "bootenv", "mtd", "flash")
        if key in plan
    ]
    return bool(observed) and all(value is False for value in observed)


def source_has_no_forbidden_tokens(path: Path) -> tuple[bool, list[str]]:
    text = read_text(path)
    hits = [token for token in FORBIDDEN_SOURCE_TOKENS if token in text]
    return not hits, hits


def build_report(expected_lyoko_sha256: str, expected_lyoko_bytes: int) -> dict[str, Any]:
    checks: list[Check] = []
    artifacts: dict[str, Any] = {}

    for path, check_id in (
        (HARDWARE_STATE, "files.hardware_state"),
        (POST_TX7_RUNBOOK, "files.post_tx7_runbook"),
        (RECOVERY_GATE, "files.recovery_gate"),
        (RECOVERY_RESULT_VERIFIER, "files.recovery_result_verifier"),
        (RECOVERY_RESULT_VERIFIER_TEST, "files.recovery_result_verifier_test"),
        (RESUME_GATE, "files.resume_gate"),
        (RESUME_RESULT_VERIFIER, "files.resume_result_verifier"),
        (RESUME_RESULT_VERIFIER_TEST, "files.resume_result_verifier_test"),
        (LYOKO_REENTRY_GATE, "files.lyoko_reentry_gate"),
        (TX7_GATE, "files.tx7_gate"),
        (TX7_AUTO_GATE, "files.tx7_auto_gate"),
        (TX7_CLIENT_WAITER, "files.tx7_client_waiter"),
        (TX11_GATE, "files.tx11_gate"),
        (TX11_BOOT_COLLECTOR, "files.tx11_boot_collector"),
        (TX13_RAM_BOOT, "files.tx13_ram_boot"),
        (TX13_TRACE_COLLECTOR, "files.tx13_trace_collector"),
        (TX13_TRACE_TEST, "files.tx13_trace_test"),
        (TX9_GATE, "files.tx9_gate"),
        (TX9_BOOT_VERIFIER, "files.tx9_boot_verifier"),
        (TX9_GATE_TEST, "files.tx9_gate_test"),
        (AELITA_MEMORY_GUARD, "files.aelita_memory_guard"),
        (AELITA_MEMORY_GUARD_TEST, "files.aelita_memory_guard_test"),
        (EVIDENCE_BINDINGS_GUARD, "files.evidence_bindings_guard"),
        (EVIDENCE_BINDINGS_GUARD_TEST, "files.evidence_bindings_guard_test"),
        (TELEMETRY_CONTRACT_GUARD, "files.telemetry_contract_guard"),
        (TELEMETRY_CONTRACT_GUARD_TEST, "files.telemetry_contract_guard_test"),
        (OBJECTIVE_COVERAGE_GUARD, "files.objective_coverage_guard"),
        (OBJECTIVE_COVERAGE_GUARD_TEST, "files.objective_coverage_guard_test"),
        (CURRENT_OFFLINE_SUITE, "files.current_offline_suite"),
        (CURRENT_OFFLINE_SUITE_TEST, "files.current_offline_suite_test"),
        (SERVED_FILES_VERIFIER, "files.served_files_verifier"),
        (SERVED_FILES_VERIFIER_TEST, "files.served_files_verifier_test"),
        (LYOKO_MANIFEST, "files.lyoko_manifest"),
        (LYOKO_WEB_ROOT, "files.lyoko_web_root"),
        (LYOKO_PACKAGE, "files.lyoko_package"),
        (LYOKO_VALIDATION, "files.lyoko_validation"),
    ):
        exists = path.is_dir() if check_id.endswith("_root") else path.is_file()
        checks.append(Check(check_id, exists, f"{path} must exist"))

    if not all(check.ok for check in checks if check.id.startswith("files.")):
        return render_report(checks, artifacts)

    state = load_json(HARDWARE_STATE)
    current = state.get("current_observation", {})
    boot_state = str(current.get("boot_state", ""))
    current_access = str(current.get("current_access", ""))
    waiting_power_cycle = boot_state == EXPECTED_BOOT_STATE and EXPECTED_ACCESS_MARKER in current_access
    recovered_readonly = (
        boot_state in RECOVERED_BOOT_STATES
        and "UART_LIVE_SSH_ICMP_HTTP_ETH0_1G" in current_access
    )
    radio5 = state.get("radio_5_ghz", {})
    evidence_values = [
        current.get("latest_recovery_evidence"),
        radio5.get("latest_recovery_evidence"),
    ]
    recovery_evidence_path = None
    recovery_evidence_verified = False
    if recovered_readonly:
        for evidence_value in evidence_values:
            if not isinstance(evidence_value, str):
                continue
            candidate = ROOT / evidence_value
            if not candidate.is_file():
                continue
            recovery_payload = load_json(candidate)
            if (
                recovery_payload.get("schema") == "openmitrastar.post-tx7-recovery-result/v1"
                and recovery_payload.get("pass") is True
                and recovery_payload.get("result_verifier_ok") is True
                and recovery_payload.get("result_verifier_status") == "POST_TX7_RECOVERY_RESULT_VERIFIED_READONLY"
            ):
                recovery_evidence_path = candidate
                recovery_evidence_verified = True
                break
    artifacts["hardware_state"] = {
        "boot_state": boot_state,
        "current_access": current_access,
        "latest_recovery_evidence": str(recovery_evidence_path) if recovery_evidence_path else None,
        "recovery_evidence_verified": recovery_evidence_verified,
    }
    checks.append(
        Check(
            "hardware_state.post_tx7_boot_state",
            waiting_power_cycle or recovered_readonly,
            f"boot_state must be {EXPECTED_BOOT_STATE} or one of {sorted(RECOVERED_BOOT_STATES)}",
        )
    )
    checks.append(
        Check(
            "hardware_state.physical_power_cycle_required",
            waiting_power_cycle or recovery_evidence_verified,
            "current_access must require physical power-cycle, or recovered state must include verified read-only recovery evidence",
        )
    )

    lyoko_bytes = LYOKO_PACKAGE.stat().st_size
    lyoko_sha256 = sha256_file(LYOKO_PACKAGE)
    validation_text = read_text(LYOKO_VALIDATION)
    artifacts["lyoko_package"] = {
        "path": str(LYOKO_PACKAGE),
        "bytes": lyoko_bytes,
        "sha256": lyoko_sha256,
    }
    checks.append(
        Check(
            "lyoko_package.sha256.expected",
            lyoko_sha256 == expected_lyoko_sha256,
            "Router-Lyoko overlay package sha256 must match expected checkpoint",
        )
    )
    checks.append(
        Check(
            "lyoko_package.bytes.expected",
            lyoko_bytes == expected_lyoko_bytes,
            "Router-Lyoko overlay package bytes must match expected checkpoint",
        )
    )
    checks.append(
        Check(
            "lyoko_validation.documents_package",
            expected_lyoko_sha256 in validation_text and str(expected_lyoko_bytes) in validation_text,
            "VALIDATION.md must document the exact Router-Lyoko package hash and size",
        )
    )

    memory_proc = subprocess.run(
        [sys.executable, str(AELITA_MEMORY_GUARD)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    artifacts["aelita_memory_guard"] = {
        "returncode": memory_proc.returncode,
        "stdout_bytes": len(memory_proc.stdout.encode("utf-8")),
        "stderr_bytes": len(memory_proc.stderr.encode("utf-8")),
    }
    checks.append(
        Check(
            "aelita_memory_guard.returncode",
            memory_proc.returncode == 0,
            "Aelita memory/dialogue guard must pass without hardware access",
        )
    )
    try:
        memory_report = parse_first_json(memory_proc.stdout)
    except Exception as exc:  # noqa: BLE001 - report exact parse failure in JSON detail
        memory_report = {}
        checks.append(Check("aelita_memory_guard.json", False, f"Aelita memory guard JSON must parse: {exc}"))
    else:
        checks.append(Check("aelita_memory_guard.json", True, "Aelita memory guard JSON parses"))
        checks.append(
            Check(
                "aelita_memory_guard.schema",
                memory_report.get("schema") == "router-lyoko.aelita-memory-guard/v1",
                "Aelita memory guard schema must be router-lyoko.aelita-memory-guard/v1",
            )
        )
        checks.append(
            Check(
                "aelita_memory_guard.ok",
                memory_report.get("ok") is True and memory_report.get("findings_count") == 0,
                "Aelita memory guard must reject hardware overclaims, write-enabled memory and broken mission logs",
            )
        )

    evidence_bindings_proc = subprocess.run(
        [sys.executable, str(EVIDENCE_BINDINGS_GUARD)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    artifacts["evidence_bindings_guard"] = {
        "returncode": evidence_bindings_proc.returncode,
        "stdout_bytes": len(evidence_bindings_proc.stdout.encode("utf-8")),
        "stderr_bytes": len(evidence_bindings_proc.stderr.encode("utf-8")),
    }
    checks.append(
        Check(
            "evidence_bindings_guard.returncode",
            evidence_bindings_proc.returncode == 0,
            "Router-Lyoko evidence bindings guard must pass without hardware access",
        )
    )
    try:
        evidence_bindings_report = parse_first_json(evidence_bindings_proc.stdout)
    except Exception as exc:  # noqa: BLE001 - report exact parse failure in JSON detail
        evidence_bindings_report = {}
        checks.append(Check("evidence_bindings_guard.json", False, f"Evidence bindings guard JSON must parse: {exc}"))
    else:
        checks.append(Check("evidence_bindings_guard.json", True, "Evidence bindings guard JSON parses"))
        checks.append(
            Check(
                "evidence_bindings_guard.schema",
                evidence_bindings_report.get("schema") == "router-lyoko.evidence-bindings-guard/v1",
                "Evidence bindings guard schema must be router-lyoko.evidence-bindings-guard/v1",
            )
        )
        checks.append(
            Check(
                "evidence_bindings_guard.ok",
                evidence_bindings_report.get("ok") is True
                and evidence_bindings_report.get("runtime_bindings", 0) >= 8
                and evidence_bindings_report.get("static_bindings", 0) >= 5,
                "Evidence bindings guard must keep runtime proof separate from static snapshots",
            )
        )

    telemetry_proc = subprocess.run(
        [sys.executable, str(TELEMETRY_CONTRACT_GUARD)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    artifacts["telemetry_contract_guard"] = {
        "returncode": telemetry_proc.returncode,
        "stdout_bytes": len(telemetry_proc.stdout.encode("utf-8")),
        "stderr_bytes": len(telemetry_proc.stderr.encode("utf-8")),
    }
    checks.append(
        Check(
            "telemetry_contract_guard.returncode",
            telemetry_proc.returncode == 0,
            "Router-Lyoko telemetry contract guard must pass without hardware access",
        )
    )
    try:
        telemetry_report = parse_first_json(telemetry_proc.stdout)
    except Exception as exc:  # noqa: BLE001 - report exact parse failure in JSON detail
        telemetry_report = {}
        checks.append(Check("telemetry_contract_guard.json", False, f"Telemetry contract guard JSON must parse: {exc}"))
    else:
        checks.append(Check("telemetry_contract_guard.json", True, "Telemetry contract guard JSON parses"))
        checks.append(
            Check(
                "telemetry_contract_guard.schema",
                telemetry_report.get("schema") == "router-lyoko.telemetry-contract-guard/v1",
                "Telemetry contract guard schema must be router-lyoko.telemetry-contract-guard/v1",
            )
        )
        checks.append(
            Check(
                "telemetry_contract_guard.ok",
                telemetry_report.get("ok") is True
                and telemetry_report.get("runtime_fields", 0) >= 5
                and telemetry_report.get("safety_flags", 0) >= 6,
                "Telemetry contract guard must keep live freshness, static mission data and observe-only safety intact",
            )
        )

    objective_proc = subprocess.run(
        [sys.executable, str(OBJECTIVE_COVERAGE_GUARD)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    artifacts["objective_coverage_guard"] = {
        "returncode": objective_proc.returncode,
        "stdout_bytes": len(objective_proc.stdout.encode("utf-8")),
        "stderr_bytes": len(objective_proc.stderr.encode("utf-8")),
    }
    checks.append(
        Check(
            "objective_coverage_guard.returncode",
            objective_proc.returncode == 0,
            "Router-Lyoko objective coverage guard must pass without hardware access",
        )
    )
    try:
        objective_report = parse_first_json(objective_proc.stdout)
    except Exception as exc:  # noqa: BLE001 - report exact parse failure in JSON detail
        objective_report = {}
        checks.append(Check("objective_coverage_guard.json", False, f"Objective coverage guard JSON must parse: {exc}"))
    else:
        checks.append(Check("objective_coverage_guard.json", True, "Objective coverage guard JSON parses"))
        checks.append(
            Check(
                "objective_coverage_guard.schema",
                objective_report.get("schema") == "router-lyoko.objective-coverage/v1",
                "Objective coverage guard schema must be router-lyoko.objective-coverage/v1",
            )
        )
        checks.append(
            Check(
                "objective_coverage_guard.ok",
                objective_report.get("ok") is True and objective_report.get("findings_count") == 0,
                "Objective coverage guard must reject missing Router-Lyoko surfaces and hardware completion overclaims",
            )
        )
        completion = objective_report.get("completion_state") or {}
        objective_recovered_readonly = (
            completion.get("boot_state") in RECOVERED_BOOT_STATES
            and completion.get("hardware_blocked") is False
            and completion.get("next_gate") in {"phase1.bridge-ethernet-ssh", "phase2.realtek-2g-complete"}
        )
        checks.append(
            Check(
                "objective_coverage_guard.next_gate",
                completion.get("achieved") is False
                and (
                    objective_recovered_readonly
                    or (
                        completion.get("next_gate") == "phase1.current-post-tx7-recovery"
                        and completion.get("hardware_blocked") is True
                    )
                ),
                "Objective coverage guard must keep recovery as next gate until proven, then advance only to bridge/2.4 client gate",
            )
        )

    current_suite_proc = subprocess.run(
        [sys.executable, str(CURRENT_OFFLINE_SUITE), "--list"],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    artifacts["current_offline_suite_list"] = {
        "returncode": current_suite_proc.returncode,
        "stdout_bytes": len(current_suite_proc.stdout.encode("utf-8")),
        "stderr_bytes": len(current_suite_proc.stderr.encode("utf-8")),
    }
    checks.append(
        Check(
            "current_offline_suite.list.returncode",
            current_suite_proc.returncode == 0,
            "current Router-Lyoko/post-TX7 offline suite list must exit 0",
        )
    )
    checks.append(
        Check(
            "current_offline_suite.list.marker",
            "OMROUTER_LYOKO_CURRENT_OFFLINE_SUITE_LIST_PASS=1" in current_suite_proc.stdout,
            "current suite list must print OMROUTER_LYOKO_CURRENT_OFFLINE_SUITE_LIST_PASS=1",
        )
    )
    try:
        current_suite_report = parse_first_json(current_suite_proc.stdout)
    except Exception as exc:  # noqa: BLE001 - report exact parse failure in JSON detail
        current_suite_report = {}
        checks.append(Check("current_offline_suite.list.json", False, f"current suite list JSON must parse: {exc}"))
    else:
        checks.append(Check("current_offline_suite.list.json", True, "current suite list JSON parses"))
        tests = set(current_suite_report.get("tests") or [])
        excluded = set(current_suite_report.get("excluded_scope") or [])
        checks.append(
            Check(
                "current_offline_suite.list.schema",
                current_suite_report.get("schema") == "router-lyoko.current-offline-suite/v1",
                "current suite list schema must be router-lyoko.current-offline-suite/v1",
            )
        )
        checks.append(
            Check(
                "current_offline_suite.list.no_missing",
                current_suite_report.get("missing") == [],
                "current suite must have no missing test files",
            )
        )
        checks.append(
            Check(
                "current_offline_suite.list.expected_count",
                current_suite_report.get("test_count") == 44,
                "current suite must keep the expected Router-Lyoko/post-TX7 test count",
            )
        )
        checks.append(
            Check(
                "current_offline_suite.list.includes_required_boundaries",
                {
                    "tools/test_monitor_2g_live_traffic.py",
                    "tools/test_preflight_post_tx7_resume_offline.py",
                    "tools/test_package_router_lyoko_overlay.py",
                    "tools/test_post_tx7_recovery_result_verifier.py",
                    "tools/test_resume_post_tx7_result_verifier.py",
                    "tools/test_router_lyoko_evidence_bindings.py",
                    "tools/test_router_lyoko_telemetry_contract.py",
                    "tools/test_router_lyoko_objective_coverage.py",
                    "tools/test_qdrv_v89_beacon_wire_layout.py",
                    "tools/test_w2_tx9_gate.py",
                    "tools/test_w2_tx12_mgmt_trace.py",
                    "tools/test_w2_tx13_mgmt_trace.py",
                    "tools/test_rtl8192ee_mgmt_trace_budget.py",
                    "tools/test_rtl8192ee_mgmt_txbd_split.py",
                    "tools/test_rtl8192ee_mgmt_frame_fields.py",
                }.issubset(tests),
                "current suite must include recovery, resume, objective, active Quantenna, TX9 and TX13 trace guards",
            )
        )
        checks.append(
            Check(
                "current_offline_suite.list.excludes_stale_release_gates",
                "tools/test_openmitrastar_f6_certification.py" not in tests
                and "tools/test_q3_persistent_composite.py" not in tests
                and "historical Q1/Q2/Q3/W5 product artifact tests" in excluded,
                "current suite must exclude superseded release/hash gates from the post-TX7 recovery preflight",
            )
        )

    served_proc = subprocess.run(
        [
            sys.executable,
            str(SERVED_FILES_VERIFIER),
            "--manifest",
            str(LYOKO_MANIFEST),
            "--base-dir",
            str(LYOKO_WEB_ROOT),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    artifacts["served_files_verifier"] = {
        "returncode": served_proc.returncode,
        "stdout_bytes": len(served_proc.stdout.encode("utf-8")),
        "stderr_bytes": len(served_proc.stderr.encode("utf-8")),
    }
    checks.append(
        Check(
            "served_files_verifier.returncode",
            served_proc.returncode == 0,
            "served files verifier must pass against the local Router-Lyoko web root",
        )
    )
    try:
        served_report = parse_first_json(served_proc.stdout)
    except Exception as exc:  # noqa: BLE001 - report exact parse failure in JSON detail
        served_report = {}
        checks.append(Check("served_files_verifier.json", False, f"served files verifier JSON must parse: {exc}"))
    else:
        checks.append(Check("served_files_verifier.json", True, "served files verifier JSON parses"))
        checks.append(
            Check(
                "served_files_verifier.ok",
                served_report.get("ok") is True,
                "served files verifier must confirm hash parity and safe-mode LAB-console semantics",
            )
        )
        served_checks = {check.get("id") for check in served_report.get("checks", []) if isinstance(check, dict)}
        checks.append(
            Check(
                "served_files_verifier.safe_mode_tx11_boot_evidence_json",
                "served./lyoko-data/safe-mode.json.tx11_command_boot_evidence_json" in served_checks,
                "served files verifier must check the TX11 Tx11BootEvidenceJson contract in safe-mode.json",
            )
        )
        checks.append(
            Check(
                "served_files_verifier.lyoko_js_safe_mode_source",
                "served./lyoko.js.fetches_safe_mode_contract" in served_checks,
                "served files verifier must check lyoko.js fetches safe-mode.json",
            )
        )

    plan_specs = (
        (
            "recovery",
            RECOVERY_GATE,
            (),
            "OMPOSTTX7_RECOVERY_PLAN_PASS=1",
            "openmitrastar.post-tx7-recovery-gate/v1",
            "OPENMITRASTAR_POST_TX7_RECOVERY_READONLY",
        ),
        (
            "resume",
            RESUME_GATE,
            (),
            "OMPOSTTX7_RESUME_PLAN_PASS=1",
            "openmitrastar.resume-post-tx7-5g-hang/v1",
            "OPENMITRASTAR_RESUME_AFTER_TX7_HANG_READONLY",
        ),
        (
            "lyoko_reentry",
            LYOKO_REENTRY_GATE,
            (),
            "OMLYOKO_REENTRY_PLAN_PASS=1",
            "router-lyoko.reentry-live-api-gate/v1",
            "OPENMITRASTAR_LYOKO_REENTRY_READONLY",
        ),
        (
            "tx11_boot",
            TX11_BOOT_COLLECTOR,
            (),
            "OMTX11_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1",
            "openmitrastar.w2-tx11-boot-evidence-collection-plan/v1",
            "",
        ),
        (
            "tx11_2g",
            TX11_GATE,
            (),
            "OM2G_TX11_GATE_PLAN_PASS=1",
            "openmitrastar.w2-tx11-gate-plan/v1",
            "",
        ),
        (
            "tx13_boot",
            TX13_RAM_BOOT,
            (),
            "OMTX13_RAM_BOOT_PREFLIGHT_PASS=1",
            "openmitrastar.w2-tx13-ram-boot-preflight/v1",
            "OPENMITRASTAR_TX13_RAM_BOOT_ONLY_NO_FLASH",
        ),
        (
            "tx13_trace",
            TX13_TRACE_COLLECTOR,
            (),
            "OMTX13_MGMT_TRACE_COLLECTION_PLAN_PASS=1",
            "openmitrastar.w2-tx13-mgmt-trace-collection-plan/v1",
            "OPENMITRASTAR_COLLECT_TX13_MGMT_TRACE_READONLY",
        ),
        (
            "tx7_auto",
            TX7_AUTO_GATE,
            ("-PlanOnly",),
            "OM2G_TX7_AUTO_GATE_PLAN_PASS=1",
            "openmitrastar.w2-tx7-auto-client-gate/v1",
            "",
        ),
        (
            "tx7_2g",
            TX7_GATE,
            ("-PlanOnly",),
            "OM2G_CANDIDATE_GATE_PLAN_PASS=1",
            "openmitrastar.w2-candidate-live-gate-run/v1",
            "",
        ),
        (
            "tx9_2g",
            TX9_GATE,
            (),
            "OM2G_TX9_GATE_PLAN_PASS=1",
            "openmitrastar.w2-tx9-gate-plan/v1",
            "",
        ),
    )

    for name, script, args, marker, schema, ack_required in plan_specs:
        proc = powershell_plan(script, *args)
        artifacts[f"{name}_plan"] = {
            "returncode": proc.returncode,
            "stdout_bytes": len(proc.stdout.encode("utf-8")),
            "stderr_bytes": len(proc.stderr.encode("utf-8")),
        }
        checks.append(Check(f"{name}.plan.returncode", proc.returncode == 0, f"{name} plan-only command must exit 0"))
        checks.append(Check(f"{name}.plan.marker", marker in proc.stdout, f"{name} plan must print {marker}"))
        try:
            plan = parse_first_json(proc.stdout)
        except Exception as exc:  # noqa: BLE001 - report exact parse failure in JSON detail
            plan = {}
            checks.append(Check(f"{name}.plan.json", False, f"{name} plan JSON must parse: {exc}"))
        else:
            checks.append(Check(f"{name}.plan.json", True, f"{name} plan JSON parses"))
            checks.append(Check(f"{name}.plan.schema", plan.get("schema") == schema, f"{name} plan schema must be {schema}"))
            plan_only_shape = str(plan.get("mode", "")).startswith("plan")
            if name == "tx7_2g":
                plan_only_shape = "READ-ONLY" in str(plan.get("classification", ""))
            if name == "tx7_auto":
                plan_only_shape = "READ-ONLY" in str(plan.get("classification", ""))
            if name in {"tx11_boot", "tx11_2g", "tx13_boot", "tx13_trace"}:
                plan_only_shape = str(plan.get("classification", "")).startswith("PLAN-ONLY")
            if name == "tx9_2g":
                plan_only_shape = str(plan.get("classification", "")).startswith("PLAN-ONLY")
            checks.append(Check(f"{name}.plan.mode", plan_only_shape, f"{name} plan must be plan-only"))
            checks.append(Check(f"{name}.plan.mutations_false", mutation_flags_false(plan), f"{name} plan must declare no mutations"))
            if name == "tx7_auto":
                checks.append(
                    Check(
                        "tx7_auto.plan.requires_recovery_result",
                        plan.get("recovery_result_required") is True,
                        "TX7 auto gate must require a verified RecoveryResultJson",
                    )
                )
            if name == "tx11_boot":
                requirements = " ".join(str(item) for item in plan.get("execution_requires", []))
                checks.append(
                    Check(
                        "tx11_boot.plan.requires_exact_ram_boot",
                        "exact TX11 image" in requirements or "router already RAM-booted with the exact TX11 image" in requirements,
                        "TX11 boot evidence collection must require the exact RAM-booted image",
                    )
                )
                checks.append(
                    Check(
                        "tx11_boot.plan.locked_by_default",
                        plan.get("execution_requested") is False,
                        "TX11 boot evidence collection must be locked by default",
                    )
                )
            if name == "tx11_2g":
                requirements = " ".join(str(item) for item in plan.get("execution_requires", []))
                checks.append(
                    Check(
                        "tx11_2g.plan.requires_exact_boot_evidence",
                        "exact TX11 RAM-boot evidence verifier PASS" in requirements,
                        "TX11 gate plan must require verified exact RAM-boot evidence before client monitoring",
                    )
                )
                checks.append(
                    Check(
                        "tx11_2g.plan.waits_for_authorized_client",
                        "authorized" in requirements.lower() and "wait_w2_2g_client.py" in requirements,
                        "TX11 gate plan must wait for an AUTHORIZED physical client before traffic gate",
                    )
                )
                checks.append(
                    Check(
                        "tx11_2g.plan.locked_by_default",
                        plan.get("execution_requested") is False,
                        "TX11 gate plan must be locked by default",
                    )
                )
            if name in {"tx13_boot", "tx13_trace"}:
                requirements = " ".join(str(item) for item in plan.get("execution_requires", []))
                checks.append(
                    Check(
                        f"{name}.plan.ack_required",
                        ack_required in requirements,
                        f"{name} must require exact acknowledgment {ack_required}",
                    )
                )
                checks.append(
                    Check(
                        f"{name}.plan.locked_by_default",
                        plan.get("execute_requested", plan.get("execution_requested")) is False,
                        f"{name} must be locked by default",
                    )
                )
            if name == "tx7_auto":
                operations = " ".join(str(item) for item in plan.get("operations", []))
                checks.append(
                    Check(
                        "tx7_auto.plan.waits_for_authorized_client",
                        "authorized" in operations.lower() and "wait" in operations.lower(),
                        "TX7 auto gate plan must wait for an AUTHORIZED physical client before traffic gate",
                    )
                )
            if name == "tx9_2g":
                requirements = " ".join(str(item) for item in plan.get("execution_requires", []))
                checks.append(
                    Check(
                        "tx9_2g.plan.requires_exact_boot_evidence",
                        "exact TX9 RAM-boot evidence JSON" in requirements,
                        "TX9 gate plan must require exact RAM-boot evidence before client monitoring",
                    )
                )
                checks.append(
                    Check(
                        "tx9_2g.plan.locked_by_default",
                        plan.get("execution_requested") is False,
                        "TX9 gate plan must be locked by default",
                    )
                )
            if ack_required:
                checks.append(
                    Check(
                        f"{name}.plan.ack_required",
                        plan.get("ack_required") == ack_required,
                        f"{name} plan must require {ack_required}",
                    )
                )

    lyoko_source = read_text(LYOKO_REENTRY_GATE)
    checks.append(
        Check(
            "lyoko_reentry.requires_recovery_guards",
            "--require-recovery-guards" in lyoko_source,
            "Lyoko live reentry must require runtime_recovery guards",
        )
    )

    resume_source = read_text(RESUME_GATE)
    checks.append(
        Check(
            "resume.optional_lyoko_reentry_available",
            "VerifyLyokoReentry" in resume_source and "verify_router_lyoko_reentry.ps1" in resume_source,
            "Resume flow must still expose optional Router-Lyoko reentry proof",
        )
    )

    recovery_result_verifier_source = read_text(RECOVERY_RESULT_VERIFIER)
    recovery_result_verifier_test_source = read_text(RECOVERY_RESULT_VERIFIER_TEST)
    checks.append(
        Check(
            "recovery_result_verifier.no_secrets_guard",
            all(
                token in recovery_result_verifier_source
                for token in (
                    "import verify_router_lyoko_no_secrets as no_secrets",
                    "def scan_no_secrets",
                    'scan_no_secrets("ssh_stdout"',
                    'scan_no_secrets("ssh_stderr"',
                    "Findings never include the secret value",
                )
            ),
            "post-TX7 recovery result verifier must scan captured SSH evidence for concrete secrets without echoing values",
        )
    )
    checks.append(
        Check(
            "recovery_result_verifier.strict_eth0_link_guard",
            all(
                token in recovery_result_verifier_source
                for token in (
                    "ETH0_SECTION_PATTERN",
                    "def eth0_section_proves_link",
                    'operstate in {"up", "unknown"}',
                    'carrier == "1"',
                    "rx_packets",
                    "tx_packets",
                    "eth0_ok must match stdout eth0 section: operstate up/unknown, carrier 1, numeric rx/tx packets",
                )
            ),
            "post-TX7 recovery result verifier must require eth0 up/unknown with carrier and numeric counters, not only markers",
        )
    )
    checks.append(
        Check(
            "recovery_result_verifier_test.no_secret_echo_case",
            all(
                token in recovery_result_verifier_test_source
                for token in (
                    "test_rejects_secret_bearing_stdout_without_echoing_secret",
                    "super-secret-router-key",
                    "assertNotIn(secret_value",
                    "ssh_stdout.no_secrets",
                )
            ),
            "post-TX7 recovery result tests must reject secret-bearing stdout without echoing the value",
        )
    )
    checks.append(
        Check(
            "recovery_result_verifier_test.strict_eth0_link_cases",
            all(
                token in recovery_result_verifier_test_source
                for token in (
                    "test_rejects_eth0_markers_without_proven_link",
                    "test_rejects_eth0_markers_with_malformed_counters",
                    "eth0_ok.matches_stdout",
                )
            ),
            "post-TX7 recovery result tests must reject eth0 marker-only or malformed-counter evidence",
        )
    )
    resume_result_verifier_source = read_text(RESUME_RESULT_VERIFIER)
    resume_result_verifier_test_source = read_text(RESUME_RESULT_VERIFIER_TEST)
    checks.append(
        Check(
            "resume_result_verifier.no_secrets_guard",
            all(
                token in resume_result_verifier_source
                for token in (
                    "import verify_router_lyoko_no_secrets as no_secrets",
                    "def scan_no_secrets",
                    '"recovery_stdout"',
                    '"tx11_2g_plan_stdout"',
                    "Findings never include the secret value",
                )
            ),
            "resume-post-TX7 result verifier must scan top-level child evidence for concrete secrets without echoing values",
        )
    )
    checks.append(
        Check(
            "resume_result_verifier_test.no_secret_echo_case",
            all(
                token in resume_result_verifier_test_source
                for token in (
                    "test_rejects_secret_bearing_top_level_stdout_without_echoing_secret",
                    "resume-secret-router-key",
                    "assertNotIn(secret_value",
                    "tx11_2g_plan_stdout.no_secrets",
                )
            ),
            "resume-post-TX7 result tests must reject secret-bearing top-level stdout without echoing the value",
        )
    )

    for script in (RECOVERY_GATE, RESUME_GATE, LYOKO_REENTRY_GATE, TX7_GATE, TX7_AUTO_GATE, TX7_CLIENT_WAITER, TX11_GATE, TX11_BOOT_COLLECTOR, TX13_RAM_BOOT, TX13_TRACE_COLLECTOR, TX9_GATE, TX9_BOOT_VERIFIER):
        ok, hits = source_has_no_forbidden_tokens(script)
        checks.append(
            Check(
                f"source.{script.name}.no_forbidden_mutation_tokens",
                ok,
                f"{script.name} must not contain forbidden tokens: {', '.join(hits) if hits else 'none'}",
            )
        )

    return render_report(checks, artifacts)


def render_report(checks: list[Check], artifacts: dict[str, Any]) -> dict[str, Any]:
    ok = all(check.ok for check in checks)
    hardware_state = artifacts.get("hardware_state") if isinstance(artifacts.get("hardware_state"), dict) else {}
    recovered = hardware_state.get("recovery_evidence_verified") is True
    return {
        "schema": "openmitrastar.post-tx7-offline-preflight/v1",
        "classification": "READONLY-OFFLINE-PREFLIGHT-NO-HARDWARE",
        "ok": ok,
        "checks": [asdict(check) for check in checks],
        "artifacts": artifacts,
        "next_gate": (
            "tx13-lossless-mgmt-trace-exact-ram-boot-and-capture"
            if ok and recovered
            else "physical-power-cycle-then-ack-gated-readonly-recovery"
            if ok
            else "fix-offline-preflight-failures"
        ),
        "mutations": {
            "uart_opened": False,
            "ssh_command": False,
            "reboot": False,
            "network_reconfigure": False,
            "bootenv": False,
            "mtd": False,
            "flash": False,
        },
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Offline preflight for post-TX7 recovery/resume without touching hardware.")
    parser.add_argument("--expected-lyoko-sha256", default=EXPECTED_LYOKO_SHA256)
    parser.add_argument("--expected-lyoko-bytes", type=int, default=EXPECTED_LYOKO_BYTES)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report = build_report(args.expected_lyoko_sha256.lower(), args.expected_lyoko_bytes)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if report["ok"]:
        print("OMPOSTTX7_OFFLINE_PREFLIGHT_PASS=1")
        return 0
    print("OMPOSTTX7_OFFLINE_PREFLIGHT_PASS=0")
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
