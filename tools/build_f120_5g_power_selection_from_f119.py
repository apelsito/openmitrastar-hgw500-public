#!/usr/bin/env python3
"""Build F120 from F119 by adding qdrv power_selection before clearsram."""
from __future__ import annotations

import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f119_5g_qdrv_contract_from_f118 as f119
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f120-5g-power-selection-from-f119"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = f119.OUT
SRC_BASE = f119.BASE_OUT
START_ENTRY = f119.START_ENTRY
HASHES_ENTRY = f119.HASHES_ENTRY
PAD_ENTRY = f119.PAD_ENTRY
QDRV_ENTRY = f119.QDRV_ENTRY
DRIVER_CONTRACT_ENTRY = f119.DRIVER_CONTRACT_ENTRY

OLD_START_BLOCK = """control_set "set power_table_checksum /etc/power_tables/tx_power_QSR1000_es.txt $power_md5" power-checksum
control_set 'set lock_checksum_list 1' checksum-lock
control_set clearsram clearsram
"""

NEW_START_BLOCK = """control_set "set power_table_checksum /etc/power_tables/tx_power_QSR1000_es.txt $power_md5" power-checksum
control_set 'set lock_checksum_list 1' checksum-lock
control_set 'set power_selection 2' power-selection
control_set clearsram clearsram
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
    if "power-selection" in text:
        raise SystemExit("F120 start script already contains power-selection gate")
    if OLD_START_BLOCK not in text:
        raise SystemExit("F120 missing qdrv sequential power-selection insertion point")
    patched = text.replace(OLD_START_BLOCK, NEW_START_BLOCK, 1)
    patched = patched.replace(
        "OMQDRVSEQ stage=start-pass mask=0x7f rf=blocked vap=blocked",
        "OMQDRVSEQ stage=start-pass mask=0xff rf=blocked vap=blocked",
        1,
    )
    patched = patched.replace(
        "OMQDRVSEQ stage=vap-pass unit=0 mode=ap interface=wifi0 rf=blocked count=1",
        "OMQDRVSEQ stage=vap-pass unit=0 mode=ap interface=wifi0 rf=blocked count=1",
        1,
    )
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "fixes": [
            "adds control set power_selection 2 before clearsram so sequential mask reaches 0xff",
            "updates expected sequential start marker from mask=0x7f to mask=0xff",
        ],
    }


def patch_hashes(data: bytes, start_hash: str) -> tuple[bytes, dict[str, object]]:
    lines = data.decode("ascii").splitlines()
    replaced = 0
    old_hash = None
    out: list[str] = []
    for line in lines:
        if line.endswith("  /usr/sbin/om-radio5-start"):
            old_hash = line.split()[0]
            out.append(f"{start_hash}  /usr/sbin/om-radio5-start")
            replaced += 1
        else:
            out.append(line)
    if replaced != 1 or old_hash is None:
        raise SystemExit("F120 could not update om-radio5-start hash entry")
    patched = ("\n".join(out) + "\n").encode("ascii")
    return patched, {
        "entry": HASHES_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched),
        "old_start_sha256": old_hash,
        "new_start_sha256": start_hash,
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    patched_start_data: bytes | None = None
    start_patch: dict[str, object] | None = None
    hashes_patch: dict[str, object] | None = None
    pad_index: int | None = None
    old_pad_size: int | None = None

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
            patched_hashes, hashes_patch = patch_hashes(entry.data, sha256(patched_start_data))
            patched_entries_2.append(replace_entry(entry, patched_hashes))
        else:
            patched_entries_2.append(entry)
    patched_entries = patched_entries_2
    if hashes_patch is None:
        raise SystemExit(f"missing CPIO entry: {HASHES_ENTRY}")

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    size_delta = start + len(interim_cpio) + len(remainder) - len(raw)
    new_pad_size = old_pad_size - size_delta
    if new_pad_size < 0:
        raise SystemExit(
            f"F120 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}"
        )
    pad_entry = patched_entries[pad_index]
    patched_entries[pad_index] = replace_entry(pad_entry, b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F120 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F120 changed CPIO end")

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
        raise SystemExit("F120 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F120 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F120 persistent entry contract failed")

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

    source_manifest_json = json.loads(source_manifest.read_text(encoding="utf-8"))
    source_result_json = json.loads(source_result.read_text(encoding="utf-8"))
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
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f120-5g-power-selection-from-f119/v1",
        "classification": "F120_FROM_F119_5G_POWER_SELECTION_FIXEDSIZE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": sha256(source_raw_bytes),
            "candidate_sha256": source_result_json["candidate_sha256"],
            "full_slot_crc32": source_result_json["full_slot_crc32"],
        },
        "change_scope": {
            "radio2g": "unchanged from F119/F114 measured 31.6 Mbps baseline",
            "radio5_start": "adds set power_selection 2 before clearsram",
            "radio5_modules": "unchanged from F119; qdrv RF/VAP gate build retained",
            "radio5_contract": "unchanged from F119; qdrv contract hash matches embedded qdrv.ko",
            "radio5_autostart": "unchanged from F119: disabled/manual only",
            "queues_dma_rates_rings": "unchanged from F119",
            "bridge_topology": "unchanged from F119",
            "artifact_manifest": "updated only om-radio5-start hash",
            "entry_layout": "same raw size, CPIO end, post-CPIO remainder and entry sample as F119",
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
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )

    full_slot = web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f120-5g-power-selection-from-f119-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": sha256(full_slot),
        "full_slot_crc32": f71.crc32(full_slot),
        "flash": False,
    }
    (OUT / "build-result.json").write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    lines = []
    for path in sorted(OUT.iterdir()):
        if path.is_file():
            lines.append(f"{sha256(path.read_bytes())}  {path.name}")
    (OUT / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="ascii")

    print("F120_BUILD_PASS")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
