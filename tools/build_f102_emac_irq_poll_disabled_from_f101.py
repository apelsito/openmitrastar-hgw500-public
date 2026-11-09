#!/usr/bin/env python3
"""Build F102 from F101 by disabling the Topaz EMAC IRQ poll fallback in DTB.

F101 has a working persistent Linux 5.10 + SSH + 2.4 GHz AP, but throughput
testing shows ``OMEMAC rx restart reason=stalled-cur-rx`` while IRQ20 still
progresses.  This candidate changes only the device-tree boolean property that
enables the EMAC poll fallback:

    qtn,irq-poll-fallback -> qtn,irq-poll-disabled

The replacement has the same byte length.  The initramfs CPIO, modules, loader
scripts, rates, queues, rings and Quantenna artifacts are not edited.
"""
from __future__ import annotations

import json
import lzma
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f102-emac-irq-poll-disabled-from-f101"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f101-2g-hwcrypto-from-f100/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f101-2g-hwcrypto-from-f100-LZMA-OFFLINE-NO-FLASH"

OLD_PROP = b"qtn,irq-poll-fallback"
NEW_PROP = b"qtn,irq-poll-disabled"
FDT_MAGIC = b"\xd0\x0d\xfe\xed"


def patch_fdt_property(blob: bytes, label: str) -> tuple[bytes, dict[str, object]]:
    if len(OLD_PROP) != len(NEW_PROP):
        raise SystemExit("F102 DTB replacement is not fixed-size")

    magic_offsets = [idx for idx in range(len(blob)) if blob.startswith(FDT_MAGIC, idx)]
    matches: list[dict[str, int]] = []
    patched = bytearray(blob)
    for magic in magic_offsets:
        if magic + 8 > len(blob):
            continue
        total_size = struct.unpack(">I", blob[magic + 4 : magic + 8])[0]
        if total_size <= 0 or magic + total_size > len(blob):
            continue
        fdt = blob[magic : magic + total_size]
        relative = fdt.find(OLD_PROP)
        while relative >= 0:
            absolute = magic + relative
            patched[absolute : absolute + len(OLD_PROP)] = NEW_PROP
            matches.append({"fdt_offset": magic, "total_size": total_size, "property_offset": absolute})
            relative = fdt.find(OLD_PROP, relative + 1)

    if len(matches) != 1:
        raise SystemExit(f"{label}: expected exactly one DTB property match, found {len(matches)}")
    if OLD_PROP in bytes(patched[matches[0]["fdt_offset"] : matches[0]["fdt_offset"] + matches[0]["total_size"]]):
        raise SystemExit(f"{label}: fallback property still present inside patched FDT")
    return bytes(patched), {
        "label": label,
        "old": OLD_PROP.decode("ascii"),
        "new": NEW_PROP.decode("ascii"),
        "matches": matches,
        "old_sha256": f71.sha256(blob),
        "new_sha256": f71.sha256(bytes(patched)),
        "bytes": len(blob),
        "delta_bytes": 0,
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{SRC_BASE}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{SRC_BASE}.config"
    source_dtb = SRC_BUILD / f"{SRC_BASE}.dtb"
    source_vmlinux = SRC_BUILD / f"{SRC_BASE}.vmlinux"
    source_manifest = SRC_BUILD / "manifest.json"
    source_result = SRC_BUILD / "build-result.json"
    for required in (
        source_raw,
        source_uncompressed,
        source_config,
        source_dtb,
        source_vmlinux,
        source_manifest,
        source_result,
        f71.TEMPLATE,
        f71.BOOTBASE,
        f71.LEGACY_LZMA,
    ):
        if not required.is_file():
            raise SystemExit(f"missing input: {required}")

    source_raw_bytes = source_raw.read_bytes()
    cpio_start, source_entries, source_remainder = f71.parse_first_cpio(source_raw_bytes)
    cpio_end = len(source_raw_bytes) - len(source_remainder)
    raw, raw_patch = patch_fdt_property(source_raw_bytes, "decompressed-payload")
    if raw[:cpio_end] != source_raw_bytes[:cpio_end]:
        raise SystemExit("F102 patch changed initramfs CPIO bytes")
    if len(raw) != len(source_raw_bytes):
        raise SystemExit("F102 patch changed decompressed payload size")

    dtb, dtb_patch = patch_fdt_property(source_dtb.read_bytes(), "copied-dtb")
    raw_path = OUT / f"{BASE_OUT}.decompressed.bin"
    uncompressed_path = OUT / f"{BASE_OUT}.uncompressed.uImage"
    lzma_path = OUT / f"{BASE_OUT}.lzma"
    uimage_path = OUT / f"{BASE_OUT}.uImage"
    web_path = OUT / f"{BASE_OUT}.webformat.bin"
    config_path = OUT / f"{BASE_OUT}.config"
    dtb_path = OUT / f"{BASE_OUT}.dtb"
    vmlinux_path = OUT / f"{BASE_OUT}.vmlinux"

    raw_path.write_bytes(raw)
    dtb_path.write_bytes(dtb)
    shutil.copy2(source_config, config_path)
    shutil.copy2(source_vmlinux, vmlinux_path)
    f71.write_uimage(source_uncompressed, raw, uncompressed_path, compression=0)
    encoded = f71.encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
        raise SystemExit("F102 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F102 webformat exceeds linux_live slot")

    contract = subprocess.run(
        [
            sys.executable,
            str(f71.BOOTBASE),
            "--candidate-slot",
            str(web_path),
            "--candidate-name",
            f"linux_live-{BUILD_TAG}",
            "--parts-dir",
            str(f71.PARTS_DIR),
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

    tftp_copy = ROOT / "work/tftp/omvl" / web_path.name
    tftp_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(web_path, tftp_copy)

    artifacts = {
        "rootfs": raw_path,
        "decompressed_payload": raw_path,
        "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "kconfig": config_path,
        "dtb": dtb_path,
        "vmlinux": vmlinux_path,
    }
    source_manifest_json = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_result_json = json.loads(source_result.read_text(encoding="utf-8"))
    cpio_names = sorted(entry.name for entry in source_entries)
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f102-emac-irq-poll-disabled-from-f101/v1",
        "classification": "F102_FROM_F101_EMAC_DTB_IRQ_POLL_FALLBACK_DISABLED_FIXEDSIZE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
            "candidate_sha256": source_result_json["candidate_sha256"],
            "full_slot_crc32": source_result_json["full_slot_crc32"],
        },
        "change_scope": {
            "emac_dtb": "changed only qtn,irq-poll-fallback to qtn,irq-poll-disabled in embedded FDT and copied .dtb",
            "initramfs_cpio": "unchanged byte-for-byte",
            "radio2g_modules": "unchanged from F101",
            "radio2g_loader_rates_crypto": "unchanged from F101",
            "radio5_modules": "unchanged from F101",
            "qdrv": "unchanged from F101",
            "queues_dma_rings_bridge": "unchanged from F101",
            "flash_layout": "unchanged",
        },
        "patch": {
            "raw": raw_patch,
            "dtb": dtb_patch,
            "cpio": {
                "start": cpio_start,
                "end": cpio_end,
                "bytes": cpio_end - cpio_start,
                "entry_count": len(cpio_names),
                "sha256_before": f71.sha256(source_raw_bytes[:cpio_end]),
                "sha256_after": f71.sha256(raw[:cpio_end]),
                "unchanged": raw[:cpio_end] == source_raw_bytes[:cpio_end],
            },
        },
        "artifacts": {
            key: {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": f71.sha256(path.read_bytes()),
                **({"crc32": f71.crc32(path.read_bytes())} if key == "webformat" else {}),
            }
            for key, path in artifacts.items()
        },
        "rootfs": {
            "rootfs": {
                "file": raw_path.name,
                "bytes": raw_path.stat().st_size,
                "sha256": f71.sha256(raw_path.read_bytes()),
            }
        },
        "slot": {
            "name": "linux_live",
            "bytes": f71.SLOT_BYTES,
            "candidate_bytes": web_path.stat().st_size,
            "fits": web_path.stat().st_size <= f71.SLOT_BYTES,
        },
        "bootbase_contract": {
            "file": contract_path.name,
            "result": contract_json.get("result"),
            "candidate_accepted": contract_json.get("candidate", {}).get("accepted_by_contract"),
        },
        "security": {"touches_router": False, "opens_uart": False, "flash": False},
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

    full_slot = web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f102-emac-irq-poll-disabled-from-f101-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": f71.sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": f71.sha256(full_slot),
        "full_slot_crc32": f71.crc32(full_slot),
        "build_dir": str(OUT),
        "tftp_copy": str(tftp_copy),
        "patch": manifest["patch"],
        "bootbase_result": contract_json.get("result"),
        "flash": False,
        "router_mutations": False,
    }
    result_path = OUT / "build-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")

    with (OUT / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as fh:
        for path in sorted([*artifacts.values(), contract_path, manifest_path, result_path], key=lambda item: item.name):
            fh.write(f"{f71.sha256(path.read_bytes())}  {path.name}\n")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
