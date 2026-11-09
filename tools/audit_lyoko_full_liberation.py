#!/usr/bin/env python3
"""Audit the evidence required by the Lyoko Full Liberation objective."""

from __future__ import annotations

import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess


ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def latest(pattern: str) -> Path:
    paths = sorted(ROOT.glob(pattern), key=lambda item: item.stat().st_mtime)
    if not paths:
        raise SystemExit(f"missing evidence: {pattern}")
    return paths[-1]


def requirement(name: str, status: str, evidence: list[str], remaining: str) -> dict:
    return {"name": name, "status": status, "evidence": evidence, "remaining": remaining}


def valid_recorded_uart_binding(record: dict, guard_sha256: str) -> bool:
    """Historical identity/RX evidence only; never authorizes another port open."""
    binding = record.get("binding") or {}
    return (
        record.get("schema") == "openmitrastar.f319-uart-readiness/v1"
        and record.get("status") == "PASS_IDENTITY_AND_RX_BINDING_ONLY"
        and record.get("host") == "192.168.1.90"
        and record.get("expected_version") == "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device"
        and record.get("guard_source_sha256") == guard_sha256
        and record.get("pinned_ssh_verified") is True
        and record.get("exclusive_guard_acquired") is True
        and record.get("cleanup") == "OWN_GUARD_RELEASED"
        and binding.get("RouterHost") == record["host"]
        and binding.get("ExpectedVersion") == record["expected_version"]
        and binding.get("Port") == "COM3"
        and binding.get("PnpDeviceId") == r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000"
        and binding.get("NonceObserved") is True
    )


def verify_recorded_bootbase_rehearsal(path: Path | None) -> dict:
    """Reuse the production, file-only proof reader; never acquire hardware."""
    if path is None:
        return {"verified": False, "error": "NOT_RUN"}
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    command = (
        "$ErrorActionPreference='Stop'\n"
        f". {quote(ROOT / 'tools/f319_recovery_guard.ps1')}\n"
        f"Get-F319VerifiedRecoveryRehearsal -ResultPath {quote(path.resolve())} | ConvertTo-Json -Compress\n"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand",
             base64.b64encode(command.encode("utf-16le")).decode("ascii")],
            stdin=subprocess.DEVNULL, capture_output=True, text=True, timeout=45,
        )
        if result.returncode != 0:
            return {"verified": False, "error": "PRODUCTION_PROOF_READER_REJECTED"}
        proof = json.loads(result.stdout.lstrip("\ufeff").strip())
        if (Path(proof.get("ResultPath", "")).resolve() != path.resolve()
                or proof.get("F314Sha256") != "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"):
            return {"verified": False, "error": "PROOF_IDENTITY_MISMATCH"}
        return {"verified": True, "error": None, "scope": proof.get("Scope")}
    except (OSError, subprocess.TimeoutExpired, ValueError, TypeError, AttributeError):
        return {"verified": False, "error": "PROOF_READER_UNAVAILABLE_OR_INVALID_OUTPUT"}


def verify_recorded_f319_runtime(directory: Path | None) -> dict:
    """Classify a historical result and its correlated evidence, never live hardware."""
    if directory is None:
        return {"verified": False, "status": "NOT_RUN"}
    names = ("result.json", "plan.json", "probe.stdout.log", "uart/capture-status.json",
             "uart/uart.raw.bin", "uart/uart.log")
    paths = [directory / name for name in names]
    if not all(path.is_file() for path in paths):
        return {"verified": False, "status": "INCOMPLETE_NOT_ACCEPTED", "directory": str(directory)}
    try:
        result, plan, capture = load(paths[0]), load(paths[1]), load(paths[3])
        required = ("claim", "mapping", "reads_zero", "writes_zero", "provider_disabled",
                    "mtd_table_unchanged", "fatal_count_unchanged", "module_unloaded",
                    "uart_no_fatal", "uart_complete_correlated")
        sha = "e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9"
        module_sha = "79436442b62110351fba44262a05ae0f2a9ffc87b36fabe74cc651112e431317"
        valid = (
            result.get("schema") == "openmitrastar.f319-spi-owner-runtime/v1"
            and result.get("status") == "PASS"
            and result.get("firmware") == "lyoko-foundation-6.8.3-f319-spi-owner-claim-device"
            and result.get("firmware_sha256") == sha and result.get("module_sha256") == module_sha
            and result.get("flash") is False and result.get("mtd_writes") is False
            and all(result.get("checks", {}).get(key) is True for key in required)
            and type(result.get("uart_capture_exit_code")) is int and result["uart_capture_exit_code"] == 0
            and plan.get("mode") == "execute" and plan.get("local_preflight_pass") is True
            and plan.get("firmware_sha256") == sha and plan.get("module_sha256") == module_sha
            and capture.get("schema") == "openmitrastar.uart-capture-status/v1"
            and capture.get("state") == "complete" and capture.get("ready") is True
            and capture.get("rx_only") is True and capture.get("dtr") is False and capture.get("rts") is False
            and capture.get("gaps") == 0 and capture.get("error") is None
            and capture.get("current_port") == "COM3"
            and capture.get("pinned_pnp_device_id") == r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000"
            and type(result.get("uart_capture_pid")) is int and result["uart_capture_pid"] > 0
            and capture.get("capture_pid") == result["uart_capture_pid"]
            and capture.get("run_id") == result.get("uart_capture_run_id")
            and isinstance(capture.get("run_id"), str) and bool(capture["run_id"])
        )
        raw = paths[4].read_bytes()
        text = paths[5].read_bytes().decode("ascii")
        stdout = paths[2].read_text(encoding="ascii")
        valid = valid and bool(raw) and len(raw) == capture.get("bytes")
        valid = valid and raw.decode("ascii", errors="replace").replace("\ufffd", "?") == text
        run = re.escape(str(capture.get("run_id")))
        begin = list(re.finditer(r"(?m)^" + run + r"_BEGIN\r?$", text))
        end = list(re.finditer(r"(?m)^" + run + r"_END\r?$", text))
        valid = valid and len(begin) == len(end) == 1 and begin[0].start() < end[0].start()
        expected = {"controller_resource_claimed": "Y", "controller_mapped": "Y",
                    "controller_read_count": "0", "controller_write_count": "0",
                    "transaction_provider_ready": "N", "MODULE_UNLOADED": "1",
                    "FATAL_BEFORE": "0", "FATAL_AFTER": "0"}
        for key, value in expected.items():
            valid = valid and re.findall(r"(?m)^" + key + r"=([^\r\n]+)\r?$", stdout) == [value]
        before = re.findall(r"(?m)^MTD_TABLE_HASH_BEFORE=([0-9a-f]{64})\r?$", stdout)
        after = re.findall(r"(?m)^MTD_TABLE_HASH_AFTER=([0-9a-f]{64})\r?$", stdout)
        valid = valid and len(before) == 1 and before == after
        valid = valid and len(re.findall(r"(?m)^OMF319_SPI_OWNER_PASS\r?$", stdout)) == 1
        valid = valid and not re.search(r"kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|Machine Check", text, re.I)
        return {"verified": bool(valid), "status": "PHYSICAL_PASS_RECORDED" if valid else "REJECTED",
                "directory": str(directory), "observed_at": result.get("generated_at"),
                "evidence": [{"path": str(path), "sha256": digest(path)} for path in paths],
                "scope": "Recorded claim/map/unload and complete capture; not current liveness or SPI transaction-provider proof"}
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        return {"verified": False, "status": "INVALID_RECORD", "directory": str(directory)}


def main() -> int:
    manifests = {
        version: load(DEVICE / f"{version}-device-bound/manifest.json")
        for version in ("f314", "f315", "f316", "f317", "f319")
    }
    f318_path = ROOT / "outputs/kernel-port/f318-store-transaction-core-20260905/manifest.json"
    f319_module_path = ROOT / "outputs/kernel-port/f319-spi-owner-probe-20260905/manifest.json"
    f318 = load(f318_path)
    f319_module = load(f319_module_path)
    live_path = latest("outputs/handoff-live/f314-full-liberation-baseline-*/status.json")
    live = load(live_path)
    f319_plan_path = latest("outputs/preflight/f319-spi-owner-claim-*/plan.json")
    f319_plan = load(f319_plan_path)
    guard_path = latest("outputs/preflight/f319-offline-guards-*/result.json")
    guard = load(guard_path)
    guard_current = (guard.get("status") == "PASS" and guard.get("hardware_actions") is False
                     and all(digest(ROOT / "tools" / name) == value for name, value in guard["sources"].items()))
    uart_paths = sorted(ROOT.glob("outputs/preflight/f319-uart-readiness-*/result.json"))
    uart_path = uart_paths[-1] if uart_paths else None
    uart = load(uart_path) if uart_path else {}
    uart_recorded = valid_recorded_uart_binding(uart, digest(ROOT / "tools/f319_uart_guard.ps1"))
    recovery_path = ROOT / "outputs/recovery/mtd3-current-evidence-20260901/result.json"
    recovery = load(recovery_path)
    rehearsal_paths = list(ROOT.glob("outputs/recovery/f319-f314-bootbase-rehearsal-*/result.json"))
    rehearsal_paths += list(ROOT.glob("outputs/recovery/f319-f314-rehearsal-detached-*/run/result.json"))
    rehearsal_path = max(rehearsal_paths, key=lambda path: path.stat().st_mtime) if rehearsal_paths else None
    rehearsal = load(rehearsal_path) if rehearsal_path else {}
    rehearsal_verification = verify_recorded_bootbase_rehearsal(rehearsal_path)
    runtime_plans = [path for path in ROOT.glob("outputs/preflight/f319-runtime-probe-*/plan.json")
                     if load(path).get("mode") == "execute"]
    runtime_directory = max(runtime_plans, key=lambda path: path.stat().st_mtime).parent if runtime_plans else None
    runtime_record = verify_recorded_f319_runtime(runtime_directory)
    runtime_pass = runtime_record["verified"]
    recovery_remaining = (
        "Verify a no-SSH Bootbase/F314 recovery route before flash. The preserved mtd3 evidence "
        "records a rootfs mount failure, not independent management recovery. Do not modify mtd3 "
        "or use the legacy helper that writes bootenv. Reacquire the live guard and a fresh "
        "authenticated console binding at execution; the recorded RX binding is not a lease."
    )
    if rehearsal_verification["verified"]:
        recovery_remaining = (
            "Exact F314 self-restoration through Bootbase is proven by verified historical evidence. "
            "Recheck current F314 SSH, adapter availability, live exclusive guard and authenticated "
            "console binding before F319 promotion. This is not current connectivity, hard CPU-lockup "
            "or partial-erase recovery proof; mtd3 independent rescue remains unproven."
        )
    elif rehearsal.get("error") == "UART port COM3 is not present":
        recovery_remaining = "Latest rehearsal stopped before UART access because the pinned FTDI was absent. Reconnect the adapter to the HGW. " + recovery_remaining

    requirements = [
        requirement(
            "F314 persistent baseline",
            "PASS" if live.get("status") == "PASS" and all(live.get("checks", {}).values()) else "FAIL",
            [str(live_path.relative_to(ROOT)), "docs/OPENMITRASTAR_F314_CURRENT_STATE.md"],
            "Keep as rollback baseline until a successor passes every physical gate.",
        ),
        requirement(
            "F314 exact Bootbase recovery",
            "PHYSICAL_PASS_RECORDED" if rehearsal_verification["verified"] else "NOT_VERIFIED",
            [str(rehearsal_path.relative_to(ROOT))] if rehearsal_path else [],
            recovery_remaining,
        ),
        requirement(
            "F315 QT4 shadow acquisition",
            "OFFLINE_PASS_PHYSICAL_NOT_RUN",
            [str((DEVICE / "f315-device-bound/manifest.json")), "outputs/kernel-port/f315-radar-shadow-20260905/manifest.json"],
            manifests["f315"]["physical_validation"]["required"],
        ),
        requirement(
            "F316 active DFS/CAC",
            "OFFLINE_PASS_PHYSICAL_NOT_RUN",
            [str((DEVICE / "f316-device-bound/manifest.json")), "outputs/kernel-port/f316-radar-native-20260905/manifest.json"],
            manifests["f316"]["physical_validation"]["required"],
        ),
        requirement(
            "F317 autonomous optimization",
            "OFFLINE_PASS_OBSERVE_ONLY",
            [str((DEVICE / "f317-device-bound/manifest.json")), "docs/OPENMITRASTAR_F317_CANDIDATE.md"],
            "Requires F316 physical acceptance, then observer CPU/RAM/liveness proof before automatic apply.",
        ),
        requirement(
            "F317 persistent journal",
            "PARTIAL",
            ["work/userland/lyoko-radiod/src/journal.c", "work/userland/lyoko-radiod/src/file_backend.c", str(f318_path.relative_to(ROOT))],
            "F318 is proven offline; an exact per-block SPI provider and physical power-loss gate are still missing.",
        ),
        requirement(
            "SPI controller ownership",
            "PHYSICAL_PASS_RECORDED" if runtime_pass else ("PHYSICAL_ATTEMPT_NOT_ACCEPTED" if runtime_directory else "OFFLINE_PASS_PHYSICAL_NOT_RUN"),
            [str(f319_module_path.relative_to(ROOT)), str(f319_plan_path.relative_to(ROOT)), "docs/OPENMITRASTAR_F319_SPI_OWNER_PROBE.md"] + ([str(runtime_directory.relative_to(ROOT))] if runtime_directory else []),
            ("Claim/map/unload and zero accesses accepted. Transaction provider remains disabled; any bounded SPI read/write is a separate versioned gate."
             if runtime_pass else "Authorization for exact F319 already received. A complete accepted runtime record is still required. " + recovery_remaining),
        ),
        requirement(
            "F319 host ownership and capture gates",
            ("PHYSICAL_PASS_RECORDED" if runtime_pass else ("OFFLINE_PASS_RX_BINDING_RECORDED_CAPTURE_NOT_RUN" if uart_recorded else "OFFLINE_PASS_PHYSICAL_NOT_RUN")) if guard_current else "STALE_OFFLINE_EVIDENCE",
            [str(guard_path.relative_to(ROOT)), "docs/OPENMITRASTAR_F319_SPI_OWNER_PROBE.md"] + ([str(uart_path.relative_to(ROOT))] if uart_path else []),
            ("Complete correlated F319 capture is recorded; its released lease never authorizes another hardware action." if runtime_pass
             else "Recorded RX binding is not ongoing ownership. Bootbase recovery has its own evidence gate; complete accepted F319 capture remains required."),
        ),
        requirement(
            "Portable multi-router platform",
            "PARTIAL",
            ["work/platform/board-profile/schema.json", "work/platform/board-profile/hgw500bna-qcv2.json", "work/userland/lyoko-radiod/README.md"],
            "Add and validate profiles/adapters for each additional physical router; only HGW-500BNA-QCv2 exists now.",
        ),
        requirement(
            "Final physical validation",
            "NOT_RUN",
            ["docs/OPENMITRASTAR_F315_CANDIDATE.md", "docs/OPENMITRASTAR_F316_CANDIDATE.md", "docs/OPENMITRASTAR_F317_CANDIDATE.md"],
            "Sequentially prove F315, F316 and F317/F318 on mtd4 with rollback, dual-radio traffic, DFS and persistence evidence.",
        ),
    ]

    checks = {
        "f314_live_pass": requirements[0]["status"] == "PASS",
        "f315_hash_present": len(manifests["f315"]["artifacts"]["webformat"]["sha256"]) == 64,
        "f316_hash_present": len(manifests["f316"]["artifacts"]["webformat"]["sha256"]) == 64,
        "f317_observe_only": manifests["f317"]["radiod_observer"]["mode"] == "observe" and manifests["f317"]["radiod_observer"]["automatic_apply"] is False,
        "f318_offline_pass": f318["status"] == "PASS" and f318["authority"]["persistent_writes_enabled"] is False,
        "f319_claim_only": f319_module["status"] == "PASS" and f319_module["contract"]["mmio_reads"] == 0 and f319_module["contract"]["mmio_writes"] == 0,
        "f319_plan_offline": f319_plan["status"] == "PASS_OFFLINE_PLAN" and f319_plan["hardware_actions_performed"] is False,
        "f319_guard_behavior_current": guard_current,
    }
    overall = "IN_PROGRESS" if all(checks.values()) else "FAILED_PRECONDITION"
    report = {
        "schema": "openmitrastar.lyoko-full-liberation-audit/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "overall_status": overall,
        "installed_firmware": "F319" if runtime_pass else ("UNCONFIRMED_AFTER_F319_ATTEMPT" if runtime_directory else "F314"),
        "installed_firmware_scope": "last accepted runtime record only; current state and later rollbacks are not queried by this offline audit",
        "f319_runtime_record": runtime_record,
        "uart_binding_record": {
            "verified_record": uart_recorded,
            "evidence": str(uart_path.relative_to(ROOT)) if uart_path else None,
            "sha256": digest(uart_path) if uart_path else None,
            "observed_at": uart.get("finished_utc"),
            "scope": "historical identity/RX observation only; guard released; no ongoing ownership or execution authority",
        },
        "independent_safety_recovery_record": {
            "evidence": str(recovery_path.relative_to(ROOT)),
            "status": recovery["status"],
            "recovery_ready": recovery["recovery_ready"],
            "scope": "historical mtd3 boot evidence; not a current physical retest",
        },
        "latest_bootbase_rehearsal_attempt": {
            "evidence": str(rehearsal_path.relative_to(ROOT)) if rehearsal_path else None,
            "status": rehearsal.get("status", "NOT_RUN"),
            "phase": rehearsal.get("phase"),
            "error": rehearsal.get("error"),
            "observed_at": rehearsal.get("finished_utc"),
            "proof_verification": rehearsal_verification,
            "scope": "last recorded attempt only; availability requires fresh identity/lease and the promoter's verified recovery proof",
        },
        "checks": checks,
        "requirements": requirements,
        "next_gate": {
            "name": "Next separately authorized Lyoko gate" if runtime_pass else "F319 SPI controller ownership physical probe",
            "requires_explicit_authorization": True,
            "authorization_status": "F319_COMPLETE_NO_NEW_CANDIDATE_AUTHORIZED" if runtime_pass else "GRANTED_FOR_EXACT_F319_HASH",
            "blocking_physical_requirement": ("Select the next versioned experiment; do not repeat accepted F319 automatically." if runtime_pass else
                                              recovery_remaining if uart_recorded else "HGW UART connection and release from Askey not yet confirmed; " + recovery_remaining),
            "candidate_sha256": None if runtime_pass else manifests["f319"]["artifacts"]["webformat"]["sha256"],
            "required_ack": None if runtime_pass else "OPENMITRASTAR_F319_MTD4_E33D8511",
            "promotion_runner": None if runtime_pass else "tools/promote_f319_mtd4_direct.ps1",
            "runtime_probe": "tools/run_f319_spi_owner_probe.ps1",
        },
    }
    output = ROOT / "outputs/audit/lyoko-full-liberation-20260905.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if overall == "IN_PROGRESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
