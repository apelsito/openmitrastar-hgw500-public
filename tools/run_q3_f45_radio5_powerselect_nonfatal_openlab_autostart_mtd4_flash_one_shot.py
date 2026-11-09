#!/usr/bin/env python3
"""One-shot Bootbase writer for the exact Q3/F45 radio5 power-selection-nonfatal open-lab autostart Linux 5.10 candidate.

Default mode is a local dry-run. Execute mode is pinned to HGW-500BNA-QCv2/A2,
the Bootbase-accepted F45 candidate, physical mtd4/linux_live, and manual
UART/Bootbase entry. It does not use omspiro, module hotload, or RAM boot.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import zlib


ROOT = Path(__file__).resolve().parents[1]
BUILD_DIR = Path(os.environ.get(
    "OM_Q3_FLASH_BUILD_DIR",
    ROOT / "work/mission-state/q3-f45-radio5-powerselect-nonfatal-openlab-autostart/build",
))
CANDIDATE = Path(os.environ.get(
    "OM_Q3_FLASH_CANDIDATE",
    BUILD_DIR / "openmitrastar-linux510-q3-f45-radio5-powerselect-nonfatal-openlab-autostart-v1.webformat.bin",
))
BOOTBASE_CONTRACT = Path(os.environ.get("OM_Q3_FLASH_BOOTBASE_CONTRACT", BUILD_DIR / "bootbase-contract.json"))
MANIFEST = Path(os.environ.get("OM_Q3_FLASH_MANIFEST", BUILD_DIR / "manifest.json"))
INITRAMFS = Path(os.environ.get(
    "OM_Q3_FLASH_INITRAMFS",
    BUILD_DIR / "openmitrastar-linux510-q3-f45-radio5-powerselect-nonfatal-openlab-autostart-v1.initramfs.cpio",
))
KCONFIG = Path(os.environ.get(
    "OM_Q3_FLASH_KCONFIG",
    BUILD_DIR / "openmitrastar-linux510-q3-f45-radio5-powerselect-nonfatal-openlab-autostart-v1.config",
))
LAYOUT_MODE = os.environ.get("OM_Q3_FLASH_LAYOUT_MODE", "initramfs")
ROOTFS_IMAGE = Path(os.environ.get("OM_Q3_FLASH_ROOTFS_IMAGE", "")) if os.environ.get("OM_Q3_FLASH_ROOTFS_IMAGE") else None
DTB_IMAGE = Path(os.environ.get("OM_Q3_FLASH_DTB", "")) if os.environ.get("OM_Q3_FLASH_DTB") else None
ROOTFS_OFFSET = int(os.environ.get("OM_Q3_FLASH_ROOTFS_OFFSET", "0x180000"), 0)
BACKUP_MANIFEST = ROOT / "outputs/flash-backups/hgw500-physical-ssh-20260823T220312Z/current-unit/manifest.json"
POWERSHELL_BACKEND = Path(os.environ.get(
    "OM_Q3_FLASH_POWERSHELL_BACKEND",
    ROOT / "tools/q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_bootbase_flash.ps1",
))
TFTP_TOOL = ROOT / "tools/tftp_serve_once.py"
UART_LOADER = ROOT / "tools/uart_ymodem_load.py"

EXPECTED_SHA256 = os.environ.get(
    "OM_Q3_FLASH_EXPECTED_SHA256",
    "18f114d09f0abe74efb928cdb3643cf6f1601c7930515091ff33eb922f197f77",
)
EXPECTED_BYTES = int(os.environ.get("OM_Q3_FLASH_EXPECTED_BYTES", "4339143"))
EXPECTED_BACKUP_MANIFEST_SHA256 = "8f3bbed7a9ed9ed07a86ba8b07aa30bc1f1ddf26940025ad1f64c8dae53b1fbf"
EXPECTED_PHYSICAL_IMAGE_SHA256 = "21449b3087b4380b7faac9813efbb3cef3ae10d34951c9777fde25b0ae6512eb"
EXPECTED_CURRENT_LIVE_CRC32 = os.environ.get("OM_Q3_F45_EXPECTED_CURRENT_LIVE_CRC32", "ec3dd18b")
EXPECTED_CURRENT_LIVE_SHA256 = os.environ.get(
    "OM_Q3_F45_EXPECTED_CURRENT_LIVE_SHA256",
    "91f2caf09e264bc030c0ed8240868a2da1c7eab8b2eab68dd3fa65c8d978b485",
)
TARGET_OFFSET = 0x007E0000
TARGET_BYTES = 0x007A0000
ROLLBACK_OFFSET = 0x00040000
ROLLBACK_BYTES = 0x007A0000
ROLLBACK_SHA256 = "f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1"
ACK = os.environ.get(
    "OM_Q3_FLASH_ACK",
    "OPENMITRASTAR_Q3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_AUTOSTART_MTD4_FLASH_18F114D0",
)


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
    if os.environ.get("OM_Q3_F45_REQUIRE_BACKUP_LIVE_SLOT_MATCH") == "1":
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
    required_paths = [CANDIDATE, BOOTBASE_CONTRACT, MANIFEST, INITRAMFS, KCONFIG, POWERSHELL_BACKEND, TFTP_TOOL, UART_LOADER]
    if LAYOUT_MODE == "squashfs-split":
        if ROOTFS_IMAGE is None or DTB_IMAGE is None:
            raise ValueError("squashfs-split requires rootfs and DTB inputs")
        required_paths.extend((ROOTFS_IMAGE, DTB_IMAGE))
    elif LAYOUT_MODE != "initramfs":
        raise ValueError(f"unsupported flash layout mode: {LAYOUT_MODE}")
    for path in required_paths:
        if not path.is_file():
            raise ValueError(f"missing required input: {path}")

    candidate = CANDIDATE.read_bytes()
    candidate_sha = hashlib.sha256(candidate).hexdigest()
    if candidate_sha != EXPECTED_SHA256 or len(candidate) != EXPECTED_BYTES:
        raise ValueError("exact autonomous candidate hash/size mismatch")

    contract = json.loads(BOOTBASE_CONTRACT.read_text(encoding="utf-8"))
    contract_image = contract.get("candidate", contract)
    header = contract_image.get("header", {})
    if contract_image.get("accepted_by_contract") is not True:
        raise ValueError("Bootbase contract is not accepted")
    if contract_image.get("sha256") != EXPECTED_SHA256 or contract_image.get("size") != EXPECTED_BYTES:
        raise ValueError("Bootbase contract is bound to a different image")
    if header.get("compression") != 3 or header.get("arch") != 19:
        raise ValueError("candidate is not ARC/LZMA Bootbase image")
    if int(header.get("payload_size", 0)) <= 0 or int(header.get("payload_size", 0)) >= TARGET_BYTES:
        raise ValueError("candidate payload size invalid")

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    webformat = manifest.get("artifacts", {}).get("webformat", {})
    if webformat.get("sha256") != EXPECTED_SHA256 or webformat.get("bytes") != EXPECTED_BYTES:
        raise ValueError("F45 manifest is bound to a different image")
    rootfs = manifest.get("artifacts", {}).get("rootfs", {})
    manifest_rootfs = manifest.get("rootfs", {}).get("rootfs", {})
    classification = str(manifest.get("classification", ""))
    schema = str(manifest.get("schema", "")).lower()
    fixed_size_compensation = manifest.get("patch", {}).get("fixed_size_compensation", {})
    is_fixed_layout = (
        "FIXED_SIZE" in classification
        or "FIXED_OFFSET" in classification
        or "fixed-size" in schema
        or "fixed-offset" in schema
        or (
            fixed_size_compensation.get("raw_bytes_preserved") is True
            and fixed_size_compensation.get("cpio_end_preserved") is True
        )
    )
    if LAYOUT_MODE == "squashfs-split":
        split_rootfs = manifest.get("artifacts", {}).get("rootfs_squashfs", {})
        if split_rootfs.get("sha256") != sha256(ROOTFS_IMAGE) or split_rootfs.get("bytes") != ROOTFS_IMAGE.stat().st_size:
            raise ValueError("split SquashFS manifest hash/size mismatch")
        rootfs_bytes = ROOTFS_IMAGE.read_bytes()
        if rootfs_bytes[:4] != b"hsqs":
            raise ValueError("split rootfs lacks SquashFS magic")
        if candidate[ROOTFS_OFFSET:ROOTFS_OFFSET + len(rootfs_bytes)] != rootfs_bytes:
            raise ValueError("candidate does not contain exact SquashFS at declared offset")
        if manifest.get("layout", {}).get("rootfs_offset") != f"0x{ROOTFS_OFFSET:06x}":
            raise ValueError("split rootfs offset contract mismatch")
    elif rootfs or manifest_rootfs:
        if rootfs.get("sha256") != manifest_rootfs.get("sha256"):
            raise ValueError("F45 manifest rootfs hash mismatch")
    elif not is_fixed_layout:
        raise ValueError("F45 manifest rootfs hash mismatch")
    actual_key_fp = manifest.get("source_rootfs_bootstrap_authorized_key_fingerprint")

    if LAYOUT_MODE == "initramfs":
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
        forbidden_markers = [b"OMPRODUCT_ENTROPY_SEED_REQUIRED", b"/dev/ttyS0"]
        found = [marker.decode("ascii", errors="ignore") for marker in forbidden_markers if marker in initramfs_bytes]
        if found:
            raise ValueError(f"initramfs contains forbidden manual entropy/UART marker: {found}")

    config = KCONFIG.read_text(encoding="utf-8", errors="replace")
    required_config = ["CONFIG_CRYPTO_JITTERENTROPY=y", "CONFIG_CRYPTO_USER_API_RNG=y", "CONFIG_MTD=y", "CONFIG_MTD_BLOCK_RO=y", "# CONFIG_MTD_BLOCK is not set", "CONFIG_JFFS2_FS=y", "# CONFIG_WATCHDOG is not set"]
    if LAYOUT_MODE == "squashfs-split":
        required_config.extend(['CONFIG_INITRAMFS_SOURCE=""', "CONFIG_SQUASHFS=y", "CONFIG_SQUASHFS_XZ=y"])
        dtb = DTB_IMAGE.read_bytes()
        for marker in (b"root=31:3", b"rootfstype=squashfs", b"rootfs_live"):
            if marker not in dtb:
                raise ValueError(f"split SquashFS DTB missing marker: {marker!r}")
    else:
        required_config.extend(["# CONFIG_RD_GZIP is not set", "CONFIG_INITRAMFS_COMPRESSION_NONE=y"])
    missing_config = [item for item in required_config if item not in config]
    if missing_config:
        raise ValueError(f"kernel config missing: {missing_config}")

    backend_text = POWERSHELL_BACKEND.read_text(encoding="utf-8", errors="replace")
    if os.environ.get("OM_Q3_FLASH_EXPECTED_SHA256") or os.environ.get("OM_Q3_FLASH_ACK"):
        for marker in ("OM_Q3_FLASH_EXPECTED_SHA256", "OM_Q3_FLASH_EXPECTED_BYTES", "OM_Q3_FLASH_ACK"):
            if marker not in backend_text:
                raise ValueError(f"PowerShell backend lacks override support: {marker}")
    elif EXPECTED_SHA256 not in backend_text or ACK not in backend_text:
        raise ValueError("PowerShell backend is not pinned to autonomous candidate")

    parts = load_backup_partitions()
    padded = full_slot_bytes(candidate)
    return {
        "candidate_sha256": EXPECTED_SHA256,
        "candidate_bytes": EXPECTED_BYTES,
        "candidate_crc32": f"{zlib.crc32(candidate) & 0xFFFFFFFF:08x}",
        "candidate_path": rel(CANDIDATE),
        "served_tftp_path": "<new-attempt>/tftp-only/" + CANDIDATE.name,
        "bootbase_contract": rel(BOOTBASE_CONTRACT),
        "manifest": rel(MANIFEST),
        "source_rootfs_bootstrap_authorized_key_fingerprint": actual_key_fp,
        "manifest_candidate_eligible": manifest.get("candidate_eligible"),
        "manifest_flash_supported": manifest.get("flash_supported"),
        "manifest_classification": manifest.get("classification"),
        "layout_mode": LAYOUT_MODE,
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


def start_tftp(timeout: int, root: Path, server_ip: str, client_ip: str, filename: str) -> subprocess.Popen[str]:
    return subprocess.Popen(
        [
            sys.executable,
            str(TFTP_TOOL),
            "--root",
            str(root),
            "--bind",
            server_ip,
            "--allow-client",
            client_ip,
            "--allow-file",
            filename,
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
    evidence_dir = getattr(args, "evidence_dir", None) or BUILD_DIR / f"flash-one-shot-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    transcript = evidence_dir / "bootbase-flash-uart.log"
    tftp = None
    tftp_log = evidence_dir / "tftp.log"
    tftp_output = ""
    served_root = evidence_dir / "tftp-only"
    served_candidate = served_root / CANDIDATE.name
    served_root_created = False
    uart_loader_log = evidence_dir / "uart-ymodem.log"
    uart_loader_status = evidence_dir / "uart-ymodem-status.json"
    uart_loader_console = evidence_dir / "uart-ymodem-console.log"
    try:
        candidate_for_backend = CANDIDATE
        if args.transport == "tftp":
            if not args.external_tftp:
                served_root.mkdir(exist_ok=False)
                served_root_created = True
                shutil.copy2(CANDIDATE, served_candidate)
                if sha256(served_candidate) != EXPECTED_SHA256 or served_candidate.stat().st_size != EXPECTED_BYTES:
                    raise RuntimeError("served TFTP candidate hash mismatch")
                candidate_for_backend = served_candidate
                tftp = start_tftp(args.timeout, served_root, args.server_ip, args.client_ip, CANDIDATE.name)
                time.sleep(0.7)
                if tftp.poll() is not None:
                    raise RuntimeError("scoped TFTP listener exited before backend; no UART backend invoked")
        else:
            loader_command = [
                    sys.executable,
                    str(UART_LOADER),
                    "--port",
                    args.port,
                    "--file",
                    str(CANDIDATE),
                    "--address",
                    "0x83000000",
                    "--expected-sha256",
                    EXPECTED_SHA256,
                    "--expected-size",
                    str(EXPECTED_BYTES),
                    "--expected-crc32",
                    str(preflight["candidate_crc32"]),
                    "--log",
                    str(uart_loader_log),
                    "--status",
                    str(uart_loader_status),
                    "--prompt-timeout",
                    "300",
                ]
            if args.uart_attach_topaz:
                loader_command.append("--receiver-ready" if args.uart_receiver_ready else "--attach-topaz")
            else:
                loader_command.append("--reboot-sysrq")
            loader_process = subprocess.Popen(
                loader_command,
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                bufsize=1,
            )
            loader_lines: list[str] = []
            assert loader_process.stdout is not None
            for line in loader_process.stdout:
                print(line, end="", flush=True)
                loader_lines.append(line)
            loader_returncode = loader_process.wait()
            loader_output = "".join(loader_lines)
            uart_loader_console.write_text(loader_output, encoding="utf-8")
            if loader_returncode != 0 or "OMLYOKO_UART_YMODEM_RAM_LOAD_PASS=1" not in loader_output:
                raise RuntimeError(f"UART/YMODEM candidate load failed; evidence={evidence_dir}")
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
            str(candidate_for_backend),
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
            "-EraseBytes",
            str(args.erase_bytes),
            "-TimeoutSeconds",
            str(args.timeout),
            "-SkipReboot",
        ]
        if args.transport == "uart-ymodem":
            command.append("-SkipNetworkTransfer")
        elif args.skip_bootbase_ping:
            command.append("-SkipBootbasePing")
        if getattr(args, "attempt_id", None):
            command.extend(("-AttemptId", args.attempt_id))
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
        if getattr(args, "attempt_id", None):
            from f319_flash_fallback import record_attempt
            record_attempt(evidence_dir, attempt_id=args.attempt_id, candidate=EXPECTED_SHA256,
                           current_crc=EXPECTED_CURRENT_LIVE_CRC32, transport=args.transport, returncode=proc.returncode)
        if proc.returncode != 0 or "OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_AND_READBACK_PASS=1" not in proc.stdout:
            raise RuntimeError(f"Q3/F45 radio5 power-selection-nonfatal open-lab flash backend failed; evidence={evidence_dir}")
        if tftp is not None and tftp.poll() is None:
            tftp.terminate()
            try:
                tftp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tftp.kill()
                tftp.wait(timeout=5)
        if tftp is not None and tftp.stdout:
            try:
                tftp_output = tftp.stdout.read()
            except OSError:
                pass
        if args.transport == "tftp":
            tftp_log.write_text(tftp_output, encoding="utf-8")
        evidence_paths = [transcript, backend_log]
        if args.transport == "tftp":
            evidence_paths.append(tftp_log)
        else:
            evidence_paths.extend((uart_loader_log, uart_loader_status, uart_loader_console))
        evidence = [{"path": rel(path), "sha256": sha256(path)} for path in evidence_paths]
        result = {
            "schema": "openmitrastar.q3-f45-radio5-powerselect-nonfatal-openlab-autostart-mtd4-flash-result/v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "PASS",
            "candidate_sha256": EXPECTED_SHA256,
            "physical_write": {
                "offset": TARGET_OFFSET,
                "erase_size": args.erase_bytes,
                "candidate_size": EXPECTED_BYTES,
                "slot_size": TARGET_BYTES,
                "partition": "mtd4/linux_live",
            },
            "protected_partitions": {**preflight["protected_partition_sha256"], "status": "PASS"},
            "rollback": {
                "partition": "mtd3/linux_safety",
                "sha256": ROLLBACK_SHA256,
                "preserved": True,
                "bootselect_unchanged": True,
                "selection": "manual-uart-ATGO",
            },
            "readback": {
                "transport": f"UART Bootbase {args.transport} load + spi_flash read/write + crc32 + cmp.b",
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
        if tftp is not None and tftp.poll() is None:
            tftp.terminate()
            try:
                tftp.wait(timeout=5)
            except subprocess.TimeoutExpired:
                tftp.kill()
                tftp.wait(timeout=5)
        if args.transport == "tftp" and not tftp_log.exists():
            if tftp is not None and tftp.stdout:
                try:
                    tftp_output = tftp.stdout.read()
                except OSError:
                    pass
            tftp_log.write_text(tftp_output, encoding="utf-8")
        if served_root_created:
            # Only this attempt's copy; preserve evidence, originals and unknown files.
            served_candidate.unlink(missing_ok=True)
            served_root.rmdir()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--server-ip", default="192.168.1.43")
    parser.add_argument("--client-ip", default="192.168.1.90")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--transport", choices=("tftp", "uart-ymodem"), default="tftp")
    parser.add_argument("--external-tftp", action="store_true")
    parser.add_argument("--skip-bootbase-ping", action="store_true")
    parser.add_argument("--skip-reboot", action="store_true")
    parser.add_argument("--uart-attach-topaz", action="store_true")
    parser.add_argument("--uart-receiver-ready", action="store_true")
    parser.add_argument("--timeout", type=int, default=900)
    parser.add_argument("--erase-bytes", type=lambda value: int(value, 0), default=TARGET_BYTES)
    parser.add_argument("--evidence-dir", type=Path, help="Exact new host evidence directory for this attempt")
    parser.add_argument("--attempt-id", help="32-hex host-only identity for pre-erase transport handoff evidence")
    args = parser.parse_args()
    if bool(args.evidence_dir) != bool(args.attempt_id):
        raise SystemExit("--evidence-dir and --attempt-id must be supplied together")
    if args.attempt_id and not re.fullmatch(r"[0-9a-f]{32}", args.attempt_id):
        raise SystemExit("--attempt-id must be exactly 32 lowercase hex digits")
    if args.evidence_dir:
        args.evidence_dir = args.evidence_dir.resolve()
        if args.evidence_dir.exists(): raise SystemExit("refusing to reuse flash attempt evidence")

    preflight = validate_local_inputs()
    if args.erase_bytes < EXPECTED_BYTES or args.erase_bytes > TARGET_BYTES or args.erase_bytes % 0x10000:
        raise SystemExit("--erase-bytes must be sector-aligned, contain the candidate, and stay within mtd4")
    preflight["write_transport"] = "UART Bootbase + YMODEM" if args.transport == "uart-ymodem" else "UART Bootbase + TFTP"
    preflight["erase_bytes"] = args.erase_bytes
    plan = {
        "mode": "execute" if args.execute else "dry-run",
        "ready": True,
        "ack": ACK,
        **preflight,
        "physical_write": {
            "partition": "mtd4/linux_live",
            "offset": "0x007e0000",
            "erase_size": f"0x{args.erase_bytes:08x}",
            "slot_size": "0x007a0000",
        },
        "forbidden_physical_writes": ["mtd0/uboot", "mtd1/env", "mtd2/env_bak", "mtd3/linux_safety", "mtd5/data"],
        "requires_execute": (["UART SysRq/autoboot catch", "YMODEM RAM load", "exact ACK"] if args.transport == "uart-ymodem" else ["manual Bootbase/ZHAL prompt on UART", "TFTP reachability", "--skip-reboot", "exact ACK"]),
        "flash_ready": False,
    }
    if not args.execute:
        print(json.dumps(plan, indent=2, sort_keys=True))
        print("OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_ONE_SHOT_DRY_RUN_PASS=1 ready=1 flash=0 linux_ram_writes=0")
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
    print(f"OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_ONE_SHOT_PASS=1 candidate={EXPECTED_SHA256} result={result['result_path']}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, KeyError, json.JSONDecodeError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"OMQ3_F45_RADIO5_POWERSELECT_NONFATAL_OPENLAB_MTD4_FLASH_ONE_SHOT_FAIL error={exc}", file=sys.stderr)
        raise SystemExit(1)

