#!/usr/bin/env python3
"""Build F115 from F114 by fixing the manual 5 GHz start gate.

F114 is the best current 2.4 GHz baseline.  This builder preserves it and only
patches the manual 5 GHz start path:

* refresh /run origin, Quantenna MAC and calibration before manual start;
* use the HGW OEM board radio parameters for the current RC1 qdrv profile;
* update radio5g/artifacts.sha256 for the patched om-radio5-start.
"""
from __future__ import annotations

import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f115-5g-manual-prep-oemboard-from-f114"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f114-2g-no-be-guard-from-f112/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f114-2g-no-be-guard-from-f112-LZMA-OFFLINE-NO-FLASH"
START_ENTRY = "usr/sbin/om-radio5-start"
HASHES_ENTRY = "usr/share/openmitrastar/radio5g/artifacts.sha256"
PAD_ENTRY = "usr/share/openmitrastar/radio5g/f110-fixed-size.pad"

OLD_CAL_CALL = """[ ! -e /sys/class/net/eth1_emac0 ] || refuse vendor-emac-present
[ ! -e /sys/class/net/eth1_emac1 ] || refuse vendor-emac-present
calibration_gate
"""
NEW_CAL_CALL = """[ ! -e /sys/class/net/eth1_emac0 ] || refuse vendor-emac-present
[ ! -e /sys/class/net/eth1_emac1 ] || refuse vendor-emac-present
prepare_runtime_sources
calibration_gate
"""
PREP_FUNCTION = """prepare_runtime_sources()
{
\t[ -r \"$origin/ready\" ] || /usr/sbin/om-origin-import || refuse origin-producer-failed
\t[ -r \"$mac_file\" ] || /usr/sbin/om-qtn-mac-prepare || refuse qtn-mac-producer-failed
\t[ -r \"$calibration_ready\" ] || /usr/sbin/om-qtn-cal-readonly || refuse calibration-producer-failed
}

"""
BOARD_OLD = "board_radio_oem_profile=0\n"
BOARD_NEW = (
    "# Current RC1 qdrv also needs the HGW OEM board radio values; without\n"
    "# them MuC reports Unsupported FEM type and wifi0 never raises carrier.\n"
    "board_radio_oem_profile=1\n"
)


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
    if "prepare_runtime_sources()" in text:
        raise SystemExit("F115 start script already contains runtime prep")
    if "calibration_gate()\n{" not in text:
        raise SystemExit("F115 missing calibration_gate insertion point")
    if OLD_CAL_CALL not in text:
        raise SystemExit("F115 missing manual-start calibration call block")
    if BOARD_OLD not in text:
        raise SystemExit("F115 missing board profile default")
    patched = text.replace("calibration_gate()\n{", PREP_FUNCTION + "calibration_gate()\n{", 1)
    patched = patched.replace(OLD_CAL_CALL, NEW_CAL_CALL, 1)
    patched = patched.replace(BOARD_OLD, BOARD_NEW, 1)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "fixes": [
            "manual 5g start rehydrates origin mtd5 runtime",
            "manual 5g start prepares qtn mac from redundant bootenv",
            "manual 5g start prepares qtn calibration read-only",
            "current rc1 path uses hgw oem board radio values",
        ],
    }


def patch_hashes(data: bytes, start_hash: str) -> tuple[bytes, dict[str, object]]:
    lines = data.decode("ascii").splitlines()
    replaced = 0
    out: list[str] = []
    old_hash = None
    for line in lines:
        if line.endswith("  /usr/sbin/om-radio5-start"):
            old_hash = line.split()[0]
            out.append(f"{start_hash}  /usr/sbin/om-radio5-start")
            replaced += 1
        else:
            out.append(line)
    if replaced != 1 or old_hash is None:
        raise SystemExit("F115 could not update om-radio5-start hash entry")
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
            patched_hashes, hashes_patch = patch_hashes(entry.data, sha256(patched_start_data))
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
        raise SystemExit(f"F115 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}")
    pad_entry = patched_entries[pad_index]
    new_pad_size = old_pad_size - size_delta
    patched_entries[pad_index] = replace_entry(pad_entry, b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start:
        raise SystemExit("F115 changed CPIO start")
    if new_remainder != remainder:
        raise SystemExit("F115 changed post-CPIO remainder")
    if len(result) != len(raw):
        raise SystemExit("F115 changed decompressed payload size")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F115 changed CPIO end")

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
        raise SystemExit("F115 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F115 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F115 persistent entry contract failed")

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
        "schema": "openmitrastar.q3-persistent-composite-f115-5g-manual-prep-oemboard-from-f114/v1",
        "classification": "F115_FROM_F114_5G_MANUAL_PREP_AND_OEM_BOARD_FIXEDSIZE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": sha256(source_raw_bytes),
            "candidate_sha256": source_result_json["candidate_sha256"],
            "full_slot_crc32": source_result_json["full_slot_crc32"],
        },
        "change_scope": {
            "radio2g": "unchanged from F114 measured 31.6 Mbps baseline",
            "radio5_start": "manual 5g start rehydrates runtime inputs and uses HGW OEM board radio values",
            "radio5_modules": "unchanged from F114/F112/F111",
            "radio5_autostart": "unchanged from F114: disabled/manual only",
            "artifact_manifest": "updated only om-radio5-start hash after fixed-size patch",
            "entry_layout": "same raw size, CPIO end, post-CPIO remainder and entry sample as F114",
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
        "schema": "openmitrastar.f115-5g-manual-prep-oemboard-from-f114-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": sha256(full_slot),
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
            fh.write(f"{sha256(path.read_bytes())}  {path.name}\n")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
