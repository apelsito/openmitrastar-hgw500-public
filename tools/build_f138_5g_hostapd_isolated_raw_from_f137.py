#!/usr/bin/env python3
"""Build F138 from F137 with the isolated-VAP hostapd raw socket fix."""
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
import build_f137_5g_post_hostapd_rearm_from_f136 as f137
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f138-5g-hostapd-isolated-raw-from-f137"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F138_FROM_F137_5G_HOSTAPD_ISOLATED_RAW_SOCKET"

SRC_BUILD = f137.OUT
SRC_BASE = f137.BASE_OUT
HASHES_ENTRY = f137.HASHES_ENTRY
PAD_ENTRY = f137.PAD_ENTRY
HOSTAPD_ENTRY = "usr/sbin/hostapd-qtn"
HOSTAPD_ARTIFACT = (
    ROOT / "outputs/kernel-port/qtn-hostapd-madwifi-v6-isolated-raw-20260830/hostapd"
)
OLD_HOSTAPD_SHA = "3d9e89809bef74711f7e77addbbfdc6892245020accd7ab11605a7420ffd3f7e"
NEW_HOSTAPD_SHA = "c09be994585d0afbb7755bba9614ffd511833cfa2fa928df8d6114875fed8a6d"
HOSTAPD_MARKER = b"OMHAPD raw-probe-socket"


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    hostapd = HOSTAPD_ARTIFACT.read_bytes()
    if sha256(hostapd) != NEW_HOSTAPD_SHA:
        raise SystemExit("F138 hostapd artifact hash mismatch")
    if HOSTAPD_MARKER not in hostapd:
        raise SystemExit("F138 hostapd marker missing")

    replacements = {HOSTAPD_ENTRY: hostapd}
    patched_entries: list[f71.CpioEntry] = []
    hostapd_patch = None
    pad_index = old_pad_size = None

    for entry in entries:
        if entry.name == HOSTAPD_ENTRY:
            old_hash = sha256(entry.data)
            if old_hash != OLD_HOSTAPD_SHA:
                raise SystemExit(f"F138 hostapd input hash mismatch: {old_hash}")
            hostapd_patch = {
                "entry": HOSTAPD_ENTRY,
                "old_sha256": old_hash,
                "new_sha256": NEW_HOSTAPD_SHA,
                "old_bytes": len(entry.data),
                "new_bytes": len(hostapd),
                "marker": HOSTAPD_MARKER.decode("ascii"),
            }
            patched_entries.append(f125.replace_entry(entry, hostapd))
        elif entry.name == PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)
    if hostapd_patch is None:
        raise SystemExit(f"missing CPIO entry: {HOSTAPD_ENTRY}")
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

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim_cpio) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(
            f"F138 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}"
        )
    patched_entries[pad_index] = f125.replace_entry(
        patched_entries[pad_index], b"\0" * new_pad_size
    )

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    new_map = {entry.name: entry.data for entry in new_entries}
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F138 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F138 changed CPIO end")
    if sha256(new_map[HOSTAPD_ENTRY]) != NEW_HOSTAPD_SHA:
        raise SystemExit("F138 embedded hostapd verification failed")

    return result, {
        "hostapd": hostapd_patch,
        "artifact_hashes": hashes_patch,
        "cpio": {
            "start": start,
            "old_end": old_cpio_end,
            "new_end": new_cpio_end,
            "old_raw_bytes": len(raw),
            "new_raw_bytes": len(result),
            "delta_bytes": 0,
            "uncompensated_delta_bytes": size_delta,
            "remainder_bytes": len(remainder),
            "remainder_sha256": sha256(remainder),
        },
        "fixed_size_compensation": {
            "entry": PAD_ENTRY,
            "old_padding_bytes": old_pad_size,
            "new_padding_bytes": new_pad_size,
            "removed_bytes": size_delta,
            "raw_bytes_preserved": True,
            "cpio_end_preserved": True,
        },
    }


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
        HOSTAPD_ARTIFACT,
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
        raise SystemExit("F138 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F138 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F138 persistent entry contract failed")

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
            "radio2g": "unchanged from F137",
            "radio5_modules": "unchanged from F137",
            "qdrv_wlan_dma_queues_rates_rings_auc_tx": "unchanged from F137",
            "radio5_start_stop": "unchanged from F137",
            "hostapd_qtn": "raw probe socket falls back to wifi0 when bridge is empty",
            "bridge_topology": "unchanged from F137; wifi0 remains outside br0",
        },
        "runtime_policy": {
            "raw_probe_socket": "bridge when configured, otherwise the BSS interface",
            "expected_marker": HOSTAPD_MARKER.decode("ascii"),
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
    artifact_paths = {
        "decompressed_payload": raw_path,
        "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "config": config_path,
        "dtb": dtb_path,
        "vmlinux": vmlinux_path,
    }
    for key, path in artifact_paths.items():
        item = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path.read_bytes())}
        if key == "webformat":
            item["crc32"] = f71.crc32(path.read_bytes())
        manifest["artifacts"][key] = item

    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    paths = (
        raw_path, uncompressed_path, lzma_path, uimage_path, web_path,
        config_path, dtb_path, vmlinux_path, contract_path,
        entry_contract_path, manifest_path,
    )
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in paths),
        encoding="ascii",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
