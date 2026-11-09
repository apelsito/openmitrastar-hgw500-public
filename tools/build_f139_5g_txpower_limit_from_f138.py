#!/usr/bin/env python3
"""Build F139 from F138 with a valid WLAN TX-power default and OEM limit."""
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
import build_f138_5g_hostapd_isolated_raw_from_f137 as f138
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f139-5g-txpower-limit-from-f138"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F139_FROM_F138_5G_TXPOWER_DEFAULT_AND_OEM_LIMIT"

SRC_BUILD = f138.OUT
SRC_BASE = f138.BASE_OUT
START_ENTRY = "usr/sbin/om-radio5-start"
WLAN_ENTRY = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/wlan.ko"
DRIVER_CONTRACT_ENTRY = "usr/share/openmitrastar/radio5g/driver-contract.env"
HASHES_ENTRY = f138.HASHES_ENTRY
PAD_ENTRY = f138.PAD_ENTRY
WLAN_ARTIFACT = ROOT / (
    "outputs/kernel-port/quantenna-linux510-radiohw-txpower-default-f139-20260830/"
    "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/wlan/wlan.ko"
)
OLD_WLAN_SHA = "09c5e347f6c0fa9acad4a7e0e3571d5d976a2cf4a5f0e304730eb825badbc872"
NEW_WLAN_SHA = "97fac710018a2bbd59dca616537171d04da1ece771c4c22439710152e6b4fe29"
OLD_START_SHA = "b471aaa8686d513c8f6b8921aeb8c80579b293aad5c59a88bf428df3b4d686d3"

OLD_TXPOWER_BLOCK = '''/usr/sbin/iwpriv-qtn wifi0 init_txpower "$qtn_txpower_val" >"$state/init-txpower.log" 2>&1 || refuse txpower-init
# OEM start-vap only calls init_txpower on the regional path; avoid the two
'''
NEW_TXPOWER_BLOCK = '''/usr/sbin/iwpriv-qtn wifi0 init_txpower "$qtn_txpower_val" >"$state/init-txpower.log" 2>&1 || refuse txpower-init
/usr/sbin/iwconfig-qtn wifi0 txpower 21 >"$state/txpower-limit-set.log" 2>&1 || refuse txpower-limit-set
/usr/sbin/iwconfig-qtn wifi0 | grep -Fq 'Tx-Power:21 dBm' || refuse txpower-limit-readback
log 'OMRADIO5_TXPOWER_LIMIT dbm=21 source=oem-init-table max=21 min=1 wlan_default=max'
# OEM start-vap only calls init_txpower on the regional path; avoid the two
'''


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    actual = sha256(data)
    if actual != OLD_START_SHA:
        raise SystemExit(f"F139 start input hash mismatch: {actual}")
    text = data.decode("ascii")
    if OLD_TXPOWER_BLOCK not in text:
        raise SystemExit("F139 TX-power insertion point missing")
    patched = text.replace(OLD_TXPOWER_BLOCK, NEW_TXPOWER_BLOCK, 1).encode("ascii")
    return patched, {
        "entry": START_ENTRY,
        "old_sha256": actual,
        "new_sha256": sha256(patched),
        "old_bytes": len(data),
        "new_bytes": len(patched),
        "marker": "OMRADIO5_TXPOWER_LIMIT",
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    wlan = WLAN_ARTIFACT.read_bytes()
    if sha256(wlan) != NEW_WLAN_SHA:
        raise SystemExit("F139 WLAN artifact hash mismatch")
    if b"OMQTNTXPWR stage=default-limit" not in wlan:
        raise SystemExit("F139 WLAN marker missing")

    replacements: dict[str, bytes] = {WLAN_ENTRY: wlan}
    report: dict[str, object] = {
        "wlan": {
            "entry": WLAN_ENTRY,
            "old_sha256": OLD_WLAN_SHA,
            "new_sha256": NEW_WLAN_SHA,
            "new_bytes": len(wlan),
            "marker": "OMQTNTXPWR stage=default-limit",
        }
    }
    patched_entries: list[f71.CpioEntry] = []
    pad_index = old_pad_size = None
    seen: set[str] = set()
    for entry in entries:
        if entry.name == START_ENTRY:
            value, item = patch_start(entry.data)
            replacements[entry.name] = value
            report["start_script"] = item
            patched_entries.append(f125.replace_entry(entry, value))
            seen.add(entry.name)
        elif entry.name == WLAN_ENTRY:
            old_hash = sha256(entry.data)
            if old_hash != OLD_WLAN_SHA:
                raise SystemExit(f"F139 WLAN input hash mismatch: {old_hash}")
            patched_entries.append(f125.replace_entry(entry, wlan))
            seen.add(entry.name)
        elif entry.name == DRIVER_CONTRACT_ENTRY:
            qdrv_hash = next(
                line.split("=", 1)[1]
                for line in entry.data.decode("ascii").splitlines()
                if line.startswith("QDRV_SHA256=")
            )
            value, item = f122.patch_driver_contract(entry.data, qdrv_hash, NEW_WLAN_SHA)
            replacements[entry.name] = value
            report["driver_contract"] = item
            patched_entries.append(f125.replace_entry(entry, value))
            seen.add(entry.name)
        elif entry.name == PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)
    required = {START_ENTRY, WLAN_ENTRY, DRIVER_CONTRACT_ENTRY}
    if seen != required:
        raise SystemExit(f"F139 missing CPIO entries: {sorted(required - seen)}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {PAD_ENTRY}")

    hashed_entries: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            value, hashes_patch = f122.patch_hashes(entry.data, replacements)
            hashed_entries.append(f125.replace_entry(entry, value))
        else:
            hashed_entries.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {HASHES_ENTRY}")
    report["artifact_hashes"] = hashes_patch
    patched_entries = hashed_entries

    interim = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(
            f"F139 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}"
        )
    patched_entries[pad_index] = f125.replace_entry(
        patched_entries[pad_index], b"\0" * new_pad_size
    )
    result = raw[:start] + b"".join(f71.serialize_entry(e) for e in patched_entries) + remainder
    new_start, new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    new_map = {entry.name: entry.data for entry in new_entries}
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F139 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F139 changed CPIO end")
    if sha256(new_map[WLAN_ENTRY]) != NEW_WLAN_SHA:
        raise SystemExit("F139 embedded WLAN verification failed")
    report["cpio"] = {
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
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{SRC_BASE}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{SRC_BASE}.config"
    source_dtb = SRC_BUILD / f"{SRC_BASE}.dtb"
    source_vmlinux = SRC_BUILD / f"{SRC_BASE}.vmlinux"
    source_manifest = SRC_BUILD / "manifest.json"
    for required in (
        source_raw, source_uncompressed, source_config, source_dtb,
        source_vmlinux, source_manifest, WLAN_ARTIFACT,
        f71.BOOTBASE, f71.LEGACY_LZMA,
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
        raise SystemExit("F139 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F139 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F139 persistent entry contract failed")
    contract = subprocess.run(
        [sys.executable, str(f71.BOOTBASE), "--candidate-slot", str(web_path),
         "--candidate-name", f"linux_live-{BUILD_TAG}", "--parts-dir", str(f71.PARTS_DIR)],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
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
            "radio2g": "unchanged from F138",
            "hostapd_qtn": "unchanged from F138",
            "qdrv_and_other_radio5_modules": "unchanged from F138",
            "wlan_ko": "remove the accidental TX-power maximum overwrite with zero",
            "radio5_start": "apply the OEM table maximum of 21 dBm and require readback",
            "dma_queues_rates_rings_forwarding_auc_tx": "unchanged from F138",
            "bridge_topology": "unchanged from F138; wifi0 remains outside br0",
        },
        "runtime_policy": {
            "txpower_default_half_dbm": 100,
            "configured_txpower_dbm": 21,
            "oem_init_txpower": "0x00ff1501: channels 0..255, max 21, min 1",
            "persistent_flash_writes": 0,
        },
        "artifacts": {},
        "slot": {"name": "linux_live", "bytes": f71.SLOT_BYTES,
                 "candidate_bytes": web_path.stat().st_size,
                 "fits": web_path.stat().st_size <= f71.SLOT_BYTES},
        "bootbase_contract": {"file": contract_path.name,
                              "result": bootbase_contract.get("result"),
                              "candidate_accepted": bootbase_contract.get("candidate_accepted")},
        "persistent_entry_contract": {"file": entry_contract_path.name, "result": "PASS"},
        "security": {"touches_router": False, "flash": False, "opens_uart": False},
    }
    artifact_paths = {
        "decompressed_payload": raw_path, "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path, "uimage": uimage_path, "webformat": web_path,
        "config": config_path, "dtb": dtb_path, "vmlinux": vmlinux_path,
    }
    for key, path in artifact_paths.items():
        item = {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path.read_bytes())}
        if key == "webformat":
            item["crc32"] = f71.crc32(path.read_bytes())
        manifest["artifacts"][key] = item
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    paths = (raw_path, uncompressed_path, lzma_path, uimage_path, web_path,
             config_path, dtb_path, vmlinux_path, contract_path,
             entry_contract_path, manifest_path)
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in paths),
        encoding="ascii",
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
