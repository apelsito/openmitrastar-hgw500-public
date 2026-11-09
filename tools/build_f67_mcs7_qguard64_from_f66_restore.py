#!/usr/bin/env python3
"""Build an F67 2.4 GHz candidate by relaxing the F66 qguard thresholds.

Input is the known-good-ish F66 qguard16r image. Output keeps forced MCS7 and
reclaim polling but raises the queue guard from 16/8 to 64/32. This is offline
only; it creates a Bootbase-compatible artifact and metadata for the existing
mtd4 flash runner.
"""
from __future__ import annotations

import hashlib
import json
import lzma
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GUARD_HIGH = int(__import__("os").environ.get("OM_F67_QGUARD_HIGH", "64"))
GUARD_LOW = int(__import__("os").environ.get("OM_F67_QGUARD_LOW", "32"))
BUILD_TAG = __import__("os").environ.get("OM_F67_BUILD_TAG", f"f67-2g-mcs7-qguard{GUARD_HIGH}r")
PROFILE_TAG = __import__("os").environ.get("OM_F67_PROFILE_TAG", f"qguard{GUARD_HIGH}r")
BE_DATA_SPLIT = __import__("os").environ.get("OM_F67_BE_DATA_SPLIT", "1") not in {"0", "N", "n", "false", "False"}
FORCE_MCS = int(__import__("os").environ.get("OM_F67_FORCE_MCS", "7"))
SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f66-2g-qguard16r-restore/build"
F65_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f65/build"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_IN = "openmitrastar-linux510-q3-persistent-f66-2g-qguard16r-LZMA-OFFLINE-NO-FLASH"
BASE_F65 = "openmitrastar-linux510-q3-persistent-f65-isolated-5g-LZMA-OFFLINE-NO-FLASH"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
OLD_LOADER = ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-radio-modules"
TEMPLATE = ROOT / "Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
BOOTBASE = ROOT / "tools/bootbase_contract_emulator.py"
LEGACY_LZMA = ROOT / "work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma"
PARTS_DIR = ROOT / "hgw500bna-qcv2-firmware-dump-verified"
SLOT_BYTES = 7_995_392
UIMAGE_MAGIC = 0x27051956
UIMAGE_HEADER = 64
RAS_OFFSET = 0x2000


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def crc32(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def parse_uimage_header(blob: bytes) -> list[int | bytes]:
    values = list(struct.unpack(">7I4B32s", blob[:UIMAGE_HEADER]))
    if values[0] != UIMAGE_MAGIC:
        raise SystemExit("bad uImage magic")
    header = bytearray(blob[:UIMAGE_HEADER])
    header[4:8] = b"\0\0\0\0"
    if zlib.crc32(header) & 0xFFFFFFFF != values[1]:
        raise SystemExit("uImage header CRC mismatch")
    return values


def write_uimage(source_uimage: Path, raw: bytes, out: Path, compression: int) -> None:
    values = parse_uimage_header(source_uimage.read_bytes())
    values[1] = 0
    values[3] = len(raw)
    values[6] = zlib.crc32(raw) & 0xFFFFFFFF
    values[10] = compression
    header = bytearray(struct.pack(">7I4B32s", *values))
    values[1] = zlib.crc32(header) & 0xFFFFFFFF
    out.write_bytes(struct.pack(">7I4B32s", *values) + raw)


def write_webformat(uimage: Path, out: Path) -> None:
    source = uimage.read_bytes()
    values = parse_uimage_header(source)
    payload = source[UIMAGE_HEADER:]
    image = bytearray(TEMPLATE.read_bytes()[:RAS_OFFSET])
    image.extend(payload)
    values[1] = 0
    values[3] = len(payload)
    values[6] = zlib.crc32(payload) & 0xFFFFFFFF
    values[8] = 0x13
    header = bytearray(struct.pack(">7I4B32s", *values))
    values[1] = zlib.crc32(header) & 0xFFFFFFFF
    image[:UIMAGE_HEADER] = struct.pack(">7I4B32s", *values)
    out.write_bytes(image)


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix()[3:]
    return f"/mnt/{drive}/{rest}"


def encode_lzma_legacy(raw_path: Path) -> bytes:
    proc = subprocess.run(
        [
            "wsl",
            "-d",
            "podman-openmitrastar-analysis",
            "--",
            wsl_path(LEGACY_LZMA),
            "--keep",
            "--best",
            wsl_path(raw_path),
            "-c",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.decode("utf-8", errors="replace") or "legacy lzma failed")
    return proc.stdout


def loader_offset() -> tuple[int, int]:
    source = (F65_BUILD / f"{BASE_F65}.decompressed.bin").read_bytes()
    old = OLD_LOADER.read_bytes()
    if source.count(old) != 1:
        raise SystemExit("cannot locate original loader span")
    return source.index(old), len(old)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for required in (TEMPLATE, BOOTBASE, LEGACY_LZMA, OLD_LOADER):
        if not required.is_file():
            raise SystemExit(f"missing input: {required}")

    source_raw = SRC_BUILD / f"{BASE_IN}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{BASE_IN}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{BASE_IN}.config"
    for required in (source_raw, source_uncompressed, source_config):
        if not required.is_file():
            raise SystemExit(f"missing source artifact: {required}")

    raw = bytearray(source_raw.read_bytes())
    offset, old_size = loader_offset()
    compact = raw[offset : offset + old_size].split(b"\0", 1)[0].decode("utf-8")
    replacements = {
        "hgw500_tx_queue_guard_high=16": f"hgw500_tx_queue_guard_high={GUARD_HIGH}",
        "hgw500_tx_queue_guard_low=8": f"hgw500_tx_queue_guard_low={GUARD_LOW}",
        "profile=all64-mcs7-eapol-mgntq-qguard16r": f"profile=all64-mcs7-eapol-mgntq-{PROFILE_TAG}",
        "profile=qguard16r": f"profile={PROFILE_TAG}",
    }
    patched = compact
    for old, new in replacements.items():
        if old not in patched:
            raise SystemExit(f"loader missing expected marker: {old}")
        patched = patched.replace(old, new)
    if not BE_DATA_SPLIT:
        for old, new in {
            "hgw500_txbd_be_data_split=1": "hgw500_txbd_be_data_split=0",
            "hgw500_txbd_be_data_split=Y": "hgw500_txbd_be_data_split=N",
        }.items():
            if old not in patched:
                raise SystemExit(f"loader missing expected BE split marker: {old}")
            patched = patched.replace(old, new)
    if FORCE_MCS == 15:
        for old, new in {
            "hgw500_force_data_mcs7=1": "hgw500_force_data_mcs7=0",
            "hgw500_force_data_mcs7=Y": "hgw500_force_data_mcs7=N",
            "hgw500_force_data_mcs15=0": "hgw500_force_data_mcs15=1",
            "hgw500_force_data_mcs15=N": "hgw500_force_data_mcs15=Y",
        }.items():
            if old not in patched:
                raise SystemExit(f"loader missing expected MCS marker: {old}")
            patched = patched.replace(old, new)
    elif FORCE_MCS != 7:
        raise SystemExit("OM_F67_FORCE_MCS currently supports only 7 or 15")
    patched_bytes = patched.encode("utf-8")
    if len(patched_bytes) > old_size:
        raise SystemExit(f"patched loader too large: {len(patched_bytes)} > {old_size}")
    raw[offset : offset + old_size] = patched_bytes + (b"\0" * (old_size - len(patched_bytes)))

    raw_path = OUT / f"{BASE_OUT}.decompressed.bin"
    uncompressed_path = OUT / f"{BASE_OUT}.uncompressed.uImage"
    lzma_path = OUT / f"{BASE_OUT}.lzma"
    uimage_path = OUT / f"{BASE_OUT}.uImage"
    web_path = OUT / f"{BASE_OUT}.webformat.bin"
    config_path = OUT / f"{BASE_OUT}.config"
    loader_path = OUT / "om-radio-modules.fixedsize"
    raw_path.write_bytes(raw)
    loader_path.write_bytes(patched_bytes)
    shutil.copy2(source_config, config_path)
    write_uimage(source_uncompressed, bytes(raw), uncompressed_path, compression=0)
    encoded = encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != bytes(raw):
        raise SystemExit("LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > SLOT_BYTES:
        raise SystemExit("webformat exceeds linux_live slot")

    contract = subprocess.run(
        [
            sys.executable,
            str(BOOTBASE),
            "--candidate-slot",
            str(web_path),
            "--candidate-name",
            f"linux_live-{BUILD_TAG}",
            "--parts-dir",
            str(PARTS_DIR),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if contract.returncode != 0:
        raise SystemExit(contract.stderr or contract.stdout)
    contract_path = OUT / "bootbase-contract.json"
    contract_path.write_text(contract.stdout, encoding="utf-8")
    contract_json = json.loads(contract.stdout)

    artifacts = {
        "decompressed_payload": raw_path,
        "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "kconfig": config_path,
    }
    report = {
        "schema": "openmitrastar.f67-fixed-size-initramfs-patch/v1",
        "source": "F66-qguard16r-restore",
        "changed_file": "usr/sbin/om-radio-modules",
        "old_loader_size": old_size,
        "compact_loader_size": len(patched_bytes),
        "padding_bytes": old_size - len(patched_bytes),
        "loader_offset": f"0x{offset:x}",
        "loader_sha256": sha256(patched_bytes),
        "initramfs_sha256": sha256(bytes(raw)),
        "webformat_sha256": sha256(web_path.read_bytes()),
        "webformat_crc32": crc32(web_path.read_bytes()),
        "bootbase_contract": contract_json.get("result"),
        "candidate_accepted": contract_json.get("candidate", {}).get("accepted_by_contract"),
        "markers": {
            "mcs7": FORCE_MCS == 7,
            "mcs15": FORCE_MCS == 15,
            "autorate": False,
            "queue_guard": True,
            f"queue_guard_high_{GUARD_HIGH}": True,
            f"queue_guard_low_{GUARD_LOW}": True,
            "reclaim_poll": True,
            "be_data_split": BE_DATA_SPLIT,
        },
        "hardware_actions": False,
        "flash_supported": False,
    }
    report_path = OUT / "f67-fixed-size-patch-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f67-qguard-variant/v1",
        "classification": f"F67_FIXED_SIZE_FROM_F66_2G_MCS7_QGUARD{GUARD_HIGH}R",
        "source": "q3-persistent-composite-f66-2g-qguard16r-restore",
        "artifacts": {
            key: {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path.read_bytes()),
                **({"crc32": crc32(path.read_bytes())} if key == "webformat" else {}),
            }
            for key, path in artifacts.items()
        },
        "slot": {"name": "linux_live", "bytes": SLOT_BYTES, "candidate_bytes": web_path.stat().st_size, "fits": True},
        "bootbase_contract": {"file": contract_path.name, "result": contract_json.get("result"), "candidate_accepted": contract_json.get("candidate", {}).get("accepted_by_contract")},
        "security": {"touches_router": False, "opens_uart": False, "flash": False},
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    with (OUT / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as fh:
        for path in sorted([*artifacts.values(), loader_path, contract_path, report_path, manifest_path], key=lambda item: item.name):
            fh.write(f"{sha256(path.read_bytes())}  {path.name}\n")

    tftp_copy = ROOT / "work/tftp/omvl" / web_path.name
    tftp_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(web_path, tftp_copy)
    full_slot = web_path.read_bytes() + b"\xff" * (SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f67-mcs7-qguard-variant-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": crc32(web_path.read_bytes()),
        "full_slot_sha256": sha256(full_slot),
        "full_slot_crc32": crc32(full_slot),
        "markers": report["markers"],
        "build_dir": str(OUT),
        "tftp_copy": str(tftp_copy),
        "flash": False,
        "router_mutations": False,
    }
    result_path = OUT / "build-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
