#!/usr/bin/env python3
"""Fail-closed Q3 v3 promotion gate for physical mtd4.

Dry-run is the default.  A physical write is unreachable unless an explicit,
hash-pinned PASS_ASSOCIATED document for the exact candidate is supplied and
the destructive acknowledgement is exact.  This tool never targets mtd0,
mtd1, mtd2, mtd3 or mtd5.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import zlib


ROOT = Path(__file__).resolve().parents[1]
PROMOTION = ROOT / "work/mission-state/q3-v3-mtd4-promotion"
CANDIDATE = PROMOTION / "artifacts/q3-autostart-v3-1f0c1bf5.bin"
TFTP_CANDIDATE = ROOT / "work/tftp/omvl/q3-autostart-v3-1f0c1bf5.bin"
Q2_ROLLBACK = PROMOTION / "artifacts/q2-rollback-cbe904ab.bin"
BUILD_MANIFEST = PROMOTION / "evidence/q3-build-manifest.json"
BOOTBASE_CONTRACT = PROMOTION / "evidence/q3-bootbase-contract.json"
RAM_EQUIVALENCE = PROMOTION / "evidence/q3-ram-equivalence.json"
BACKUP_MANIFEST = PROMOTION / "evidence/current-unit-backup-manifest.json"
Q2_FLASH_RESULT = PROMOTION / "evidence/q2-flash-result.json"
OMSPIRO = ROOT / "outputs/kernel-port/omspiro-readonly-RAM-ONLY-NO-FLASH/omspiro.ko"
BACKEND = ROOT / "tools/q3_v3_mtd4_bootbase_flash.ps1"

EXPECTED_CANDIDATE = "1f0c1bf5b29c77c3670be9891db9da6bb3d186f0fb931b8de711a5b5d89c6296"
EXPECTED_CANDIDATE_BYTES = 4_312_048
EXPECTED_Q2 = "cbe904ab7a807838fa12077fab924c79ce3c112a5ef40727cbaf9ec98f638cf1"
EXPECTED_Q2_BYTES = 4_157_772
SLOT_BYTES = 0x7A0000
ACK = "OPENMITRASTAR_Q3_V3_MTD4_FLASH_1F0C1BF5_PASS_ASSOCIATED"
BACKUP_MANIFEST_SHA = "38932dabe6057df544e4f114df7cecee33b615576ec5dafdf29c07cb1e85a935"
PROTECTED = {
    "mtd0": "a5fee18d095b1a7987ad71492bc6d1f86656d6b6a0877adeb40e5300e2eff7f1",
    "mtd1": "12aac941ac824b6249a20e6c7523e46cd484ac5e8a85cdea73659835fb352b1d",
    "mtd2": "8992410e131045fd6521fb5ebd7de87bb95b862d65ea7811ee4f12b4beb65483",
    "mtd3": "f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1",
    "mtd5": "1ba0ec4124a4fb34701ac08079b7598ecf7ac25b96380b92182d0e67261dbba0",
}
PARTITION_FILES = {
    "mtd0": "hgw500_mtdblock0.bin", "mtd1": "hgw500_mtdblock1.bin",
    "mtd2": "hgw500_mtdblock2.bin", "mtd3": "hgw500_mtdblock3.bin",
    "mtd5": "hgw500_mtdblock5.bin",
}
BACKUP_DIR = ROOT / "outputs/flash-backups/hgw500-physical-ssh-20260820/current-unit"
Q2_FULL_SLOT_SHA = "29e696799639d19e37fec7e142f67228127a26a5aaa014dd06c3c9d6381b8221"
Q2_FULL_SLOT_CRC = "d533dfd0"
ROLLBACK_CRC = "f7d14d3d"
OMSPIRO_SHA = "7e00484816f37496f263e22e1bb286d8383681f1af4ad5629cd49ca97d659201"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


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


def validate_association(path: Path | None) -> tuple[bool, str, str | None]:
    if path is None or not path.is_file():
        return False, "missing PASS_ASSOCIATED evidence", None
    digest = sha(path)
    try:
        evidence = load_json(path)
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"invalid association evidence: {exc}", digest
    checks = (
        evidence.get("schema") == "openmitrastar.q3-client-association-evidence/v1",
        evidence.get("status") == "PASS_ASSOCIATED",
        evidence.get("candidate_sha256") == EXPECTED_CANDIDATE,
        evidence.get("client_association", {}).get("status") == "PASS",
        evidence.get("client_traffic", {}).get("status") == "PASS",
        evidence.get("flash_actions") is False,
    )
    return all(checks), "PASS_ASSOCIATED" if all(checks) else "association contract incomplete", digest


def validate_static() -> dict:
    required = [CANDIDATE, Q2_ROLLBACK, BUILD_MANIFEST,
                BOOTBASE_CONTRACT, RAM_EQUIVALENCE, BACKUP_MANIFEST,
                Q2_FLASH_RESULT, OMSPIRO, BACKEND]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise ValueError(f"missing promotion inputs: {missing}")
    if sha(CANDIDATE) != EXPECTED_CANDIDATE or CANDIDATE.stat().st_size != EXPECTED_CANDIDATE_BYTES:
        raise ValueError("exact Q3 candidate mismatch")
    if sha(Q2_ROLLBACK) != EXPECTED_Q2 or Q2_ROLLBACK.stat().st_size != EXPECTED_Q2_BYTES:
        raise ValueError("Q2 rollback mismatch")
    if sha(BACKUP_MANIFEST) != BACKUP_MANIFEST_SHA:
        raise ValueError("current-unit backup manifest mismatch")

    build = load_json(BUILD_MANIFEST)
    bootbase = load_json(BOOTBASE_CONTRACT)
    ram = load_json(RAM_EQUIVALENCE)
    backup = load_json(BACKUP_MANIFEST)
    q2_result = load_json(Q2_FLASH_RESULT)
    if build["artifacts"]["webformat"]["sha256"] != EXPECTED_CANDIDATE:
        raise ValueError("Q3 build manifest candidate mismatch")
    if not bootbase.get("accepted_by_contract"):
        raise ValueError("Bootbase contract is not PASS")
    if ram.get("result") != "Q3_AUTOSTART_V3_RAM_PASS_ASSOCIATION_PENDING" or ram["candidate"]["sha256"] != EXPECTED_CANDIDATE:
        raise ValueError("Q3 RAM evidence does not bind exact candidate")
    if ram["open_gates"]["flash"]["status"] != "NOT_EXECUTED":
        raise ValueError("Q3 RAM evidence flash boundary invalid")

    by_index = {f"mtd{row['index']}": row for row in backup["partitions"]}
    for name, expected in PROTECTED.items():
        row = by_index[name]
        if row["sha256"] != expected or row["exact_size"] is not True:
            raise ValueError(f"protected backup mismatch: {name}")
        physical = BACKUP_DIR / PARTITION_FILES[name]
        if not physical.is_file() or sha(physical) != expected or physical.stat().st_size != row["size"]:
            raise ValueError(f"protected backup file mismatch: {name}")
    if q2_result.get("status") != "PASS" or q2_result.get("candidate_sha256") != EXPECTED_Q2:
        raise ValueError("Q2 rollback flash result mismatch")
    if q2_result["readback"]["candidate_prefix_sha256"] != EXPECTED_Q2 or q2_result["readback"]["full_slot_sha256"] != Q2_FULL_SLOT_SHA:
        raise ValueError("Q2 rollback readback mismatch")
    for name, expected in PROTECTED.items():
        if q2_result["protected_partitions"][name] != expected:
            raise ValueError(f"Q2 protected readback mismatch: {name}")
    if sha(OMSPIRO) != OMSPIRO_SHA or OMSPIRO.stat().st_size != 4856:
        raise ValueError("OMSPIRO read-only verifier mismatch")

    candidate = CANDIDATE.read_bytes()
    padded = candidate + b"\xff" * (SLOT_BYTES - len(candidate))
    return {
        "candidate_crc32": f"{zlib.crc32(candidate) & 0xffffffff:08x}",
        "full_slot_sha256": hashlib.sha256(padded).hexdigest(),
        "full_slot_crc32": f"{zlib.crc32(padded) & 0xffffffff:08x}",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--association-evidence", type=Path,
                        default=PROMOTION / "association-evidence.REQUIRED.json")
    parser.add_argument("--output", type=Path, default=PROMOTION / "promotion-manifest.json")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    args = parser.parse_args(argv)

    computed = validate_static()
    association_ok, association_detail, association_sha = validate_association(args.association_evidence)
    gates = {
        "exact_q3_candidate": "PASS",
        "bootbase_slot_contract": "PASS",
        "q3_ram_equivalence": "PASS_ASSOCIATION_PENDING",
        "q2_rollback_artifact": "PASS",
        "current_unit_protected_backups": "PASS",
        "mtd4_only_write_policy": "PASS",
        "client_association_and_traffic": "PASS_ASSOCIATED" if association_ok else "PENDING",
    }
    status = "GO" if association_ok else "NO_GO"
    report = {
        "schema": "openmitrastar.q3-v3-mtd4-promotion/v1",
        "status": status,
        "candidate": {"path": str(CANDIDATE.relative_to(ROOT)), "sha256": EXPECTED_CANDIDATE,
                      "bytes": EXPECTED_CANDIDATE_BYTES, **computed},
        "target": {"partition": "mtd4/linux_live", "offset": "0x007e0000", "bytes": SLOT_BYTES},
        "write_policy": {
            "only_partition": "mtd4/linux_live", "only_offset": "0x007e0000",
            "only_bytes": SLOT_BYTES, "forbidden_partitions": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"],
            "environment_write_forbidden": True, "mtd6_is_logical_not_physical": True,
        },
        "protected_partitions": {
            name: {"sha256": digest, "path": str((BACKUP_DIR / PARTITION_FILES[name]).relative_to(ROOT))}
            for name, digest in PROTECTED.items()
        },
        "physical_backups": {"manifest": str(BACKUP_MANIFEST.relative_to(ROOT)),
                             "manifest_sha256": BACKUP_MANIFEST_SHA},
        "rollback": {
            "q2_artifact": str(Q2_ROLLBACK.relative_to(ROOT)), "q2_sha256": EXPECTED_Q2,
            "q2_bytes": EXPECTED_Q2_BYTES, "q2_full_slot_sha256": Q2_FULL_SLOT_SHA,
            "linux_safety_sha256": PROTECTED["mtd3"], "manual_uart": "ATGO"
        },
        "tftp_staging": {
            "path": str(TFTP_CANDIDATE.relative_to(ROOT)),
            "required_for_execute": True,
            "staged_now": TFTP_CANDIDATE.is_file()
            and sha(TFTP_CANDIDATE) == EXPECTED_CANDIDATE,
        },
        "evidence": {
            "q3_build_manifest": {"path": str(BUILD_MANIFEST.relative_to(ROOT)), "sha256": sha(BUILD_MANIFEST)},
            "q3_bootbase_contract": {"path": str(BOOTBASE_CONTRACT.relative_to(ROOT)), "sha256": sha(BOOTBASE_CONTRACT)},
            "q3_ram_equivalence": {"path": str(RAM_EQUIVALENCE.relative_to(ROOT)), "sha256": sha(RAM_EQUIVALENCE)},
            "q2_flash_result": {"path": str(Q2_FLASH_RESULT.relative_to(ROOT)), "sha256": sha(Q2_FLASH_RESULT)},
            "omspiro_readonly": {"path": str(OMSPIRO.relative_to(ROOT)), "sha256": OMSPIRO_SHA},
        },
        "association_evidence": {"path": str(args.association_evidence), "sha256": association_sha,
                                 "detail": association_detail},
        "gates": gates,
        "only_blocker": None if association_ok else "client association and bidirectional traffic",
        "write_permitted": association_ok,
        "execute_requested": args.execute,
        "hardware_actions": False,
        "flash_actions": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))

    if not association_ok:
        print("OMQ3_V3_MTD4_PROMOTION_NO_GO blocker=PASS_ASSOCIATED flash=0")
        return 2
    if not args.execute:
        print("OMQ3_V3_MTD4_PROMOTION_GO_DRY_RUN association=PASS_ASSOCIATED flash=0")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"--execute requires --ack {ACK}")

    atomic_copy(CANDIDATE, TFTP_CANDIDATE)
    if sha(TFTP_CANDIDATE) != EXPECTED_CANDIDATE:
        raise SystemExit("TFTP candidate staging failed")
    assoc_path = args.association_evidence.resolve()
    assoc_sha = sha(assoc_path)
    transcript = PROMOTION / "execution" / "q3-v3-bootbase-flash-uart.log"
    command = [
        "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BACKEND),
        "-Execute", "-Ack", ACK,
        "-Candidate", str(TFTP_CANDIDATE), "-ExpectedSha256", EXPECTED_CANDIDATE,
        "-ExpectedBytes", str(EXPECTED_CANDIDATE_BYTES), "-Port", args.port,
        "-ServerIp", args.server_ip, "-ClientIp", args.host, "-HostAddress", args.host,
        "-Transcript", str(transcript), "-RollbackSha256", PROTECTED["mtd3"],
        "-ProtectedMtd0Sha256", PROTECTED["mtd0"], "-ProtectedMtd1Sha256", PROTECTED["mtd1"],
        "-ProtectedMtd2Sha256", PROTECTED["mtd2"], "-ProtectedMtd5Sha256", PROTECTED["mtd5"],
        "-RollbackCrc32", ROLLBACK_CRC, "-CurrentLiveCrc32", Q2_FULL_SLOT_CRC,
        "-ExpectedCandidateCrc32", computed["candidate_crc32"],
        "-ExpectedFullSlotSha256", computed["full_slot_sha256"],
        "-ExpectedFullSlotCrc32", computed["full_slot_crc32"],
        "-OmspiroModule", str(OMSPIRO), "-ExpectedOmspiroSha256", OMSPIRO_SHA,
        "-ExpectedOmspiroBytes", "4856", "-ExpectedOmspiroKernelRelease", "5.10.260-openmitrastar-radiohw",
        "-ExpectedOmspiroDeviceMode", "0400", "-AssociationEvidence", str(assoc_path),
        "-ExpectedAssociationEvidenceSha256", assoc_sha, "-Q2RollbackArtifact", str(Q2_ROLLBACK),
    ]
    proc = subprocess.run(command, cwd=ROOT, text=True)
    if proc.returncode:
        raise SystemExit(proc.returncode)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
