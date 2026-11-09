#!/usr/bin/env python3
"""Build F116 from F115 by opening wifi0 before hostapd-qtn.

F115 reaches MuC boot, creates wifi0 and gets hostapd-qtn control ready, but the
netdev stays down/carrierless.  This keeps the F114/F115 2.4 GHz baseline and
only patches the manual 5 GHz start order:

* open the qdrv RF gate;
* bring wifi0 administratively UP;
* then launch hostapd-qtn and wait for carrier.
"""
from __future__ import annotations

import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f115_5g_manual_prep_oemboard_from_f114 as f115
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f116-5g-wifi0-up-before-hostapd-from-f115"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = f115.OUT
SRC_BASE = f115.BASE_OUT
START_ENTRY = f115.START_ENTRY
HASHES_ENTRY = f115.HASHES_ENTRY
PAD_ENTRY = f115.PAD_ENTRY

OLD_RF_BLOCK = """printf '1\\n' >"$rf" || refuse rf-open
[ "$(cat "$rf")" = 1 ] || refuse rf-readback
/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &
"""

NEW_RF_BLOCK = """printf '1\\n' >"$rf" || refuse rf-open
[ "$(cat "$rf")" = 1 ] || refuse rf-readback
ifconfig wifi0 up || refuse wifi0-up
[ "$(( $(cat /sys/class/net/wifi0/flags) & 0x1 ))" -eq 1 ] || refuse wifi0-up-readback
/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &
"""


def sha256(data: bytes) -> str:
    return f71.sha256(data)


def replace_entry(entry: f71.CpioEntry, data: bytes) -> f71.CpioEntry:
    return f71.CpioEntry(
        name=entry.name,
        mode=entry.mode,
        data=data,
        ino=entry.ino,
        uid=entry.uid,
        gid=entry.gid,
        nlink=entry.nlink,
        mtime=entry.mtime,
        devmajor=entry.devmajor,
        devminor=entry.devminor,
        rdevmajor=entry.rdevmajor,
        rdevminor=entry.rdevminor,
    )


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if "ifconfig wifi0 up || refuse wifi0-up" in text:
        raise SystemExit("F116 start script already contains wifi0-up gate")
    if OLD_RF_BLOCK not in text:
        raise SystemExit("F116 missing RF-before-hostapd insertion block")
    patched = text.replace(OLD_RF_BLOCK, NEW_RF_BLOCK, 1)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "fixes": [
            "manual 5g start keeps F115 runtime prep and OEM board radio values",
            "manual 5g start opens qdrv RF before hostapd-qtn",
            "manual 5g start brings wifi0 administratively up before hostapd-qtn",
            "manual 5g carrier gate remains after hostapd-qtn readiness",
        ],
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    trailer = entries[-1]
    if trailer.name != "TRAILER!!!":
        raise SystemExit("source CPIO trailer missing")

    start_patch: dict[str, object] | None = None
    hashes_patch: dict[str, object] | None = None
    patched_start_data: bytes | None = None
    pad_index: int | None = None
    old_pad_size: int | None = None
    patched_entries: list[f71.CpioEntry] = []

    for entry in entries:
        if entry.name == START_ENTRY:
            patched_start_data, start_patch = patch_start(entry.data)
            patched_entries.append(replace_entry(entry, patched_start_data))
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
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            patched_hashes, hashes_patch = f115.patch_hashes(
                entry.data, sha256(patched_start_data)
            )
            patched_entries_2.append(replace_entry(entry, patched_hashes))
        else:
            patched_entries_2.append(entry)
    patched_entries = patched_entries_2
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {HASHES_ENTRY}")

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    interim_len = start + len(interim_cpio) + len(remainder)
    size_delta = interim_len - len(raw)
    if old_pad_size - size_delta < 0:
        raise SystemExit(
            f"F116 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}"
        )
    pad_entry = patched_entries[pad_index]
    new_pad_size = old_pad_size - size_delta
    patched_entries[pad_index] = replace_entry(pad_entry, b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start:
        raise SystemExit("F116 changed CPIO start")
    if new_remainder != remainder:
        raise SystemExit("F116 changed post-CPIO remainder")
    if len(result) != len(raw):
        raise SystemExit("F116 changed decompressed payload size")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F116 changed CPIO end")

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
    raw, patch_report = patch_cpio(source_raw_bytes)
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
        raise SystemExit("F116 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F116 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F116 persistent entry contract failed")

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
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f116-5g-wifi0-up-before-hostapd-from-f115/v1",
        "classification": "F116_FROM_F115_5G_WIFI0_UP_BEFORE_HOSTAPD_FIXEDSIZE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": sha256(source_raw_bytes),
            "candidate_sha256": source_result_json["candidate_sha256"],
            "full_slot_crc32": source_result_json["full_slot_crc32"],
        },
        "change_scope": {
            "radio2g": "unchanged from F115/F114 measured 31.6 Mbps baseline",
            "radio5_start": "manual 5g start opens RF and brings wifi0 up before hostapd-qtn",
            "radio5_modules": "unchanged from F115",
            "radio5_autostart": "unchanged from F115: disabled/manual only",
            "queues_dma_rates_rings": "unchanged from F115",
            "bridge_topology": "unchanged from F115",
            "artifact_manifest": "updated only om-radio5-start hash after fixed-size patch",
            "entry_layout": "same raw size, CPIO end, post-CPIO remainder and entry sample as F115",
        },
        "patch": patch_report,
        "artifacts": {
            key: {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256(path.read_bytes()),
                **({"crc32": f71.crc32(path.read_bytes())} if key == "webformat" else {}),
            }
            for key, path in artifacts.items()
        },
        "rootfs": {
            "rootfs": {
                "file": raw_path.name,
                "bytes": raw_path.stat().st_size,
                "sha256": sha256(raw_path.read_bytes()),
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
        "persistent_entry_contract": {
            "file": entry_contract_path.name,
            "result": json.loads(entry_contract_path.read_text(encoding="ascii")).get("result"),
        },
        "security": {"touches_router": False, "opens_uart": False, "flash": False},
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

    full_slot = web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f116-5g-wifi0-up-before-hostapd-from-f115-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": sha256(full_slot),
        "full_slot_crc32": f71.crc32(full_slot),
        "flash": False,
        "notes": [
            "F116 preserves F115 modules and 2.4 GHz baseline",
            "Only usr/sbin/om-radio5-start and its artifacts.sha256 entry change",
            "wifi0 is brought UP after rf-readback and before hostapd-qtn",
        ],
    }
    result_path = OUT / "build-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")

    lines = []
    for path in sorted(OUT.iterdir()):
        if path.is_file():
            lines.append(f"{sha256(path.read_bytes())}  {path.name}")
    (OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")

    print("F116_BUILD_PASS")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
