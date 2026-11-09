#!/usr/bin/env python3
"""Build F136 from F133 by deferring the first post-hostapd Tx-Power gate."""
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
import build_f133_5g_disable_hr_timer_from_f132 as f133
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f136-5g-defer-post-hostapd-visibility-from-f133"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F136_FROM_F133_5G_DEFER_POST_HOSTAPD_VISIBILITY"

SRC_BUILD = f133.OUT
SRC_BASE = f133.BASE_OUT
START_ENTRY = f133.START_ENTRY
HASHES_ENTRY = f133.HASHES_ENTRY
PAD_ENTRY = f133.PAD_ENTRY

OLD_START_SHA = "bdc3245efd75b6e8f381e8de24e059cdfb38aa5e567f2c454618175208bbb72a"

VISIBILITY_FUNCTION_END = """\tlog "OMRADIO5_VISIBILITY_STATE_PASS label=$label tx_power_dbm=$tx_power"
}
"""

VISIBILITY_FUNCTION_WITH_OBSERVER = """\tlog "OMRADIO5_VISIBILITY_STATE_PASS label=$label tx_power_dbm=$tx_power"
}

observe_radio5_visibility_state()
{
\tlabel=$1
\taction=$2
\ttx_power=unknown
\tif /usr/sbin/iwconfig-qtn wifi0 >"$state/iwconfig-$label.log" 2>&1; then
\t\tparsed=$(sed -n 's/.*Tx-Power:\\([0-9][0-9]*\\) dBm.*/\\1/p' "$state/iwconfig-$label.log" | head -n 1)
\t\tcase "$parsed" in ''|*[!0-9]*) tx_power=unknown ;; *) tx_power=$parsed ;; esac
\t\tif [ "$tx_power" != unknown ] && [ "$tx_power" -gt 0 ] &&
\t\t\tgrep -Fq 'Frequency:5.18 GHz' "$state/iwconfig-$label.log"; then
\t\t\tlog "OMRADIO5_VISIBILITY_STATE_PASS label=$label tx_power_dbm=$tx_power source=f136"
\t\t\treturn 0
\t\tfi
\tfi
\tqtn_visibility_snapshot "$label-deferred"
\tlog "OMRADIO5_VISIBILITY_DEFER label=$label tx_power_dbm=$tx_power action=$action source=f136"
\treturn 0
}
"""

OLD_POST_HOSTAPD_GATE = """kill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead
require_radio5_visibility_state post-hostapd
[ -e /sys/devices/virtual/net/wifi0/wps_button ] || refuse wps-gpio4-sysfs-absent
"""

NEW_POST_HOSTAPD_GATE = """kill -0 "$hostapd_shell_pid" >/dev/null 2>&1 || refuse hostapd-dead
observe_radio5_visibility_state post-hostapd continue-to-coc
[ -e /sys/devices/virtual/net/wifi0/wps_button ] || refuse wps-gpio4-sysfs-absent
"""


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    actual = sha256(data)
    if actual != OLD_START_SHA:
        raise SystemExit(f"F136 start input hash mismatch: {actual}")
    text = data.decode("ascii")
    if "OMRADIO5_VISIBILITY_DEFER" in text:
        raise SystemExit("F136 start script already contains deferred visibility marker")
    replacements = (
        (VISIBILITY_FUNCTION_END, VISIBILITY_FUNCTION_WITH_OBSERVER, "visibility_observer"),
        (OLD_POST_HOSTAPD_GATE, NEW_POST_HOSTAPD_GATE, "post_hostapd_defer"),
    )
    patched = text
    applied: list[str] = []
    for old, new, name in replacements:
        if old not in patched:
            raise SystemExit(f"F136 missing insertion point: {name}")
        patched = patched.replace(old, new, 1)
        applied.append(name)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_sha256": OLD_START_SHA,
        "new_sha256": sha256(patched_bytes),
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "applied": applied,
        "fixes": [
            "keeps F133 qdrv HR timer disabled",
            "continues past the first post-hostapd Tx-Power:0 dBm observation",
            "keeps the later post-CoC visibility gate strict",
            "does not change 2.4 GHz, qdrv, wlan, queues, DMA, rates, rings, bridge topology, forwarding or auc_tx",
        ],
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    replacements: dict[str, bytes] = {}
    start_patch = None
    pad_index = old_pad_size = None

    for entry in entries:
        if entry.name == START_ENTRY:
            start_data, start_patch = patch_start(entry.data)
            replacements[START_ENTRY] = start_data
            patched_entries.append(f125.replace_entry(entry, start_data))
        elif entry.name == PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)
    if start_patch is None:
        raise SystemExit(f"missing CPIO entry: {START_ENTRY}")
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

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim_cpio) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(f"F136 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}")
    patched_entries[pad_index] = f125.replace_entry(patched_entries[pad_index], b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F136 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F136 changed CPIO end")

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
        raise SystemExit("F136 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F136 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F136 persistent entry contract failed")

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
            "radio2g": "unchanged from F133",
            "radio5_modules": "unchanged from F133",
            "qdrv": "unchanged from F133; HR one-shot remains disabled",
            "wlan": "unchanged from F133",
            "radio5_start": "defers only the first post-hostapd visibility failure, then keeps later gates strict",
            "radio5_stop": "unchanged from F133",
            "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F133",
            "bridge_topology": "unchanged from F133; wifi0 remains outside br0",
        },
        "runtime_policy": {
            "hr_timer": "not armed on qdrv_wlan_init",
            "post_hostapd_txpower_zero": "snapshot and continue to CoC/PM0",
            "post_coc_visibility": "strict",
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
        "security": {
            "touches_router": False,
            "flash": False,
            "opens_uart": False,
        },
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
        item = {
            "file": path.name,
            "bytes": path.stat().st_size,
            "sha256": sha256(path.read_bytes()),
        }
        if key == "webformat":
            item["crc32"] = f71.crc32(path.read_bytes())
        manifest["artifacts"][key] = item

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
