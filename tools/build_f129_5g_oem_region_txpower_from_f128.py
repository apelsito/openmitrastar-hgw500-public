#!/usr/bin/env python3
"""Build F129 from F128 with the OEM regional TX-power path."""
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
import build_f128_5g_visibility_power_gate_from_f127 as f128
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f129-5g-oem-region-txpower-from-f128"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = f128.OUT
SRC_BASE = f128.BASE_OUT
START_ENTRY = f128.START_ENTRY
HASHES_ENTRY = f128.HASHES_ENTRY
PAD_ENTRY = f128.PAD_ENTRY

OLD_EXTRA_TXPOWER_BLOCK = """/usr/sbin/iwpriv-qtn wifi0 init_txpower "$qtn_txpower_val" >"$state/init-txpower.log" 2>&1 || refuse txpower-init
/usr/sbin/iwpriv-qtn wifi0 cfg_txpower "$qtn_txpower_val" >"$state/cfg-txpower.log" 2>&1 || refuse txpower-cfg
/usr/sbin/iwpriv-qtn wifi0 cfg_reg_txpower "$qtn_reg_txpower_val" >"$state/cfg-reg-txpower.log" 2>&1 || refuse txpower-reg-cfg
/usr/sbin/iwpriv-qtn wifi0 doth 1 >"$state/doth-set.log" 2>&1 || refuse doth-enable
"""

NEW_OEM_TXPOWER_BLOCK = """/usr/sbin/iwpriv-qtn wifi0 init_txpower "$qtn_txpower_val" >"$state/init-txpower.log" 2>&1 || refuse txpower-init
# OEM start-vap only calls init_txpower on the regional path; avoid the two
# broader table rewrites while Tx-Power is stuck at 0 dBm.
/usr/sbin/iwpriv-qtn wifi0 doth 1 >"$state/doth-set.log" 2>&1 || refuse doth-enable
"""

OLD_LOG_LINE = """log "OMRADIO5_TXPOWER_PARITY init=$qtn_txpower_val reg=$qtn_reg_txpower_val doth=1 tpc=1 source=oem-start-vap"
"""

NEW_LOG_LINE = """log "OMRADIO5_TXPOWER_PARITY init=$qtn_txpower_val doth=1 tpc=1 source=oem-regional-path cfg_txpower=skipped cfg_reg_txpower=skipped"
"""

OLD_SNAPSHOT_DMESG = """\t\t/usr/sbin/iwpriv-qtn wifi0 get_pm 2>&1 || true
\t\tif [ -r "$state/hostapd.log" ]; then
"""

NEW_SNAPSHOT_DMESG = """\t\t/usr/sbin/iwpriv-qtn wifi0 get_pm 2>&1 || true
\t\tprintf 'cal_tail_begin\\n'
\t\tdmesg 2>/dev/null | grep -E 'OMQTNCALFOPS|pdetector|Power cal|DC/IQ|rx_iq|dc_iq|txpower|Tx-Power|OMQDRVSEQ|OMQDRVBC|OMQDRVLED' | tail -n 160 || true
\t\tprintf 'cal_tail_end\\n'
\t\tif [ -r "$state/hostapd.log" ]; then
"""


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if "source=oem-regional-path" in text:
        raise SystemExit("F129 start script already contains OEM regional txpower path")
    replacements = (
        (OLD_EXTRA_TXPOWER_BLOCK, NEW_OEM_TXPOWER_BLOCK, "oem_region_txpower"),
        (OLD_LOG_LINE, NEW_LOG_LINE, "txpower_log"),
        (OLD_SNAPSHOT_DMESG, NEW_SNAPSHOT_DMESG, "cal_power_snapshot"),
    )
    patched = text
    applied: list[str] = []
    for old, new, name in replacements:
        if old not in patched:
            raise SystemExit(f"F129 missing insertion point: {name}")
        patched = patched.replace(old, new, 1)
        applied.append(name)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "applied": applied,
        "fixes": [
            "keeps init_txpower but skips cfg_txpower and cfg_reg_txpower to match the OEM regional start-vap path",
            "keeps DOTH/TPC and fail-closed visibility gates from F128",
            "adds calibration and power-related dmesg tail to visibility snapshots",
            "does not change qdrv, wlan, queues, DMA, rates, rings, forwarding, bridge topology or auc_tx",
        ],
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    patched_start_data = None
    start_patch = None
    pad_index = old_pad_size = None

    for entry in entries:
        if entry.name == START_ENTRY:
            patched_start_data, start_patch = patch_start(entry.data)
            patched_entries.append(f125.replace_entry(entry, patched_start_data))
        elif entry.name == PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)
    if patched_start_data is None or start_patch is None:
        raise SystemExit(f"missing CPIO entry: {START_ENTRY}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {PAD_ENTRY}")

    patched_entries_2: list[f71.CpioEntry] = []
    hashes_patch = None
    start_hash = sha256(patched_start_data)
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            hashes_data, hashes_patch = f125.patch_hashes(entry.data, start_hash)
            patched_entries_2.append(f125.replace_entry(entry, hashes_data))
        else:
            patched_entries_2.append(entry)
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {HASHES_ENTRY}")
    patched_entries = patched_entries_2

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim_cpio) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F129 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}")
    patched_entries[pad_index] = f125.replace_entry(patched_entries[pad_index], b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F129 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F129 changed CPIO end")

    return result, {
        "start_script": start_patch,
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
        raise SystemExit("F129 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F129 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F129 persistent entry contract failed")

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
        "classification": "F129_FROM_F128_5G_OEM_REGION_TXPOWER",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_data["artifacts"]["webformat"]["sha256"],
            "raw_sha256": source_manifest_data["artifacts"]["decompressed_payload"]["sha256"],
        },
        "patch": patch_report,
        "change_scope": {
            "radio2g": "unchanged from F128",
            "radio5_start": "uses OEM regional TX-power sequence and keeps F128 fail-closed visibility gates",
            "radio5_stop": "unchanged from F128",
            "radio5_modules": "unchanged from F128",
            "qdrv": "unchanged from F128",
            "wlan": "unchanged from F128",
            "bridge_topology": "unchanged from F128",
            "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F128",
        },
        "runtime_policy": {
            "persistent_ap_profiles": ["product-v6", "beacon-lifetime-37527d16"],
            "association_window_auto_stop": False,
            "visibility_false_ready_allowed": False,
            "txpower_zero_ready_allowed": False,
            "txpower_path": "oem-regional-init-only",
            "skips_cfg_txpower": True,
            "skips_cfg_reg_txpower": True,
            "persistent_flash_writes": 0,
        },
        "artifacts": {
            "decompressed_payload": {"file": raw_path.name, "bytes": raw_path.stat().st_size, "sha256": sha256(raw_path.read_bytes())},
            "uncompressed_uimage": {"file": uncompressed_path.name, "bytes": uncompressed_path.stat().st_size, "sha256": sha256(uncompressed_path.read_bytes())},
            "lzma": {"file": lzma_path.name, "bytes": lzma_path.stat().st_size, "sha256": sha256(lzma_path.read_bytes())},
            "uimage": {"file": uimage_path.name, "bytes": uimage_path.stat().st_size, "sha256": sha256(uimage_path.read_bytes())},
            "webformat": {"file": web_path.name, "bytes": web_path.stat().st_size, "sha256": sha256(web_path.read_bytes()), "crc32": f71.crc32(web_path.read_bytes())},
            "config": {"file": config_path.name, "bytes": config_path.stat().st_size, "sha256": sha256(config_path.read_bytes())},
            "dtb": {"file": dtb_path.name, "bytes": dtb_path.stat().st_size, "sha256": sha256(dtb_path.read_bytes())},
            "vmlinux": {"file": vmlinux_path.name, "bytes": vmlinux_path.stat().st_size, "sha256": sha256(vmlinux_path.read_bytes())},
        },
        "slot": {"name": "linux_live", "bytes": f71.SLOT_BYTES, "candidate_bytes": web_path.stat().st_size, "fits": web_path.stat().st_size <= f71.SLOT_BYTES},
        "bootbase_contract": {"file": contract_path.name, "result": bootbase_contract.get("result"), "candidate_accepted": bootbase_contract.get("candidate", {}).get("accepted")},
        "persistent_entry_contract": {"file": entry_contract_path.name, "result": json.loads(entry_contract_path.read_text(encoding="utf-8")).get("result")},
        "security": {"touches_router": False, "flash": False, "opens_uart": False},
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sum_files = [raw_path, uncompressed_path, lzma_path, uimage_path, web_path, config_path, dtb_path, vmlinux_path, manifest_path, entry_contract_path, contract_path]
    (OUT / "SHA256SUMS").write_bytes(
        "".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in sum_files).encode("ascii")
    )
    result = {
        "status": "PASS",
        "build_tag": BUILD_TAG,
        "out": str(OUT.relative_to(ROOT)),
        "webformat": str(web_path.relative_to(ROOT)),
        "webformat_sha256": manifest["artifacts"]["webformat"]["sha256"],
        "candidate_crc32": manifest["artifacts"]["webformat"]["crc32"],
        "full_slot_crc32": f71.crc32(web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)),
        "qdrv_sha256": f122.NEW_QDRV_SHA,
        "wlan_sha256": f122.NEW_WLAN_SHA,
        "fix": "5g-oem-regional-init-txpower-only-plus-cal-power-snapshots",
    }
    (OUT / "build-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
