#!/usr/bin/env python3
"""Build F162 from stable F157 with read-only TQE forwarding counters."""
from __future__ import annotations

import hashlib
import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f122_5g_beacon_lifetime_from_f121 as f122
import build_f125_5g_assoc_window_guard_from_f124 as f125
import build_f143_5g_deferred_dma_free_from_f142 as engine
import build_f157_5g_persistent_bridge_from_f156 as f157
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f162-2g-tqe-readonly-from-f157"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F162_FROM_F157_2G_TQE_READONLY"

SRC_BUILD = f157.OUT
SRC_BASE = f157.BASE_OUT
MODULE_BUILD = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-tqe-readonly-f162-20260831"
NEW_SWITCH_TQE = (
    MODULE_BUILD
    / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/platform/topaz/switch_tqe.ko"
)
BUILD_PROFILE = MODULE_BUILD / "build-profile.env"
MODULE_MANIFEST = MODULE_BUILD / "module-manifest.tsv"

SWITCH_TQE_ENTRY = (
    "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/switch_tqe.ko"
)
CONTRACT_ENTRY = "usr/share/openmitrastar/radio5g/driver-contract.env"
HASHES_ENTRY = engine.HASHES_ENTRY
PAD_ENTRY = engine.PAD_ENTRY
QDRV_ENTRY = engine.QDRV_ENTRY
WLAN_ENTRY = engine.WLAN_ENTRY

OLD_SWITCH_TQE_SHA = "1f2e7e8abe9ce08571ca97fdc39123d0c7c146c09b8a1e0ae657b72487f2b8a1"
NEW_SWITCH_TQE_SHA = "bd5ab1018d293dc6bed655ec2bbc6da64a3969f28a3de578c04fa9c3f4af635f"
QDRV_SHA = f157.QDRV_SHA
WLAN_SHA = f157.WLAN_SHA


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def replacement_switch_tqe() -> bytes:
    if not NEW_SWITCH_TQE.is_file():
        raise SystemExit(f"missing F162 switch_tqe build: {NEW_SWITCH_TQE}")
    data = NEW_SWITCH_TQE.read_bytes()
    actual = sha256(data)
    if actual != NEW_SWITCH_TQE_SHA:
        raise SystemExit(f"F162 switch_tqe hash mismatch: {actual}")
    if b"omtqe-readonly-v1" not in data:
        raise SystemExit("F162 switch_tqe read-only counter marker missing")
    return data


def patch_contract(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    old = f"SWITCH_TQE_SHA256={OLD_SWITCH_TQE_SHA}"
    new = f"SWITCH_TQE_SHA256={NEW_SWITCH_TQE_SHA}"
    if text.count(old) != 1:
        raise SystemExit("F162 driver contract switch_tqe hash mismatch")
    patched = text.replace(old, new, 1).encode("ascii")
    return patched, {
        "entry": CONTRACT_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched),
        "old_switch_tqe_sha256": OLD_SWITCH_TQE_SHA,
        "new_switch_tqe_sha256": NEW_SWITCH_TQE_SHA,
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    new_switch_tqe = replacement_switch_tqe()
    replacements: dict[str, bytes] = {SWITCH_TQE_ENTRY: new_switch_tqe}
    patched_entries: list[f71.CpioEntry] = []
    seen: set[str] = set()
    pad_index = old_pad_size = None
    report: dict[str, object] = {
        "switch_tqe": {
            "entry": SWITCH_TQE_ENTRY,
            "old_sha256": OLD_SWITCH_TQE_SHA,
            "new_sha256": NEW_SWITCH_TQE_SHA,
            "old_bytes": None,
            "new_bytes": len(new_switch_tqe),
            "build_profile": str(BUILD_PROFILE.relative_to(ROOT)),
            "module_manifest": str(MODULE_MANIFEST.relative_to(ROOT)),
            "behavior": "read-only counters exposed through /sys/class/net/tqe/dbg",
        }
    }

    for entry in entries:
        if entry.name == SWITCH_TQE_ENTRY:
            actual = sha256(entry.data)
            if actual != OLD_SWITCH_TQE_SHA:
                raise SystemExit(f"F162 source switch_tqe hash mismatch: {actual}")
            report["switch_tqe"]["old_bytes"] = len(entry.data)
            patched_entries.append(f125.replace_entry(entry, new_switch_tqe))
            seen.add(entry.name)
        elif entry.name == CONTRACT_ENTRY:
            patched, item = patch_contract(entry.data)
            replacements[CONTRACT_ENTRY] = patched
            report["driver_contract"] = item
            patched_entries.append(f125.replace_entry(entry, patched))
            seen.add(entry.name)
        elif entry.name == PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)

    for required in (SWITCH_TQE_ENTRY, CONTRACT_ENTRY):
        if required not in seen:
            raise SystemExit(f"missing CPIO entry: {required}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {PAD_ENTRY}")

    final_entries: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            patched, hashes_patch = f122.patch_hashes(entry.data, replacements)
            final_entries.append(f125.replace_entry(entry, patched))
        else:
            final_entries.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {HASHES_ENTRY}")
    report["artifact_hashes"] = hashes_patch

    interim = b"".join(f71.serialize_entry(entry) for entry in final_entries)
    size_delta = start + len(interim) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F162 fixed-size padding cannot absorb delta={size_delta}")
    final_entries[pad_index] = f125.replace_entry(
        final_entries[pad_index], b"\0" * new_pad_size
    )

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in final_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _entries, new_remainder = f71.parse_first_cpio(result)
    if (
        new_start != start
        or new_remainder != remainder
        or len(result) != len(raw)
        or len(result) - len(new_remainder) != old_cpio_end
    ):
        raise SystemExit("F162 changed fixed payload layout")
    report["fixed_size_compensation"] = {
        "entry": PAD_ENTRY,
        "old_padding_bytes": old_pad_size,
        "new_padding_bytes": new_pad_size,
        "removed_bytes": size_delta,
        "raw_bytes_preserved": True,
        "cpio_end_preserved": True,
    }
    return result, report


def main() -> int:
    for required in (NEW_SWITCH_TQE, BUILD_PROFILE, MODULE_MANIFEST):
        if not required.is_file():
            raise SystemExit(f"missing input: {required}")

    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{SRC_BASE}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{SRC_BASE}.config"
    source_dtb = SRC_BUILD / f"{SRC_BASE}.dtb"
    source_vmlinux = SRC_BUILD / f"{SRC_BASE}.vmlinux"
    source_manifest = SRC_BUILD / "manifest.json"
    for required in (
        source_raw, source_uncompressed, source_config, source_dtb,
        source_vmlinux, source_manifest, f71.BOOTBASE, f71.LEGACY_LZMA,
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
        raise SystemExit("F162 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F162 webformat exceeds linux_live slot")

    entry_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_path) != 0:
        raise SystemExit("F162 persistent entry contract failed")
    contract = subprocess.run(
        [
            sys.executable, str(f71.BOOTBASE), "--candidate-slot", str(web_path),
            "--candidate-name", f"linux_live-{BUILD_TAG}", "--parts-dir", str(f71.PARTS_DIR),
        ],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if contract.returncode != 0:
        raise SystemExit(contract.stderr or contract.stdout)
    contract_path = OUT / "bootbase-contract.json"
    contract_path.write_text(contract.stdout, encoding="utf-8")
    bootbase = json.loads(contract.stdout)
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
            "base": "F157 stable dual-radio persistent bridge",
            "radio2g": "byte-identical to F157; F160/F161 diagnostics removed",
            "radio5": "qdrv, wlan, firmware, rates, queues, DMA and TX-BA policy unchanged",
            "switch_tqe": "only read-only packet-path counters added",
            "forwarding_behavior": "unchanged",
        },
        "runtime_policy": {
            "counter_path": "/sys/class/net/tqe/dbg",
            "counter_version": "omtqe-readonly-v1",
            "contains_mac_addresses": False,
            "persistent_flash_writes": 0,
        },
        "artifacts": {},
        "slot": {
            "name": "linux_live", "bytes": f71.SLOT_BYTES,
            "candidate_bytes": web_path.stat().st_size,
            "fits": web_path.stat().st_size <= f71.SLOT_BYTES,
        },
        "bootbase_contract": {
            "file": contract_path.name, "result": bootbase.get("result"),
            "candidate_accepted": bootbase.get("candidate_accepted"),
        },
        "persistent_entry_contract": {"file": entry_path.name, "result": "PASS"},
        "security": {"touches_router": False, "flash": False, "opens_uart": False},
    }
    paths = {
        "decompressed_payload": raw_path, "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path, "uimage": uimage_path, "webformat": web_path,
        "config": config_path, "dtb": dtb_path, "vmlinux": vmlinux_path,
    }
    for key, path in paths.items():
        item = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path.read_bytes())}
        if key == "webformat":
            item["crc32"] = f71.crc32(path.read_bytes())
        manifest["artifacts"][key] = item

    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    full_slot = web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f162-2g-tqe-readonly-from-f157-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": sha256(full_slot),
        "full_slot_crc32": f71.crc32(full_slot),
        "build_dir": str(OUT),
        "bootbase_result": bootbase.get("result"),
        "flash": False,
        "router_mutations": False,
    }
    result_path = OUT / "build-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sum_paths = [*paths.values(), contract_path, entry_path, manifest_path, result_path]
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in sum_paths),
        encoding="ascii",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
