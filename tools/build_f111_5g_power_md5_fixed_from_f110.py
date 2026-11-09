#!/usr/bin/env python3
"""Build F111 from F110 by fixing the 5 GHz power-table checksum preflight.

F110 boots and preserves the F104 2.4 GHz baseline, but manual 5 GHz start
refuses before loading modules because BusyBox lacks md5sum.  The table is
static and sha256sum is available, so F111 validates the known SHA-256 and then
passes the corresponding OEM MD5 to qdrv.
"""
from __future__ import annotations

import json
import lzma
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f111-5g-power-md5-fixed-from-f110"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f110-2g-f104-rc1-5g-manual/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f110-2g-f104-rc1-5g-manual-LZMA-OFFLINE-NO-FLASH"
BASELINE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f104-2g-be-guard16-from-f103/build"
BASELINE_BASE = "openmitrastar-linux510-q3-persistent-f104-2g-be-guard16-from-f103-LZMA-OFFLINE-NO-FLASH"
START_ENTRY = "usr/sbin/om-radio5-start"
PAD_ENTRY = "usr/share/openmitrastar/radio5g/f110-fixed-size.pad"

POWER_TABLE_SHA256 = "1f884017d214bf185a82bd3ed991f5095251474d9336c9c3af07f2a36aaf28d5"
POWER_TABLE_MD5 = "1a3e318227fdc19079418f847d3e2ee8"

OLD_BLOCK = """power_md5=$(md5sum /etc/power_tables/tx_power_QSR1000_es.txt 2>/dev/null | awk '{ print $1 }')
case "$power_md5" in ????????????????????????????????) ;; *) refuse power-md5-contract ;; esac
"""
NEW_BLOCK = f"""power_sha=$(sha256sum /etc/power_tables/tx_power_QSR1000_es.txt 2>/dev/null | awk '{{ print $1 }}')
[ "$power_sha" = {POWER_TABLE_SHA256} ] || refuse power-sha-contract
power_md5={POWER_TABLE_MD5}
"""


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


def pad_entry_like(entry: f71.CpioEntry, size: int) -> f71.CpioEntry:
    return replace_entry(entry, b"\0" * size)


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if OLD_BLOCK not in text:
        raise SystemExit("F110 om-radio5-start missing md5sum power block")
    patched = text.replace(OLD_BLOCK, NEW_BLOCK, 1).encode("ascii")
    return patched, {
        "entry": START_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched),
        "old_sha256": f71.sha256(data),
        "new_sha256": f71.sha256(patched),
        "fix": "replace unavailable md5sum runtime dependency with sha256 validation plus fixed OEM MD5",
        "power_table_sha256": POWER_TABLE_SHA256,
        "power_table_md5": POWER_TABLE_MD5,
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_len = len(raw) - len(remainder) - start
    trailer = entries[-1]
    if trailer.name != "TRAILER!!!":
        raise SystemExit("source CPIO trailer missing")

    patched_entries: list[f71.CpioEntry] = []
    patch_report: dict[str, object] | None = None
    pad_template: f71.CpioEntry | None = None
    old_pad_size = None
    for entry in entries[:-1]:
        if entry.name == START_ENTRY:
            patched_data, patch_report = patch_start(entry.data)
            patched_entries.append(replace_entry(entry, patched_data))
        elif entry.name == PAD_ENTRY:
            pad_template = entry
            old_pad_size = len(entry.data)
        else:
            patched_entries.append(entry)
    if patch_report is None:
        raise SystemExit(f"missing CPIO entry: {START_ENTRY}")
    if pad_template is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {PAD_ENTRY}")

    without_pad = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    trailer_size = len(f71.serialize_entry(trailer))
    pad_serialized_needed = old_cpio_len - len(without_pad) - trailer_size
    if pad_serialized_needed <= 0:
        raise SystemExit("F111 script growth exceeded available fixed-size padding")
    adjusted_pad = None
    for size in range(max(0, old_pad_size - 4096), old_pad_size + 4096):
        candidate = pad_entry_like(pad_template, size)
        if len(f71.serialize_entry(candidate)) == pad_serialized_needed:
            adjusted_pad = candidate
            break
    if adjusted_pad is None:
        raise SystemExit(f"cannot adjust padding to serialized size {pad_serialized_needed}")
    patched_entries.append(adjusted_pad)
    patched_entries.append(trailer)
    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    if len(patched_cpio) != old_cpio_len:
        raise SystemExit("F111 fixed-size CPIO contract failed before serialization")

    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    if len(result) != len(raw) or new_start != start or new_remainder != remainder:
        raise SystemExit("F111 changed raw size/start/remainder")
    patch_report.update({
        "cpio_start": start,
        "cpio_end": len(raw) - len(remainder),
        "raw_bytes": len(raw),
        "remainder_bytes": len(remainder),
        "remainder_sha256": f71.sha256(remainder),
        "padding_entry": PAD_ENTRY,
        "old_padding_bytes": old_pad_size,
        "new_padding_bytes": len(adjusted_pad.data),
        "padding_delta": len(adjusted_pad.data) - old_pad_size,
    })
    return result, patch_report


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{SRC_BASE}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{SRC_BASE}.config"
    source_dtb = SRC_BUILD / f"{SRC_BASE}.dtb"
    source_vmlinux = SRC_BUILD / f"{SRC_BASE}.vmlinux"
    source_manifest = SRC_BUILD / "manifest.json"
    source_result = SRC_BUILD / "build-result.json"
    baseline_raw = BASELINE_BUILD / f"{BASELINE_BASE}.decompressed.bin"
    for required in (
        source_raw,
        source_uncompressed,
        source_config,
        source_dtb,
        source_vmlinux,
        source_manifest,
        source_result,
        baseline_raw,
        f71.TEMPLATE,
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
        raise SystemExit("F111 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F111 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(baseline_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F111 persistent entry contract failed")

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
        "schema": "openmitrastar.q3-persistent-composite-f111-5g-power-md5-fixed-from-f110/v1",
        "classification": "F111_FROM_F110_RADIO5_POWER_TABLE_MD5_RUNTIME_FIX",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw.read_bytes()),
            "candidate_sha256": source_result_json["candidate_sha256"],
            "full_slot_crc32": source_result_json["full_slot_crc32"],
        },
        "change_scope": {
            "radio2g": "unchanged from F104/F110 measured baseline",
            "radio5_start": "replace missing md5sum dependency with sha256 gate and fixed OEM MD5",
            "radio5_modules": "unchanged from F110 RC1",
            "radio5_autostart": "unchanged from F110: disabled/manual only",
            "entry_layout": "same raw size, CPIO end, post-CPIO remainder and entry sample as F104",
        },
        "patch": patch_report,
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
        "schema": "openmitrastar.f111-5g-power-md5-fixed-from-f110-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": f71.sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": f71.sha256(full_slot),
        "full_slot_crc32": f71.crc32(full_slot),
        "build_dir": str(OUT),
        "tftp_copy": str(tftp_copy),
        "patch": patch_report,
        "bootbase_result": contract_json.get("result"),
        "flash": False,
        "router_mutations": False,
    }
    result_path = OUT / "build-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")

    with (OUT / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as fh:
        for path in sorted([*artifacts.values(), contract_path, entry_contract_path, manifest_path, result_path], key=lambda item: item.name):
            fh.write(f"{f71.sha256(path.read_bytes())}  {path.name}\n")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
