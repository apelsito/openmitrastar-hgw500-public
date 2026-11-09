#!/usr/bin/env python3
"""Build F133 from F132 by disabling qdrv's HR one-shot timer at init."""
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
import build_f132_5g_hrflags_skip_epilogue_from_f129 as f132
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f133-5g-disable-hr-timer-from-f132"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F133_FROM_F132_5G_DISABLE_HR_TIMER"

SRC_BUILD = f132.OUT
SRC_BASE = f132.BASE_OUT
START_ENTRY = f132.base.START_ENTRY
HASHES_ENTRY = f132.base.HASHES_ENTRY
PAD_ENTRY = f132.base.PAD_ENTRY
QDRV_ENTRY = f132.base.QDRV_ENTRY
WLAN_ENTRY = f132.base.WLAN_ENTRY
DRIVER_CONTRACT_ENTRY = f132.base.DRIVER_CONTRACT_ENTRY

OLD_QDRV_SHA = "768aa153d4977a7fe75145f2793eb7c0632b4ee94f6abffdfdcea4df72a64127"
QDRV_HR_TIMER_FILE_OFF = 0x240C4
OLD_HR_TIMER_BLOCK = bytes.fromhex(
    "00 26 8f 1f 00 00 48 76"
    "4a 24 00 00 00 db 00 da"
    "0a 21 80 0f 00 00 00 00"
    "e9 70 22 20 80 0f 00 00 00 00"
    "00 16 01 70 00 00 00 00"
    "e9 70 95 21 c1 02"
    "22 20 80 0f 00 00 00 00"
)
NEW_BRANCH_OVER_HR_TIMER = bytes.fromhex("1c f0")
START_LOG_INSERT_AFTER = (
    "[ \"$(sha256sum \"$loader\" 2>/dev/null | awk '{ print $1 }')\" = \"$expected_loader_sha\" ] || "
    "refuse ram-insmod-contract\n"
)
START_LOG_LINE = "log 'OMRADIO5_HR_TIMER_POLICY disabled-in-qdrv-init source=f133'\n"


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def patch_qdrv(data: bytes) -> tuple[bytes, dict[str, object]]:
    actual = sha256(data)
    if actual != OLD_QDRV_SHA:
        raise SystemExit(f"F133 qdrv input hash mismatch: {actual}")
    got = data[QDRV_HR_TIMER_FILE_OFF:QDRV_HR_TIMER_FILE_OFF + len(OLD_HR_TIMER_BLOCK)]
    if got != OLD_HR_TIMER_BLOCK:
        raise SystemExit(
            "F133 qdrv HR timer block guard mismatch: "
            f"got={got[:16].hex()} expected={OLD_HR_TIMER_BLOCK[:16].hex()}"
        )
    patched = bytearray(data)
    patched[QDRV_HR_TIMER_FILE_OFF:QDRV_HR_TIMER_FILE_OFF + len(NEW_BRANCH_OVER_HR_TIMER)] = (
        NEW_BRANCH_OVER_HR_TIMER
    )
    result = bytes(patched)
    return result, {
        "entry": QDRV_ENTRY,
        "old_sha256": OLD_QDRV_SHA,
        "new_sha256": sha256(result),
        "old_bytes": len(data),
        "new_bytes": len(result),
        "branch_patch": {
            "file_offset": QDRV_HR_TIMER_FILE_OFF,
            "start_vma": "0x24090",
            "target_vma": "0x240c8",
            "old_bytes_hex": OLD_HR_TIMER_BLOCK.hex(),
            "new_bytes_hex": NEW_BRANCH_OVER_HR_TIMER.hex(),
            "effect": "branch over timer_setup and mod_timer in qdrv_wlan_init, leaving HR one-shot unarmed",
        },
    }


def patch_start(data: bytes, qdrv_hash: str) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if OLD_QDRV_SHA not in text:
        raise SystemExit("F133 start script missing old qdrv hash")
    patched = text.replace(OLD_QDRV_SHA, qdrv_hash)
    if START_LOG_LINE not in patched:
        if START_LOG_INSERT_AFTER not in patched:
            raise SystemExit("F133 start script missing HR policy insertion point")
        patched = patched.replace(START_LOG_INSERT_AFTER, START_LOG_INSERT_AFTER + START_LOG_LINE, 1)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "old_qdrv_sha256": OLD_QDRV_SHA,
        "new_qdrv_sha256": qdrv_hash,
        "fixes": [
            "keeps F132 RF/VAP/userspace ordering",
            "updates the qdrv integrity expectation for the HR-timer-disabled qdrv",
            "logs the F133 HR timer policy before radio control sequencing",
            "does not change 2.4 GHz, queues, DMA, rates, rings, forwarding, bridge topology or auc_tx",
        ],
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    pad_index = old_pad_size = None
    seen: set[str] = set()
    replacements: dict[str, bytes] = {}
    patch_report: dict[str, object] = {}

    qdrv_hash = None
    for entry in entries:
        if entry.name == QDRV_ENTRY:
            qdrv_data, qdrv_patch = patch_qdrv(entry.data)
            qdrv_hash = sha256(qdrv_data)
            replacements[QDRV_ENTRY] = qdrv_data
            patch_report["qdrv"] = qdrv_patch
            break
    if qdrv_hash is None:
        raise SystemExit(f"missing CPIO entry: {QDRV_ENTRY}")

    for entry in entries:
        if entry.name == QDRV_ENTRY:
            patched_entries.append(f125.replace_entry(entry, replacements[QDRV_ENTRY]))
            seen.add(entry.name)
        elif entry.name == START_ENTRY:
            start_data, start_patch = patch_start(entry.data, qdrv_hash)
            replacements[START_ENTRY] = start_data
            patch_report["start_script"] = start_patch
            patched_entries.append(f125.replace_entry(entry, start_data))
            seen.add(entry.name)
        elif entry.name == DRIVER_CONTRACT_ENTRY:
            contract_data, contract_patch = f122.patch_driver_contract(
                entry.data, qdrv_hash, f122.NEW_WLAN_SHA
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

    patched_entries_2: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            hashes_data, hashes_patch = f122.patch_hashes(entry.data, replacements)
            patched_entries_2.append(f125.replace_entry(entry, hashes_data))
        else:
            patched_entries_2.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {HASHES_ENTRY}")
    patched_entries = patched_entries_2
    patch_report["artifact_hashes"] = hashes_patch

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim_cpio) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F133 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}")
    patched_entries[pad_index] = f125.replace_entry(patched_entries[pad_index], b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F133 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F133 changed CPIO end")

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
        raise SystemExit("F133 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F133 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F133 persistent entry contract failed")

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
            "radio2g": "unchanged from F132",
            "radio5_start": "unchanged from F132 except qdrv integrity hash and HR timer policy log",
            "radio5_stop": "unchanged from F132",
            "radio5_modules": "qdrv.ko patched in-place to skip qdrv_wlan_init HR timer setup/mod_timer",
            "qdrv": "binary in-place HR one-shot timer disabled before callback scheduling",
            "wlan": "unchanged from F132",
            "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F132",
            "bridge_topology": "unchanged from F132",
        },
        "runtime_policy": {
            "hr_timer": "not armed on qdrv_wlan_init",
            "hrflags_callback": "still skipped from F132 if somehow invoked",
            "rf_before_vap": False,
            "association_window_auto_stop": False,
            "persistent_flash_writes": 0,
        },
        "artifacts": {
            "decompressed_payload": {
                "file": raw_path.name,
                "bytes": raw_path.stat().st_size,
                "sha256": sha256(raw_path.read_bytes()),
            },
            "uncompressed_uimage": {
                "file": uncompressed_path.name,
                "bytes": uncompressed_path.stat().st_size,
                "sha256": sha256(uncompressed_path.read_bytes()),
            },
            "lzma": {
                "file": lzma_path.name,
                "bytes": lzma_path.stat().st_size,
                "sha256": sha256(lzma_path.read_bytes()),
            },
            "uimage": {
                "file": uimage_path.name,
                "bytes": uimage_path.stat().st_size,
                "sha256": sha256(uimage_path.read_bytes()),
            },
            "webformat": {
                "file": web_path.name,
                "bytes": web_path.stat().st_size,
                "sha256": sha256(web_path.read_bytes()),
                "crc32": f71.crc32(web_path.read_bytes()),
            },
            "config": {
                "file": config_path.name,
                "bytes": config_path.stat().st_size,
                "sha256": sha256(config_path.read_bytes()),
            },
            "dtb": {
                "file": dtb_path.name,
                "bytes": dtb_path.stat().st_size,
                "sha256": sha256(dtb_path.read_bytes()),
            },
            "vmlinux": {
                "file": vmlinux_path.name,
                "bytes": vmlinux_path.stat().st_size,
                "sha256": sha256(vmlinux_path.read_bytes()),
            },
        },
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
        "security": {
            "touches_router": False,
            "flash": False,
            "opens_uart": False,
        },
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

    sha_lines = []
    for path in (
        raw_path,
        uncompressed_path,
        lzma_path,
        uimage_path,
        web_path,
        config_path,
        dtb_path,
        vmlinux_path,
        contract_path,
        entry_contract_path,
        manifest_path,
    ):
        sha_lines.append(f"{sha256(path.read_bytes())}  {path.name}\n")
    (OUT / "SHA256SUMS").write_text("".join(sha_lines), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
