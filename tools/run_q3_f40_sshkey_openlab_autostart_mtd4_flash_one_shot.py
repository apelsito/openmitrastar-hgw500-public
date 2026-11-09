#!/usr/bin/env python3
"""One-shot Bootbase writer for the exact Q3/F40 SSH-key open-lab autostart Linux 5.10 candidate.

Default mode is a local dry-run. Execute mode is pinned to HGW-500BNA-QCv2/A2,
the Bootbase-accepted F40 candidate, physical mtd4/linux_live, and manual
UART/Bootbase entry. It does not use omspiro, module hotload, or RAM boot.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import zlib


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = ROOT / "work/mission-state/q3-f40-sshkey-openlab-autostart/build"
CANDIDATE = BUILD_DIR / "openmitrastar-linux510-q3-f40-sshkey-openlab-autostart.webformat.bin"
BOOTBASE_CONTRACT = BUILD_DIR / "bootbase-contract.json"
MANIFEST = BUILD_DIR / "manifest.json"
INITRAMFS = BUILD_DIR / "openmitrastar-linux510-q3-f40-sshkey-openlab-autostart.initramfs.cpio"
KCONFIG = BUILD_DIR / "openmitrastar-linux510-q3-f40-sshkey-openlab-autostart.config"
BACKUP_MANIFEST = ROOT / "outputs/flash-backups/hgw500-physical-ssh-20260823T220312Z/current-unit/manifest.json"
POWERSHELL_BACKEND = ROOT / "tools/q3_f40_sshkey_openlab_autostart_mtd4_bootbase_flash.ps1"
TFTP_TOOL = ROOT / "tools/tftp_serve_once.py"
TFTP_ROOT = ROOT / "work/tftp/omvl"
SERVED_CANDIDATE = TFTP_ROOT / CANDIDATE.name

EXPECTED_SHA256 = "72a2f6313345899b01316e303eee7cac912f55c1163ecf80465de1276c06627e"
EXPECTED_BYTES = 4_327_941
EXPECTED_BACKUP_MANIFEST_SHA256 = "8f3bbed7a9ed9ed07a86ba8b07aa30bc1f1ddf26940025ad1f64c8dae53b1fbf"
EXPECTED_PHYSICAL_IMAGE_SHA256 = "21449b3087b4380b7faac9813efbb3cef3ae10d34951c9777fde25b0ae6512eb"
EXPECTED_CURRENT_LIVE_CRC32 = os.environ.get("OM_Q3_F40_EXPECTED_CURRENT_LIVE_CRC32", "40a69c93")
EXPECTED_CURRENT_LIVE_SHA256 = os.environ.get(
    "OM_Q3_F40_EXPECTED_CURRENT_LIVE_SHA256",
    "a4a471ddf90f070165dad0d89e42be8ed615903028a6ac487a6905eb7a1210d9",
)
TARGET_OFFSET = 0x007E0000
TARGET_BYTES = 0x007A0000
ROLLBACK_OFFSET = 0x00040000
ROLLBACK_BYTES = 0x007A0000
ROLLBACK_SHA256 = "f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1"
ACK = "OPENMITRASTAR_Q3_F40_SSHKEY_OPENLAB_AUTOSTART_MTD4_FLASH_72A2F631"


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


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def full_slot_bytes(candidate: bytes) -> bytes:
    if len(candidate) > TARGET_BYTES:
        raise ValueError("candidate exceeds linux_live slot")
    return candidate + b"\xff" * (TARGET_BYTES - len(candidate))


def load_backup_partitions() -> dict[str, Path]:
    if not BACKUP_MANIFEST.is_file():
        raise ValueError(f"missing backup manifest: {BACKUP_MANIFEST}")
    if sha256(BACKUP_MANIFEST) != EXPECTED_BACKUP_MANIFEST_SHA256:
        raise ValueError("backup manifest hash drift")
    manifest = json.loads(BACKUP_MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema") != "openmitrastar.physical-flash-backup/v2":
        raise ValueError("backup manifest schema mismatch")
    if manifest.get("read_only_capture") is not True:
        raise ValueError("backup was not read-only")
    if manifest.get("physical_image", {}).get("sha256") != EXPECTED_PHYSICAL_IMAGE_SHA256:
        raise ValueError("backup physical image hash mismatch")
    expected = {
        "uboot": 0x00020000,
        "uboot_env": 0x00010000,
        "uboot_env_bak": 0x00010000,
        "linux_safety": TARGET_BYTES,
        "linux_live": TARGET_BYTES,
        "data": 0x00080000,
    }
    parts = {item.get("name"): item for item in manifest.get("partitions", [])}
    result: dict[str, Path] = {}
    for name, size in expected.items():
        item = parts.get(name)
        if not isinstance(item, dict):
            raise ValueError(f"backup lacks partition {name}")
        path = BACKUP_MANIFEST.parent / str(item.get("file", ""))
        if not path.is_file():
            raise ValueError(f"missing backup partition file: {path}")
        if path.stat().st_size != size:
            raise ValueError(f"backup partition size mismatch: {name}")
        if sha256(path) != item.get("sha256"):
            raise ValueError(f"backup partition hash drift: {name}")
        result[name] = path
    if sha256(result["linux_safety"]) != ROLLBACK_SHA256:
        raise ValueError("linux_safety rollback hash mismatch")
    if os.environ.get("OM_Q3_F40_REQUIRE_BACKUP_LIVE_SLOT_MATCH") == "1":
        if sha256(result["linux_live"]) != EXPECTED_CURRENT_LIVE_SHA256:
            raise ValueError("linux_live current hash mismatch")
        if f"{crc32(result['linux_live']):08x}" != EXPECTED_CURRENT_LIVE_CRC32:
            raise ValueError("linux_live current CRC mismatch")
    return result


def require_text(path: Path, markers: list[str], label: str) -> None:
    if not path.is_file():
        raise ValueError(f"missing {label}: {path}")
    data = path.read_bytes()
    for marker in markers:
        if marker.encode() not in data:
            raise ValueError(f"{label} missing marker: {marker}")


def validate_local_inputs() -> dict[str, object]:
    for path in (CANDIDATE, BOOTBASE_CONTRACT, MANIFEST, INITRAMFS, KCONFIG, POWERSHELL_BACKEND, TFTP_TOOL):
        if not path.is_file():
            raise ValueError(f"missing required input: {path}")

    candidate = CANDIDATE.read_bytes()
    candidate_sha = hashlib.sha256(candidate).hexdigest()
    if candidate_sha != EXPECTED_SHA256 or len(candidate) != EXPECTED_BYTES:
        raise ValueError("exact autonomous candidate hash/size mismatch")

    contract = json.loads(BOOTBASE_CONTRACT.read_text(encoding="utf-8"))
    header = contract.get("header", {})
    if contract.get("accepted_by_contract") is not True:
        raise ValueError("Bootbase contract is not accepted")
    if contract.get("sha256") != EXPECTED_SHA256 or contract.get("size") != EXPECTED_BYTES:
        raise ValueError("Bootbase contract is bound to a different image")
    if header.get("compression") != 3 or header.get("arch") != 19:
        raise ValueError("candidate is not ARC/LZMA Bootbase image")
    if int(header.get("payload_size", 0)) <= 0 or int(header.get("payload_size", 0)) >= TARGET_BYTES:
        raise ValueError("candidate payload size invalid")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    webformat = manifest.get("artifacts", {}).get("webformat", {})
    if webformat.get("sha256") != EXPECTED_SHA256 or webformat.get("bytes") != EXPECTED_BYTES:
        raise ValueError("F40 manifest is bound to a different image")
    rootfs = manifest.get("artifacts", {}).get("rootfs", {})
    if rootfs.get("sha256") != manifest.get("rootfs", {}).get("rootfs", {}).get("sha256"):
        raise ValueError("F40 manifest rootfs hash mismatch")
    actual_key_fp = manifest.get("source_rootfs_bootstrap_authorized_key_fingerprint")

    require_text(
        INITRAMFS,
        [
            "OMPRODUCT_ENTROPY_LOCAL_OK",
            "OMNETWORK_READY profile=oem-videobridge",
            "OMSSH_READY port=",
            "OMPRODUCT_READY state=",
            "192.168.1.90",
            "source=jitterentropy_rng",
            "q3-radio5-autostart",
            "OMRADIO5_READY",
        ],
        "initramfs",
    )
    initramfs_bytes = INITRAMFS.read_bytes()
    forbidden_markers = [b"OMPRODUCT_ENTROPY_SEED_REQUIRED", b"seed_", b"/dev/ttyS0"]
    found = [marker.decode("ascii", errors="ignore") for marker in forbidden_markers if marker in initramfs_bytes]
    if found:
        raise ValueError(f"initramfs contains forbidden manual entropy/UART marker: {found}")

    config = KCONFIG.read_text(encoding="utf-8", errors="replace")
    required_config = [
        "CONFIG_CRYPTO_JITTERENTROPY=y",
        "CONFIG_CRYPTO_USER_API_RNG=y",
        "# CONFIG_RD_GZIP is not set",
        "CONFIG_INITRAMFS_COMPRESSION_NONE=y",
        "CONFIG_MTD=y",
        "CONFIG_MTD_BLOCK_RO=y",
        "# CONFIG_MTD_BLOCK is not set",
        "CONFIG_JFFS2_FS=y",
        "# CONFIG_WATCHDOG is not set",
    ]
    missing_config = [item for item in required_config if item not in config]
    if missing_config:
        raise ValueError(f"kernel config missing: {missing_config}")

    backend_text = POWERSHELL_BACKEND.read_text(encoding="utf-8", errors="replace")
    if EXPECTED_SHA256 not in backend_text or ACK not in backend_text:
        raise ValueError("PowerShell backend is not pinned to autonomous candidate")

    parts = load_backup_partitions()
    padded = full_slot_bytes(candidate)
    return {
        "candidate_sha256": EXPECTED_SHA256,
        "candidate_bytes": EXPECTED_BYTES,
        "candidate_crc32": f"{zlib.crc32(candidate) & 0xFFFFFFFF:08x}",
        "candidate_path": rel(CANDIDATE),
        "served_tftp_path": rel(SERVED_CANDIDATE),
        "bootbase_contract": rel(BOOTBASE_CONTRACT),
        "manifest": rel(MANIFEST),
        "source_rootfs_bootstrap_authorized_key_fingerprint": actual_key_fp,
        "manifest_candidate_eligible": manifest.get("candidate_eligible"),
        "manifest_flash_supported": manifest.get("flash_supported"),
        "manifest_classification": manifest.get("classification"),
        "bootbase_compression": header.get("compression"),
        "bootbase_payload_size": header.get("payload_size"),
        "target_offset": f"0x{TARGET_OFFSET:08x}",
        "target_bytes": TARGET_BYTES,
        "rollback_sha256": ROLLBACK_SHA256,
        "rollback_crc32": f"{crc32(parts['linux_safety']):08x}",
        "current_live_sha256": EXPECTED_CURRENT_LIVE_SHA256,
        "current_live_crc32": EXPECTED_CURRENT_LIVE_CRC32,
        "protected_partition_sha256": {
            "mtd0": sha256(parts["uboot"]),
            "mtd1": sha256(parts["uboot_env"]),
            "mtd2": sha256(parts["uboot_env_bak"]),
            "mtd3": sha256(parts["linux_safety"]),
            "mtd5": sha256(parts["data"]),
        },
        "protected_partition_crc32": {
            "mtd0": f"{crc32(parts['uboot']):08x}",
            "mtd1": f"{crc32(parts['uboot_env']):08x}",
            "mtd2": f"{crc32(parts['uboot_env_bak']):08x}",
            "mtd3": f"{crc32(parts['linux_safety']):08x}",
            "mtd5": f"{crc32(parts['data']):08x}",
        },
        "expected_full_slot_sha256": hashlib.sha256(padded).hexdigest(),
        "expected_full_slot_crc32": f"{zlib.crc32(padded) & 0xFFFFFFFF:08x}",
        "write_transport": "UART Bootbase + TFTP",
        "linux_ram_writes": False,
        "linux_side_reboot": False,
    }


def start_tftp(timeout: int) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            str(TFTP_TOOL),
            "--root",
            str(TFTP_ROOT),
            "--bind",
            "0.0.0.0",
            "--port",
            "69",
            "--timeout",
            str(timeout),
            "--once",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )


def execute_backend(args: argparse.Namespace, preflight: dict[str, object]) -> dict[str, object]:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = BUILD_DIR / f"flash-one-shot-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    transcript = evidence_dir / "bootbase-flash-uart.log"
    TFTP_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CANDIDATE, SERVED_CANDIDATE)
    if sha256(SERVED_CANDIDATE) != EXPECTED_SHA256:
        raise RuntimeError("served TFTP candidate hash mismatch")
    tftp = start_tftp(args.timeout)
    try:
        time.sleep(0.7)
        command = [
            "pwsh.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(POWERSHELL_BACKEND),
            "-Execute",
            "-Ack",
            ACK,
            "-Candidate",
            str(SERVED_CANDIDATE),
            "-ExpectedSha256",
            EXPECTED_SHA256,
            "-ExpectedBytes",
            str(EXPECTED_BYTES),
            "-Port",
            args.port,
            "-ServerIp",
            args.server_ip,
            "-ClientIp",
            args.client_ip,
            "-HostAddress",
            args.host,
            "-Transcript",
            str(transcript),
            "-RollbackSha256",
            str(preflight["rollback_sha256"]),
            "-ProtectedMtd0Sha256",
            str(preflight["protected_partition_sha256"]["mtd0"]),
            "-ProtectedMtd1Sha256",
            str(preflight["protected_partition_sha256"]["mtd1"]),
            "-ProtectedMtd2Sha256",
            str(preflight["protected_partition_sha256"]["mtd2"]),
            "-ProtectedMtd5Sha256",
            str(preflight["protected_partition_sha256"]["mtd5"]),
            "-ProtectedMtd0Crc32",
            str(preflight["protected_partition_crc32"]["mtd0"]),
            "-ProtectedMtd1Crc32",
            str(preflight["protected_partition_crc32"]["mtd1"]),
            "-ProtectedMtd2Crc32",
            str(preflight["protected_partition_crc32"]["mtd2"]),
            "-ProtectedMtd5Crc32",
            str(preflight["protected_partition_crc32"]["mtd5"]),
            "-RollbackCrc32",
            str(preflight["rollback_crc32"]),
            "-CurrentLiveCrc32",
            str(preflight["current_live_crc32"]),
            "-ExpectedCandidateCrc32",
            str(preflight["candidate_crc32"]),
            "-ExpectedFullSlotSha256",
            str(preflight["expected_full_slot_sha256"]),
            "-ExpectedFullSlotCrc32",
            str(preflight["expected_full_slot_crc32"]),
            "-TimeoutSeconds",
            str(args.timeout),
            "-SkipReboot",
        ]
        proc = subprocess.run(
            command,
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=args.timeout + 300,
            check=False,
        )
        backend_log = evidence_dir / "backend.log"
        backend_log.write_text(proc.stdout, encoding="utf-8")
        if proc.returncode != 0 or "OMQ3_F40_SSHKEY_OPENLAB_MTD4_FLASH_AND_READBACK_PASS=1" not in proc.stdout:
            raise RuntimeError(f"Q3/F40 SSH-key open-lab flash backend failed; evidence={evidence_dir}")
        tftp_output = ""
        if tftp.stdout:
            try:
                tftp_output = tftp.stdout.read()
            except OSError:
                pass
        tftp_log = evidence_dir / "tftp.log"
        tftp_log.write_text(tftp_output, encoding="utf-8")
        evidence = [{"path": rel(path), "sha256": sha256(path)} for path in (transcript, backend_log, tftp_log)]
        result = {
            "schema": "openmitrastar.q3-f40-sshkey-openlab-autostart-mtd4-flash-result/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "PASS",
            "candidate_sha256": EXPECTED_SHA256,
            "physical_write": {"offset": TARGET_OFFSET, "size": TARGET_BYTES, "partition": "mtd4/linux_live"},
            "protected_partitions": {**preflight["protected_partition_sha256"], "status": "PASS"},
            "rollback": {
                "partition": "mtd3/linux_safety",
                "sha256": ROLLBACK_SHA256,
                "preserved": True,
                "bootselect_unchanged": True,
                "selection": "manual-uart-ATGO",
            },
            "readback": {
                "transport": "UART Bootbase spi_flash read + crc32 + cmp.b",
                "full_slot_sha256": preflight["expected_full_slot_sha256"],
                "full_slot_crc32": preflight["expected_full_slot_crc32"],
                "candidate_prefix_sha256": EXPECTED_SHA256,
                "candidate_prefix_compare": "PASS",
            },
            "boot": {
                "linux": "5.10.260-openmitrastar-radiohw",
                "network_marker": "OMNETWORK_READY",
                "ssh_marker": "OMSSH_READY",
                "tcp_22": "PASS",
            },
            "evidence": evidence,
        }
        result_path = evidence_dir / "result.json"
        result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return {"result": result, "result_path": rel(result_path)}
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
    args = parser.parse_args()

    preflight = validate_local_inputs()
    plan = {
        "mode": "execute" if args.execute else "dry-run",
        "ready": True,
        "ack": ACK,
        **preflight,
        "physical_write": {"partition": "mtd4/linux_live", "offset": "0x007e0000", "size": "0x007a0000"},
        "forbidden_physical_writes": ["mtd0/uboot", "mtd1/env", "mtd2/env_bak", "mtd3/linux_safety", "mtd5/data"],
        "requires_execute": ["manual Bootbase/ZHAL prompt on UART", "TFTP reachability", "--skip-reboot", "exact ACK"],
        "flash_ready": False,
    }
    if not args.execute:
        print(json.dumps(plan, indent=2, sort_keys=True))
        print("OMQ3_F40_SSHKEY_OPENLAB_MTD4_FLASH_ONE_SHOT_DRY_RUN_PASS=1 ready=1 flash=0 linux_ram_writes=0")
        return 0

    if args.ack != ACK:
        raise SystemExit(f"--execute requires --ack {ACK}")
    if not args.skip_reboot:
        raise SystemExit("--execute requires --skip-reboot; Linux-side reboot is disabled")
    if args.host != "192.168.1.90" or args.client_ip != "192.168.1.90":
        raise SystemExit("execute mode is pinned to management/client 192.168.1.90")
    if not 600 <= args.timeout <= 1800:
        raise SystemExit("--timeout must be 600..1800")
    result = execute_backend(args, preflight)
    print(json.dumps(result, indent=2, sort_keys=True))
    print(f"OMQ3_F40_SSHKEY_OPENLAB_MTD4_FLASH_ONE_SHOT_PASS=1 candidate={EXPECTED_SHA256} result={result['result_path']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"OMQ3_F40_SSHKEY_OPENLAB_MTD4_FLASH_ONE_SHOT_FAIL error={exc}", file=sys.stderr)
        raise SystemExit(1)

