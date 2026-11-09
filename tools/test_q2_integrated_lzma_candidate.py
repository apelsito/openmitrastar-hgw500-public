#!/usr/bin/env python3
"""Offline contract for the isolated Q2 integrated LZMA candidate."""
from __future__ import annotations

import hashlib
import json
import lzma
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "work/mission-state/q2-integrated-lzma-candidate"
BUILD = LANE / "build"
ROOTFS_BUILD = LANE / "rootfs-build"
BASE = "openmitrastar-linux510-q2-parity-v1-LZMA-OFFLINE-NO-FLASH"
SLOT = 0x7A0000
Q1_ROOTFS = ROOT / "work/mission-state/q1-full-product/rootfs-build/openmitrastar-q1-full-product-rootfs-v1.squashfs"
Q1_UIMAGE = ROOT / "work/mission-state/q1-full-product/build/openmitrastar-linux510-q1-full-product-v1-RAM-ONLY.uImage"
Q1_WEB = ROOT / "work/mission-state/q1-full-product/build/openmitrastar-linux510-q1-full-product-v1-RAM-ONLY.webformat.bin"
Q1_LZMA = ROOT / "work/mission-state/q1-lzma-flash-candidate/build/openmitrastar-linux510-q1-full-product-v1-LZMA-OFFLINE-NO-FLASH.webformat.bin"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(value: bool, message: str) -> None:
    if not value:
        raise AssertionError(message)


def header(blob: bytes) -> tuple[int | bytes, ...]:
    require(len(blob) >= 64, "short uImage")
    values = struct.unpack(">7I4B32s", blob[:64])
    require(values[0] == 0x27051956, "bad uImage magic")
    zeroed = bytearray(blob[:64])
    zeroed[4:8] = b"\0\0\0\0"
    require(zlib.crc32(zeroed) & 0xFFFFFFFF == values[1], "bad uImage header CRC")
    return values


def main() -> int:
    manifest = json.loads((BUILD / "manifest.json").read_text(encoding="utf-8"))
    contract = json.loads((BUILD / "bootbase-contract.json").read_text(encoding="utf-8"))
    layout = json.loads((BUILD / "ram-layout.json").read_text(encoding="utf-8"))
    rootmeta = json.loads((ROOTFS_BUILD / "manifest.json").read_text(encoding="utf-8"))
    rootfs = ROOTFS_BUILD / rootmeta["rootfs"]["file"]
    raw = BUILD / f"{BASE}.decompressed.bin"
    encoded = BUILD / f"{BASE}.lzma"
    source = BUILD / f"{BASE}.uncompressed.uImage"
    uimage = BUILD / f"{BASE}.uImage"
    web = BUILD / f"{BASE}.webformat.bin"
    tftp = ROOT / "work/tftp/omvl/linux510-q2-parity-v1-LZMA-RAM-TEST-NO-FLASH.bin"

    require(manifest["schema"] == "openmitrastar.q2-integrated-lzma-candidate/v1", "schema")
    require(manifest["candidate_eligible"] is False and manifest["flash_supported"] is False, "classification")
    require(manifest["hardware_actions"] is False, "hardware boundary")
    require(rootmeta["capabilities"]["backup_restore"] is True, "backup/restore missing")
    require(rootmeta["capabilities"]["https_443_optional_external_pem"] is True, "HTTPS missing")
    require(rootmeta["capabilities"]["getinfo_16667"] is True, "getinfo missing")
    require(rootmeta["capabilities"]["w3_no_ioss_route_embedded"] is True, "W3 no-IOSS missing")
    require(rootmeta["security"]["ioss_reset_pulse_forbidden"] is True, "IOSS pulse not forbidden")
    require(rootmeta["security"]["psk_bundled"] is False, "PSK bundled")
    require(rootmeta["security"]["https_pem_bundled"] is False, "PEM bundled")

    require(sha(Q1_ROOTFS) == "ef2b1e162f3656410b4bb984199328e4dd6b2ddf5f9abc1fc99a6bbaa9c280a4", "Q1 rootfs changed")
    require(sha(Q1_UIMAGE) == "fb2fab1fb54b141ae1ba7e7a977437ed9e6cdded8d0131405249b570adde5887", "Q1 uImage changed")
    require(sha(Q1_WEB) == "7a5ab53db4055fcbe0e9b55b300430fe669d461ca237469165f556fbaf1107ac", "Q1 web changed")
    require(sha(Q1_LZMA) == "bd473ef7f7238a5f9488e4739308615355c7e86526c5c867e16d3a232908c306", "Q1 LZMA changed")

    raw_blob = raw.read_bytes()
    encoded_blob = encoded.read_bytes()
    source_blob = source.read_bytes()
    uimage_blob = uimage.read_bytes()
    web_blob = web.read_bytes()
    src = header(source_blob)
    out = header(uimage_blob)
    require(source_blob[64:] == raw_blob, "raw payload drift")
    require(lzma.decompress(encoded_blob, format=lzma.FORMAT_ALONE) == raw_blob, "LZMA round trip")
    require(encoded_blob[:5] == bytes.fromhex("5d00000002"), "OEM LZMA dictionary")
    require(int.from_bytes(encoded_blob[5:13], "little") == len(raw_blob), "LZMA size")
    require(out[4:6] == src[4:6] and out[10] == 3, "load/entry/compression")
    require(zlib.crc32(encoded_blob) & 0xFFFFFFFF == out[6], "payload CRC")
    require(tftp.read_bytes() == web_blob, "TFTP differs")
    require(len(web_blob) <= SLOT, "slot overflow")
    require(contract["accepted_by_contract"] is True and contract["errors"] == [], "Bootbase contract")
    require(layout["safe_offline"] is True, "RAM layout")
    require(manifest["slot"]["spare_bytes"] == SLOT - len(web_blob), "slot accounting")
    require(manifest["reproducibility"]["kernel_two_incremental_trees_identical"] is True, "kernel reproducibility")
    require(sha(rootfs) == rootmeta["rootfs"]["sha256"], "rootfs manifest")

    print(
        "OMQ2_INTEGRATED_LZMA_OFFLINE_PASS "
        f"sha256={sha(web)} bytes={web.stat().st_size} spare={SLOT-web.stat().st_size} "
        f"rootfs_sha256={sha(rootfs)} backup_restore=1 https=443 getinfo=16667 "
        "w3_no_ioss=1 q1_unchanged=1 hardware=0 flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
