#!/usr/bin/env python3
"""Fail-closed one-shot writer for the exact Q1 candidate and physical mtd4.

Default mode is a local dry-run. Execute mode is deliberately hard-pinned to
HGW-500BNA-QCv2/A2, candidate bd473ef7..., physical linux_live at 0x7e0000,
and rollback linux_safety at 0x040000. It consumes existing read-only current
flash and exact-image RAM-equivalence attestations; it never creates or
weakens those prerequisites.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time
import zlib

from openmitrastar_flash_backup_preflight import validate_current_read_attestation


ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "work/mission-state/F2_Q1_FULL_FLASH_CANDIDATE_INPUT_CONTRACT.json"
CANDIDATE_DIR = ROOT / "work/mission-state/f2-q1-full-flash-candidate"
CANDIDATE = CANDIDATE_DIR / "openmitrastar-linux510-q1-full-webformat.bin"
MANIFEST = CANDIDATE_DIR / "manifest.json"
CURRENT_READ = CANDIDATE_DIR / "current-flash-read.json"
RAM_EQUIVALENCE = CANDIDATE_DIR / "ram-equivalence.json"
READINESS_JSON = ROOT / "work/mission-state/F2_Q1_FULL_FLASH_CANDIDATE_READINESS.json"
READINESS_MD = ROOT / "work/mission-state/F2_Q1_FULL_FLASH_CANDIDATE_READINESS.md"
POWERSHELL_BACKEND = ROOT / "tools/q1_mtd4_bootbase_flash.ps1"
READINESS_TOOL = ROOT / "tools/openmitrastar_flash_candidate_readiness.py"
TFTP_TOOL = ROOT / "tools/tftp_serve_once.py"

EXPECTED_SHA256 = "bd473ef7f7238a5f9488e4739308615355c7e86526c5c867e16d3a232908c306"
EXPECTED_BYTES = 3_647_602
PHYSICAL_FLASH_BYTES = 0x01000000
TARGET_OFFSET = 0x007E0000
TARGET_BYTES = 0x007A0000
ROLLBACK_OFFSET = 0x00040000
ROLLBACK_BYTES = 0x007A0000
ROLLBACK_SHA256 = "f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1"
ROLLBACK_LOG = ROOT / "outputs/uart-live/zhal-atgo-oem.log"
ROLLBACK_LOG_SHA256 = "ef928a82ffe27f9a8b982d8a361dc490b13c3639267cc941ba9571ecd1cb88c8"
ACK = "OPENMITRASTAR_Q1_MTD4_FLASH_BD473EF7"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def crc32(path: Path) -> int:
    value = 0
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            value = zlib.crc32(block, value)
    return value & 0xFFFFFFFF


def parse_time(value: object, label: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{label} has no timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError(f"{label} timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def require_fresh(value: object, label: str, max_age_minutes: int, now: datetime) -> float:
    captured = parse_time(value, label)
    age = (now - captured).total_seconds() / 60.0
    if age < -5 or age > max_age_minutes:
        raise ValueError(f"{label} age invalid: {age:.1f} minutes")
    return age


def resolve_backup_partitions(attestation: dict[str, object]) -> tuple[Path, Path]:
    manifest_value = attestation.get("source_backup_manifest")
    if not isinstance(manifest_value, str):
        raise ValueError("current-read source backup manifest missing")
    backup_manifest = Path(manifest_value)
    if not backup_manifest.is_absolute():
        backup_manifest = ROOT / backup_manifest
    backup_manifest = backup_manifest.resolve()
    if not backup_manifest.is_file():
        raise ValueError(f"current-read source backup manifest missing: {backup_manifest}")
    expected_manifest_sha = attestation.get("source_backup_manifest_sha256")
    if sha256(backup_manifest) != expected_manifest_sha:
        raise ValueError("current-read source backup manifest hash drift")
    backup = json.loads(backup_manifest.read_text(encoding="utf-8"))
    parts = {item["name"]: item for item in backup.get("partitions", [])}
    result: list[Path] = []
    for name, expected_size in (("linux_safety", ROLLBACK_BYTES), ("linux_live", TARGET_BYTES)):
        item = parts.get(name)
        if not isinstance(item, dict):
            raise ValueError(f"fresh backup lacks {name}")
        path = backup_manifest.parent / str(item.get("file", ""))
        if not path.is_file() or path.stat().st_size != expected_size:
            raise ValueError(f"fresh backup artifact invalid: {name}")
        if sha256(path) != item.get("sha256"):
            raise ValueError(f"fresh backup artifact hash drift: {name}")
        if attestation.get("partition_sha256", {}).get(name) != item.get("sha256"):
            raise ValueError(f"current-read does not bind fresh {name}")
        result.append(path)
    if sha256(result[0]) != ROLLBACK_SHA256:
        raise ValueError("fresh linux_safety differs from pinned rollback")
    return result[0], result[1]


def full_slot_bytes(candidate: bytes) -> bytes:
    if len(candidate) > TARGET_BYTES:
        raise ValueError("candidate exceeds linux_live")
    return candidate + b"\xff" * (TARGET_BYTES - len(candidate))


def validate_local_inputs(max_age_minutes: int) -> dict[str, object]:
    for path in (CONTRACT, CANDIDATE, MANIFEST, CURRENT_READ, RAM_EQUIVALENCE,
                 POWERSHELL_BACKEND, READINESS_TOOL, TFTP_TOOL):
        if not path.is_file():
            raise ValueError(f"missing required input: {path}")
    candidate_data = CANDIDATE.read_bytes()
    if len(candidate_data) != EXPECTED_BYTES or hashlib.sha256(candidate_data).hexdigest() != EXPECTED_SHA256:
        raise ValueError("exact Q1 candidate hash/size mismatch")
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("candidate_eligible") is not True:
        raise ValueError("promoted candidate manifest is not eligible")
    if manifest.get("target") != {
        "model": "HGW-500BNA-QCv2", "hardware_revision": "A2", "slot": "linux_live"
    }:
        raise ValueError("candidate target identity mismatch")
    artifact = manifest.get("artifact", {})
    if artifact.get("sha256") != EXPECTED_SHA256 or artifact.get("size") != EXPECTED_BYTES:
        raise ValueError("candidate manifest artifact mismatch")
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    device = contract.get("device", {})
    if device != {
        "model": "HGW-500BNA-QCv2", "hardware_revision": "A2",
        "target_slot": "linux_live", "rollback_slot": "linux_safety",
        "slot_size": TARGET_BYTES,
    }:
        raise ValueError("Q1 physical target contract drift")
    current = json.loads(CURRENT_READ.read_text(encoding="utf-8"))
    equivalence = json.loads(RAM_EQUIVALENCE.read_text(encoding="utf-8"))
    now = datetime.now(timezone.utc)
    current_age = require_fresh(current.get("captured_at"), "current-flash-read", max_age_minutes, now)
    equivalence_age = require_fresh(
        equivalence.get("generated_at"), "ram-equivalence", max_age_minutes, now
    )
    if equivalence.get("schema") != "openmitrastar.ram-equivalence/v1":
        raise ValueError("RAM equivalence schema mismatch")
    if equivalence.get("status") != "PASS" or equivalence.get("candidate_sha256") != EXPECTED_SHA256:
        raise ValueError("RAM equivalence does not PASS the exact candidate")
    if equivalence.get("flash_actions") is not False or equivalence.get("secret_values_recorded") is not False:
        raise ValueError("RAM equivalence safety contract mismatch")
    required_checks = contract["ram_equivalence_contract"]["required_checks"]
    failed = [name for name in required_checks if equivalence.get("checks", {}).get(name) != "PASS"]
    if failed:
        raise ValueError(f"RAM equivalence required checks failed: {failed}")
    evidence = equivalence.get("evidence", [])
    if not evidence:
        raise ValueError("RAM equivalence has no hash-bound evidence")
    for item in evidence:
        path = Path(str(item.get("path", "")))
        if not path.is_absolute():
            path = ROOT / path
        if not path.is_file() or sha256(path) != item.get("sha256"):
            raise ValueError(f"RAM equivalence evidence drift: {path}")
    baseline_path = ROOT / contract["cached_f2"]["baseline"]["path"]
    baseline = json.loads(baseline_path.read_text(encoding="utf-8"))
    current_ok, current_detail = validate_current_read_attestation(
        CURRENT_READ, baseline, "linux_live",
        contract.get("current_unit_recovery_contract"),
    )
    if not current_ok:
        raise ValueError(f"current-unit attestation invalid: {current_detail}")
    if not ROLLBACK_LOG.is_file() or sha256(ROLLBACK_LOG) != ROLLBACK_LOG_SHA256:
        raise ValueError("manual UART rollback evidence hash drift")
    safety, live = resolve_backup_partitions(current)
    padded = full_slot_bytes(candidate_data)
    return {
        "candidate_sha256": EXPECTED_SHA256,
        "candidate_bytes": EXPECTED_BYTES,
        "candidate_crc32": f"{zlib.crc32(candidate_data) & 0xFFFFFFFF:08x}",
        "target_offset": TARGET_OFFSET,
        "target_bytes": TARGET_BYTES,
        "rollback_offset": ROLLBACK_OFFSET,
        "rollback_bytes": ROLLBACK_BYTES,
        "rollback_sha256": ROLLBACK_SHA256,
        "rollback_crc32": f"{crc32(safety):08x}",
        "current_live_sha256": sha256(live),
        "current_live_crc32": f"{crc32(live):08x}",
        "expected_full_slot_sha256": hashlib.sha256(padded).hexdigest(),
        "expected_full_slot_crc32": f"{zlib.crc32(padded) & 0xFFFFFFFF:08x}",
        "current_read_age_minutes": round(current_age, 2),
        "ram_equivalence_age_minutes": round(equivalence_age, 2),
        "attested_bootcmd": current.get("bootcmd"),
        "attested_bootselect": current.get("bootselect"),
        "rollback_selected_before_write": False,
        "manual_uart_rollback_proven": True,
        "manual_uart_rollback_log_sha256": ROLLBACK_LOG_SHA256,
        "environment_divergence_documented": True,
        "environment_write": False,
    }


def run_readiness() -> dict[str, object]:
    proc = subprocess.run(
        [sys.executable, str(READINESS_TOOL), "--workspace", str(ROOT),
         "--contract", str(CONTRACT), "--json-out", str(READINESS_JSON),
         "--md-out", str(READINESS_MD), "--strict"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if proc.returncode != 0:
        raise ValueError(f"strict Q1 readiness failed: {proc.stdout.strip()} {proc.stderr.strip()}")
    report = json.loads(READINESS_JSON.read_text(encoding="utf-8"))
    if report.get("candidate_eligible") is not True or report.get("candidate_sha256") != EXPECTED_SHA256:
        raise ValueError("strict readiness did not approve the exact candidate")
    blocking = [gate for gate in report.get("gates", []) if gate.get("blocking")]
    if not blocking or any(gate.get("passed") is not True for gate in blocking):
        raise ValueError("not every blocking readiness gate passed")
    return report


def start_tftp(timeout: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [sys.executable, str(TFTP_TOOL), "--root", str(CANDIDATE_DIR),
         "--bind", "0.0.0.0", "--port", "69", "--timeout", str(timeout), "--once"],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def execute_backend(args: argparse.Namespace, preflight: dict[str, object]) -> dict[str, object]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = CANDIDATE_DIR / f"flash-one-shot-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    transcript = evidence_dir / "bootbase-flash-uart.log"
    tftp = start_tftp(args.timeout)
    try:
        time.sleep(0.7)
        command = [
            "pwsh.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
            str(POWERSHELL_BACKEND), "-Execute", "-Ack", ACK,
            "-Candidate", str(CANDIDATE), "-ExpectedSha256", EXPECTED_SHA256,
            "-ExpectedBytes", str(EXPECTED_BYTES), "-Port", args.port,
            "-ServerIp", args.server_ip, "-ClientIp", args.client_ip,
            "-HostAddress", args.host, "-Transcript", str(transcript),
            "-RollbackSha256", str(preflight["rollback_sha256"]),
            "-RollbackCrc32", str(preflight["rollback_crc32"]),
            "-CurrentLiveCrc32", str(preflight["current_live_crc32"]),
            "-ExpectedCandidateCrc32", str(preflight["candidate_crc32"]),
            "-ExpectedFullSlotSha256", str(preflight["expected_full_slot_sha256"]),
            "-ExpectedFullSlotCrc32", str(preflight["expected_full_slot_crc32"]),
            "-TimeoutSeconds", str(args.timeout),
        ]
        if args.skip_reboot:
            command.append("-SkipReboot")
        proc = subprocess.run(
            command, cwd=ROOT, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=args.timeout + 300, check=False,
        )
        backend_log = evidence_dir / "backend.log"
        backend_log.write_text(proc.stdout, encoding="utf-8")
        if proc.returncode != 0 or "OMQ1_MTD4_FLASH_AND_READBACK_PASS=1" not in proc.stdout:
            raise RuntimeError(f"Q1 flash backend failed; evidence={evidence_dir}")
        tftp_output = ""
        if tftp.stdout:
            try:
                tftp_output = tftp.stdout.read()
            except OSError:
                pass
        (evidence_dir / "tftp.log").write_text(tftp_output, encoding="utf-8")
        evidence = []
        for path in (transcript, backend_log, evidence_dir / "tftp.log"):
            evidence.append({"path": str(path.relative_to(ROOT)), "sha256": sha256(path)})
        result = {
            "schema": "openmitrastar.q1-mtd4-flash-result/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "PASS",
            "candidate_sha256": EXPECTED_SHA256,
            "physical_write": {"offset": TARGET_OFFSET, "size": TARGET_BYTES, "partition": "mtd4/linux_live"},
            "rollback": {"offset": ROLLBACK_OFFSET, "size": ROLLBACK_BYTES,
                         "partition": "mtd3/linux_safety", "sha256": ROLLBACK_SHA256,
                         "preserved": True, "bootselect_unchanged": True,
                         "selection": "manual-uart-ATGO",
                         "evidence_sha256": ROLLBACK_LOG_SHA256},
            "readback": {"full_slot_sha256": preflight["expected_full_slot_sha256"],
                         "candidate_prefix_sha256": EXPECTED_SHA256, "status": "PASS"},
            "evidence": evidence,
        }
        result_path = evidence_dir / "result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"result": result, "result_path": str(result_path.relative_to(ROOT))}
    finally:
        if tftp.poll() is None:
            tftp.terminate()
            try:
                tftp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tftp.kill()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--client-ip", default="192.168.1.90")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--skip-reboot", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--max-attestation-age-minutes", type=int, default=240)
    args = parser.parse_args()
    plan = {
        "mode": "execute" if args.execute else "dry-run",
        "candidate": str(CANDIDATE.relative_to(ROOT)),
        "candidate_sha256": EXPECTED_SHA256,
        "candidate_bytes": EXPECTED_BYTES,
        "physical_write": {"partition": "mtd4/linux_live", "offset": "0x007e0000", "size": "0x007a0000"},
        "rollback": {"partition": "mtd3/linux_safety", "offset": "0x00040000",
                     "size": "0x007a0000", "sha256": ROLLBACK_SHA256, "write": False,
                     "selection": "manual-uart-ATGO",
                     "evidence_sha256": ROLLBACK_LOG_SHA256},
        "environment_write": False,
        "requires": ["fresh current-flash-read", "exact-candidate RAM equivalence PASS",
                     "all strict readiness gates PASS", "UART+Bootbase+TFTP",
                     "fresh mtd3 CRC equals current-unit dump before mtd4 write"],
    }
    if not args.execute:
        try:
            preflight = validate_local_inputs(args.max_attestation_age_minutes)
            readiness = run_readiness()
            plan["preflight"] = preflight
            plan["blocking_gates_passed"] = sum(
                1 for gate in readiness["gates"] if gate.get("blocking") and gate.get("passed")
            )
            plan["dry_run_ready"] = True
        except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
            plan["dry_run_ready"] = False
            plan["blocked_reason"] = str(exc)
        print(json.dumps(plan, indent=2, sort_keys=True))
        print(f"OMQ1_MTD4_FLASH_ONE_SHOT_DRY_RUN_PASS=1 ready={int(bool(plan['dry_run_ready']))} flash=0")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"--execute requires --ack {ACK}")
    if args.host != "192.168.1.90" or args.client_ip != "192.168.1.90":
        raise SystemExit("Q1 execute mode is pinned to management/client 192.168.1.90")
    if not 600 <= args.timeout <= 1800:
        raise SystemExit("--timeout must be 600..1800")
    preflight = validate_local_inputs(args.max_attestation_age_minutes)
    run_readiness()
    result = execute_backend(args, preflight)
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"OMQ1_MTD4_FLASH_ONE_SHOT_PASS=1 candidate={EXPECTED_SHA256} result={result['result_path']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError,
            subprocess.TimeoutExpired) as exc:
        print(f"OMQ1_MTD4_FLASH_ONE_SHOT_FAIL error={exc}", file=sys.stderr)
        raise SystemExit(1)
