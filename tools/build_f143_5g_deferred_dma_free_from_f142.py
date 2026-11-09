#!/usr/bin/env python3
"""Build F143 from F142 with IRQ-safe deferred hostlink DMA frees."""
from __future__ import annotations

import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f125_5g_assoc_window_guard_from_f124 as f125
import build_f142_5g_disassoc_atomic_from_f141 as f142
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f143-5g-deferred-dma-free-from-f142"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F143_FROM_F142_5G_DEFERRED_DMA_FREE"

SRC_BUILD = f142.OUT
SRC_BASE = f142.BASE_OUT
START_ENTRY = f142.START_ENTRY
HASHES_ENTRY = f142.HASHES_ENTRY
PAD_ENTRY = f142.PAD_ENTRY
QDRV_ENTRY = f142.QDRV_ENTRY
WLAN_ENTRY = f142.WLAN_ENTRY
DRIVER_CONTRACT_ENTRY = f142.DRIVER_CONTRACT_ENTRY

OLD_QDRV_SHA = "92381049063ec04d4e6e744c340345a1f1cb2feea18d4c7765a3b35b9f22d343"
NEW_QDRV_SHA = "db498a534bf388f2e0ddf75e6802c99fb868e9dc6e9a4e3a56f5ab69f785a8e9"
WLAN_SHA = f142.WLAN_SHA
NEW_QDRV = (
    ROOT
    / "outputs/kernel-port/quantenna-linux510-radiohw-deferred-free-f143-20260830"
    / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
)
BUILD_PROFILE = NEW_QDRV.parents[7] / "build-profile.env"
MODULE_MANIFEST = NEW_QDRV.parents[7] / "module-manifest.tsv"


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def replacement_qdrv() -> bytes:
    if not NEW_QDRV.is_file():
        raise SystemExit(f"missing F143 qdrv build: {NEW_QDRV}")
    data = NEW_QDRV.read_bytes()
    actual = sha256(data)
    if actual != NEW_QDRV_SHA:
        raise SystemExit(f"F143 rebuilt qdrv hash mismatch: {actual}")
    for marker in (
        b"OMQDRVHLINK stage=free-deferred",
        b"OMQDRVHLINK stage=free-defer-alloc-failed",
        b"OMQDRVHR stage=timer-disabled reason=hgw-v89",
    ):
        if marker not in data:
            raise SystemExit(f"F143 rebuilt qdrv missing marker: {marker!r}")
    return data


def patch_start(data: bytes, qdrv_hash: str) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if OLD_QDRV_SHA not in text:
        raise SystemExit("F143 start script missing F142 qdrv hash")
    patched = text.replace(OLD_QDRV_SHA, qdrv_hash)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "old_qdrv_sha256": OLD_QDRV_SHA,
        "new_qdrv_sha256": qdrv_hash,
        "fixes": [
            "keeps F142 RF/VAP/userspace ordering and TX-power behavior",
            "updates the qdrv integrity expectation for the rebuilt IRQ-safe driver",
            "does not change 2.4 GHz, rates, rings, forwarding, bridge topology or auc_tx",
        ],
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    new_qdrv = replacement_qdrv()
    qdrv_hash = sha256(new_qdrv)
    patched_entries: list[f71.CpioEntry] = []
    replacements: dict[str, bytes] = {QDRV_ENTRY: new_qdrv}
    patch_report: dict[str, object] = {
        "qdrv": {
            "entry": QDRV_ENTRY,
            "old_sha256": OLD_QDRV_SHA,
            "new_sha256": qdrv_hash,
            "old_bytes": None,
            "new_bytes": len(new_qdrv),
            "build_profile": str(BUILD_PROFILE.relative_to(ROOT)),
            "module_manifest": str(MODULE_MANIFEST.relative_to(ROOT)),
            "fixes": [
                "defer hostlink coherent DMA frees to process context when called from interrupt context or with IRQs disabled",
                "retain GFP_DMA | GFP_ATOMIC for DISASSOC payload allocation",
                "disable the legacy qdrv hang-recovery timer on HGW-500BNA-QCv2 before timer_setup/mod_timer",
            ],
        }
    }
    pad_index = old_pad_size = None
    seen: set[str] = set()

    for entry in entries:
        if entry.name == QDRV_ENTRY:
            actual = sha256(entry.data)
            if actual != OLD_QDRV_SHA:
                raise SystemExit(f"F143 source qdrv hash mismatch: {actual}")
            patch_report["qdrv"]["old_bytes"] = len(entry.data)
            patched_entries.append(f125.replace_entry(entry, new_qdrv))
            seen.add(entry.name)
        elif entry.name == START_ENTRY:
            start_data, start_patch = patch_start(entry.data, qdrv_hash)
            replacements[START_ENTRY] = start_data
            patch_report["start_script"] = start_patch
            patched_entries.append(f125.replace_entry(entry, start_data))
            seen.add(entry.name)
        elif entry.name == DRIVER_CONTRACT_ENTRY:
            contract_data, contract_patch = f122.patch_driver_contract(
                entry.data, qdrv_hash, WLAN_SHA
            )
            replacements[DRIVER_CONTRACT_ENTRY] = contract_data
            patch_report["driver_contract"] = contract_patch
            patched_entries.append(f125.replace_entry(entry, contract_data))
            seen.add(entry.name)
        elif entry.name == PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)

    for required in (QDRV_ENTRY, START_ENTRY, DRIVER_CONTRACT_ENTRY):
        if required not in seen:
            raise SystemExit(f"missing CPIO entry: {required}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {PAD_ENTRY}")

    hashed_entries: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            hashes_data, hashes_patch = f122.patch_hashes(entry.data, replacements)
            hashed_entries.append(f125.replace_entry(entry, hashes_data))
        else:
            hashed_entries.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {HASHES_ENTRY}")
    patched_entries = hashed_entries
    patch_report["artifact_hashes"] = hashes_patch

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim_cpio) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F143 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}")
    patched_entries[pad_index] = f125.replace_entry(
        patched_entries[pad_index], b"\0" * new_pad_size
    )

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F143 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F143 changed CPIO end")

    patch_report["cpio"] = {
        "start": start,
        "old_end": old_cpio_end,
        "new_end": new_cpio_end,
        "old_raw_bytes": len(raw),
        "new_raw_bytes": len(result),
        "delta_bytes": 0,
        "uncompensated_delta_bytes": size_delta,
        "remainder_bytes": len(remainder),
        "remainder_sha256": sha256(remainder),
    }
    patch_report["fixed_size_compensation"] = {
        "entry": PAD_ENTRY,
        "old_padding_bytes": old_pad_size,
        "new_padding_bytes": new_pad_size,
        "removed_bytes": size_delta,
        "raw_bytes_preserved": True,
        "cpio_end_preserved": True,
    }
    return result, patch_report


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{SRC_BASE}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{SRC_BASE}.config"
    source_dtb = SRC_BUILD / f"{SRC_BASE}.dtb"
    source_vmlinux = SRC_BUILD / f"{SRC_BASE}.vmlinux"
    source_manifest = SRC_BUILD / "manifest.json"
    for required in (
        source_raw,
        source_uncompressed,
        source_config,
        source_dtb,
        source_vmlinux,
        source_manifest,
        NEW_QDRV,
        BUILD_PROFILE,
        MODULE_MANIFEST,
        f71.BOOTBASE,
        f71.LEGACY_LZMA,
    ):
        if not required.is_file():
            raise SystemExit(f"missing input: {required}")

    raw, patch_report = patch_cpio(source_raw.read_bytes())
    raw_path = OUT / f"{BASE_OUT}.decompressed.bin"
    uncompressed_path = OUT / f"{BASE_OUT}.uncompressed.uImage"
    lzma_path = OUT / f"{BASE_OUT}.lzma"
    uimage_path = OUT / f"{BASE_OUT}.uImage"
    web_path = OUT / f"{BASE_OUT}.webformat.bin"
    config_path = OUT / f"{BASE_OUT}.config"
    dtb_path = OUT / f"{BASE_OUT}.dtb"
    vmlinux_path = OUT / f"{BASE_OUT}.vmlinux"

    raw_path.write_bytes(raw)
    shutil.copy2(source_config, config_path)
    shutil.copy2(source_dtb, dtb_path)
    shutil.copy2(source_vmlinux, vmlinux_path)
    f71.write_uimage(source_uncompressed, raw, uncompressed_path, compression=0)
    encoded = f71.encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
        raise SystemExit("F143 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F143 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F143 persistent entry contract failed")

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
    bootbase_contract = json.loads(contract.stdout)

    source_manifest_data = json.loads(source_manifest.read_text(encoding="ascii"))
    manifest = {
        "schema": f"openmitrastar.q3-persistent-composite-{BUILD_TAG}/v1",
        "classification": CLASSIFICATION,
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_data["artifacts"]["webformat"]["sha256"],
            "raw_sha256": source_manifest_data["artifacts"]["decompressed_payload"]["sha256"],
        },
        "patch": patch_report,
        "change_scope": {
            "radio2g": "unchanged from F142",
            "radio5_start": "unchanged from F142 except qdrv integrity hash",
            "radio5_stop": "unchanged from F142",
            "radio5_modules": "only qdrv.ko replaced from the verified 25-module build",
            "qdrv": "rebuilt with deferred hostlink DMA free and source-level HGW HR timer disable",
            "wlan": "unchanged from F142",
            "rates_rings_forwarding_auc_tx": "unchanged from F142",
            "bridge_topology": "unchanged from F142",
        },
        "runtime_policy": {
            "hr_timer": "disabled for HGW-500BNA-QCv2 before timer setup",
            "disassoc_dma_allocation": "GFP_DMA | GFP_ATOMIC",
            "hostlink_dma_free": "deferred to system workqueue from interrupt/IRQ-disabled context",
            "expected_effect": "remove dma_free_coherent IRQ warnings and management stalls after association/disassociation",
            "persistent_flash_writes": 0,
        },
        "artifacts": {},
        "slot": {
            "name": "linux_live",
            "bytes": f71.SLOT_BYTES,
            "candidate_bytes": web_path.stat().st_size,
            "fits": web_path.stat().st_size <= f71.SLOT_BYTES,
        },
        "bootbase_contract": {
            "file": contract_path.name,
            "result": bootbase_contract.get("result"),
            "candidate_accepted": bootbase_contract.get("candidate_accepted"),
        },
        "persistent_entry_contract": {
            "file": entry_contract_path.name,
            "result": "PASS",
        },
        "security": {"touches_router": False, "flash": False, "opens_uart": False},
    }
    for key, path in {
        "decompressed_payload": raw_path,
        "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "config": config_path,
        "dtb": dtb_path,
        "vmlinux": vmlinux_path,
    }.items():
        item = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path.read_bytes())}
        if key == "webformat":
            item["crc32"] = f71.crc32(path.read_bytes())
        manifest["artifacts"][key] = item

    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sum_paths = [
        raw_path, uncompressed_path, lzma_path, uimage_path, web_path,
        config_path, dtb_path, vmlinux_path, contract_path,
        entry_contract_path, manifest_path,
    ]
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in sum_paths),
        encoding="ascii",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
