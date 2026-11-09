#!/usr/bin/env python3
"""Offline verification for the full Q1 LZMA flash-sized candidate."""
from __future__ import annotations

import hashlib
import json
import lzma
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "work/mission-state/q1-lzma-flash-candidate/build"
SOURCE_BUILD = ROOT / "work/mission-state/q1-full-product/build"
BASE = "openmitrastar-linux510-q1-full-product-v1-LZMA-OFFLINE-NO-FLASH"
SOURCE_BASE = "openmitrastar-linux510-q1-full-product-v1-RAM-ONLY"
SLOT = 0x7A0000
RAS = 0x2000
EXPECTED_SOURCE_UIMAGE = "fb2fab1fb54b141ae1ba7e7a977437ed9e6cdded8d0131405249b570adde5887"
EXPECTED_SOURCE_WEB = "7a5ab53db4055fcbe0e9b55b300430fe669d461ca237469165f556fbaf1107ac"
EXPECTED_ENCODER = "04875199aab45068a183eededd351eb5abe4b39dfa6229c980e3e6e9f8d9ed18"


def sha(data_or_path: bytes | Path) -> str:
    data = data_or_path if isinstance(data_or_path, bytes) else data_or_path.read_bytes()
    return hashlib.sha256(data).hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def header(data: bytes) -> tuple[int | bytes, ...]:
    require(len(data) >= 64, "short uImage")
    values = struct.unpack(">7I4B32s", data[:64])
    require(values[0] == 0x27051956, "bad uImage magic")
    zero = bytearray(data[:64])
    zero[4:8] = b"\0\0\0\0"
    require(zlib.crc32(zero) & 0xFFFFFFFF == values[1], "bad uImage header CRC")
    return values


def main() -> int:
    source_uimage_path = SOURCE_BUILD / f"{SOURCE_BASE}.uImage"
    source_web_path = SOURCE_BUILD / f"{SOURCE_BASE}.webformat.bin"
    raw_path = BUILD / f"{BASE}.decompressed.bin"
    encoded_path = BUILD / f"{BASE}.lzma"
    uimage_path = BUILD / f"{BASE}.uImage"
    web_path = BUILD / f"{BASE}.webformat.bin"
    tftp_path = ROOT / "work/tftp/omvl/linux510-q1-full-product-v1-LZMA-RAM-TEST-NO-FLASH.bin"
    manifest = json.loads((BUILD / "manifest.json").read_text(encoding="utf-8"))
    contract = json.loads((BUILD / "bootbase-contract.json").read_text(encoding="utf-8"))
    layout = json.loads((BUILD / "ram-layout.json").read_text(encoding="utf-8"))

    require(sha(source_uimage_path) == EXPECTED_SOURCE_UIMAGE, "source uImage drift")
    require(sha(source_web_path) == EXPECTED_SOURCE_WEB, "source webformat drift")
    source = source_uimage_path.read_bytes()
    raw = raw_path.read_bytes()
    encoded = encoded_path.read_bytes()
    uimage = uimage_path.read_bytes()
    web = web_path.read_bytes()
    require(tftp_path.read_bytes() == web, "TFTP RAM-test copy differs from candidate")
    src = header(source)
    out = header(uimage)
    ras_header = header(web)

    require(source[64:] == raw, "decompressed payload is not exact source payload")
    require(lzma.decompress(encoded, format=lzma.FORMAT_ALONE) == raw,
            "LZMA round-trip differs from source payload")
    require(encoded[:5] == bytes.fromhex("5d00000002"),
            "LZMA properties/dictionary differ from OEM 32 MiB contract")
    require(int.from_bytes(encoded[5:13], "little") == len(raw),
            "LZMA exact output size is absent")
    require(out[3] == len(encoded) and len(uimage) == 64 + len(encoded),
            "compressed uImage size mismatch")
    require(out[4:6] == src[4:6], "load/entry not preserved")
    require(out[7] == 5 and out[8] == 0x13 and out[9] == 2 and out[10] == 3,
            "OEM ARC Linux LZMA header mismatch")
    require(zlib.crc32(encoded) & 0xFFFFFFFF == out[6], "uImage LZMA CRC mismatch")
    require(ras_header[3] == len(encoded), "RAS payload size mismatch")
    require(ras_header[4:11] == out[4:11], "RAS/uImage header fields differ")
    require(web[RAS:RAS + len(encoded)] == encoded, "RAS payload differs from LZMA stream")
    require(zlib.crc32(web[RAS:]) & 0xFFFFFFFF == ras_header[6], "RAS payload CRC mismatch")
    require(len(web) <= SLOT, "candidate exceeds linux_live")

    require(contract["accepted_by_contract"] is True, "Bootbase contract rejected")
    require(contract["errors"] == [], "Bootbase contract has errors")
    ch = contract["header"]
    require(ch["compression"] == 3, "contract did not identify LZMA")
    require(ch["lzma_declared_uncompressed_size"] == len(raw), "contract size mismatch")
    require(ch["lzma_decompressed_sha256"] == sha(raw), "contract decoded hash mismatch")

    require(layout["safe_offline"] is True, "unsafe RAM layout")
    require(layout["staging_decompression_disjoint"] is True, "staging/output overlap")
    require(layout["entry_inside_decompressed_image"] is True, "entry outside output")
    require(layout["probability_workspace_inside_ddr"] is True, "LZMA workspace outside DDR")

    require(manifest["classification"] ==
            "FLASH-SIZED-Q1-LZMA-CANDIDATE-HARDWARE-PENDING-NO-FLASH",
            "wrong classification")
    require(manifest["candidate_eligible"] is False, "unbooted candidate promoted")
    require(manifest["flash_supported"] is False, "unbooted candidate permits flash")
    require(manifest["slot"]["fits"] is True, "manifest slot fit false")
    require(manifest["slot"]["candidate_bytes"] == len(web), "manifest image size mismatch")
    require(manifest["compression"]["decoded_sha256"] == sha(raw), "manifest decoded hash mismatch")
    require(manifest["compression"]["legacy_encoder_sha256"] == EXPECTED_ENCODER,
            "legacy encoder drift")
    require(manifest["header"]["load_entry_preserved_from_q1"] is True,
            "manifest load/entry gate false")
    require(manifest["artifacts"]["tftp_copy"]["sha256"] == sha(web),
            "manifest TFTP hash mismatch")
    require(manifest["source_rootfs"]["sha256"] ==
            "ef2b1e162f3656410b4bb984199328e4dd6b2ddf5f9abc1fc99a6bbaa9c280a4",
            "Q1 derived rootfs binding drift")
    require(manifest["reproducibility"] == {
        "two_lzma_encodes_identical": True,
        "two_uimages_identical": True,
        "two_webformat_images_identical": True,
    }, "reproducibility gates incomplete")
    require(manifest["runtime_gates"]["exact_candidate_ram_boot"] == "pending",
            "hardware RAM boot claimed without evidence")
    require(manifest["runtime_gates"]["flash"].startswith("forbidden-"),
            "flash gate lost")
    require(manifest["ram_boot_contract"]["commands"] == [
        "tftpboot 0x83000000 linux510-q1-full-product-v1-LZMA-RAM-TEST-NO-FLASH.bin",
        "bootm 0x83000000",
    ], "exact RAM boot command drift")
    require(manifest["ram_boot_contract"]["flash_write"] is False,
            "RAM boot contract permits flash")

    print(
        "OMQ1_LZMA_OFFLINE_TEST_PASS "
        f"image_sha256={sha(web)} bytes={len(web)} spare={SLOT-len(web)} "
        f"decoded_sha256={sha(raw)} load=0x{out[4]:08x} entry=0x{out[5]:08x} "
        "bootbase=pass layout=safe hardware=0 flash=0"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AssertionError, KeyError, FileNotFoundError, json.JSONDecodeError, lzma.LZMAError) as exc:
        print(f"OMQ1_LZMA_OFFLINE_TEST_FAIL reason={exc}")
        raise SystemExit(1)
