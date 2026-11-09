#!/usr/bin/env python3
"""Build F122 from F121 by enabling the latest beacon-lifetime qdrv path."""
from __future__ import annotations

import io
import json
import lzma
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f121_5g_carrier_probe_from_f120 as f121
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f122-5g-beacon-lifetime-from-f121"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = f121.OUT
SRC_BASE = f121.BASE_OUT
START_ENTRY = f121.START_ENTRY
HASHES_ENTRY = f121.HASHES_ENTRY
PAD_ENTRY = f121.PAD_ENTRY
QDRV_ENTRY = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko"
WLAN_ENTRY = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/wlan.ko"
FEATURE_ENTRY = "etc/openmitrastar/features/q3-radio5-beacon-lifetime"
DRIVER_CONTRACT_ENTRY = "usr/share/openmitrastar/radio5g/driver-contract.env"
OVERLAY = (
    ROOT
    / "outputs/kernel-port/q3-dual-radio-open-lab-beacon-lifetime-powerselect-seq-f46-20260825"
    / "openmitrastar-q3-dual-radio-open-lab-beacon-lifetime-overlay.tar.gz"
)
NEW_PROFILE = "beacon-lifetime-37527d16"
OLD_PROFILE = "assoc-trace-cal-a4a4e277"
OLD_QDRV_SHA = "a4a4e277bf815e8b408594d67a1d1afcec03251af5bc4d05b51567abbb41ef33"
NEW_QDRV_SHA = "37527d16fa93325b676fde7247314fa0a9179095f3e6a7eb8dc19c63962b6f5f"
NEW_WLAN_SHA = "09c5e347f6c0fa9acad4a7e0e3571d5d976a2cf4a5f0e304730eb825badbc872"


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


def overlay_file(name: str) -> bytes:
    with tarfile.open(OVERLAY, "r:gz") as archive:
        member = archive.getmember(name)
        handle = archive.extractfile(member)
        if handle is None:
            raise SystemExit(f"overlay member is not a regular file: {name}")
        return handle.read()


def patch_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if NEW_PROFILE in text:
        raise SystemExit("F122 start script already has beacon-lifetime F46 profile")
    if OLD_PROFILE not in text or OLD_QDRV_SHA not in text:
        raise SystemExit("F122 missing F121 beacon-lifetime replacement point")
    patched = text.replace(OLD_PROFILE, NEW_PROFILE)
    patched = patched.replace(OLD_QDRV_SHA, NEW_QDRV_SHA)
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": START_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched_bytes),
        "old_profile": OLD_PROFILE,
        "new_profile": NEW_PROFILE,
        "old_qdrv_sha256": OLD_QDRV_SHA,
        "new_qdrv_sha256": NEW_QDRV_SHA,
    }


def patch_driver_contract(data: bytes, qdrv_hash: str, wlan_hash: str) -> tuple[bytes, dict[str, object]]:
    out: list[str] = []
    old_qdrv = old_wlan = None
    for line in data.decode("ascii").splitlines():
        if line.startswith("QDRV_SHA256="):
            old_qdrv = line
            out.append(f"QDRV_SHA256={qdrv_hash}")
        elif line.startswith("WLAN_SHA256="):
            old_wlan = line
            out.append(f"WLAN_SHA256={wlan_hash}")
        else:
            out.append(line)
    if old_qdrv is None or old_wlan is None:
        raise SystemExit("F122 could not update driver-contract.env")
    patched = ("\n".join(out) + "\n").encode("ascii")
    return patched, {
        "entry": DRIVER_CONTRACT_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched),
        "old_qdrv_line": old_qdrv,
        "old_wlan_line": old_wlan,
        "new_qdrv_sha256": qdrv_hash,
        "new_wlan_sha256": wlan_hash,
    }


def patch_hashes(data: bytes, replacements: dict[str, bytes]) -> tuple[bytes, dict[str, object]]:
    replaced: dict[str, dict[str, str]] = {}
    lines: list[str] = []
    for line in data.decode("ascii").splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2 and parts[1].startswith("/"):
            entry_name = parts[1][1:]
            if entry_name in replacements:
                new_hash = sha256(replacements[entry_name])
                replaced[entry_name] = {"old_sha256": parts[0], "new_sha256": new_hash}
                lines.append(f"{new_hash}  /{entry_name}")
                continue
        lines.append(line)
    for entry_name in sorted(set(replacements) - set(replaced)):
        new_hash = sha256(replacements[entry_name])
        replaced[entry_name] = {"old_sha256": "", "new_sha256": new_hash}
        lines.append(f"{new_hash}  /{entry_name}")
    patched = ("\n".join(lines) + "\n").encode("ascii")
    return patched, {
        "entry": HASHES_ENTRY,
        "old_sha256": sha256(data),
        "new_sha256": sha256(patched),
        "replaced": replaced,
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    qdrv = overlay_file(QDRV_ENTRY)
    wlan = overlay_file(WLAN_ENTRY)
    if sha256(qdrv) != NEW_QDRV_SHA or sha256(wlan) != NEW_WLAN_SHA:
        raise SystemExit("F122 overlay module hash mismatch")
    feature = b"Q3_RADIO5_BEACON_LIFETIME=1\n"

    replacements: dict[str, bytes] = {
        QDRV_ENTRY: qdrv,
        WLAN_ENTRY: wlan,
        FEATURE_ENTRY: feature,
    }
    patch_report: dict[str, object] = {
        "modules": {
            QDRV_ENTRY: {"new_sha256": NEW_QDRV_SHA, "new_bytes": len(qdrv)},
            WLAN_ENTRY: {"new_sha256": NEW_WLAN_SHA, "new_bytes": len(wlan)},
        },
        "feature": {"entry": FEATURE_ENTRY, "new_value": feature.decode("ascii").strip()},
    }

    patched_entries: list[f71.CpioEntry] = []
    pad_index = old_pad_size = None
    seen = set()
    for entry in entries:
        if entry.name == START_ENTRY:
            start_data, start_patch = patch_start(entry.data)
            replacements[START_ENTRY] = start_data
            patch_report["start_script"] = start_patch
            patched_entries.append(replace_entry(entry, start_data))
            seen.add(entry.name)
        elif entry.name == DRIVER_CONTRACT_ENTRY:
            contract_data, contract_patch = patch_driver_contract(entry.data, NEW_QDRV_SHA, NEW_WLAN_SHA)
            replacements[DRIVER_CONTRACT_ENTRY] = contract_data
            patch_report["driver_contract"] = contract_patch
            patched_entries.append(replace_entry(entry, contract_data))
            seen.add(entry.name)
        elif entry.name in replacements:
            old_data = entry.data
            new_data = replacements[entry.name]
            patch_report.setdefault("entries", {})[entry.name] = {
                "old_sha256": sha256(old_data),
                "new_sha256": sha256(new_data),
                "old_bytes": len(old_data),
                "new_bytes": len(new_data),
            }
            patched_entries.append(replace_entry(entry, new_data))
            seen.add(entry.name)
        elif entry.name == PAD_ENTRY:
            pad_index = len(patched_entries)
            old_pad_size = len(entry.data)
            patched_entries.append(entry)
        else:
            patched_entries.append(entry)

    for required in (QDRV_ENTRY, WLAN_ENTRY, FEATURE_ENTRY, START_ENTRY, DRIVER_CONTRACT_ENTRY):
        if required not in seen:
            raise SystemExit(f"missing CPIO entry: {required}")
    if pad_index is None or old_pad_size is None:
        raise SystemExit(f"missing fixed-size padding entry: {PAD_ENTRY}")

    patched_entries_2: list[f71.CpioEntry] = []
    hashes_patch = None
    for entry in patched_entries:
        if entry.name == HASHES_ENTRY:
            hashes_data, hashes_patch = patch_hashes(entry.data, replacements)
            patched_entries_2.append(replace_entry(entry, hashes_data))
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
        raise SystemExit(f"F122 fixed-size padding cannot absorb delta={size_delta}, pad={old_pad_size}")
    pad_entry = patched_entries[pad_index]
    patched_entries[pad_index] = replace_entry(pad_entry, b"\0" * new_pad_size)

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start or new_remainder != remainder or len(result) != len(raw):
        raise SystemExit("F122 changed fixed payload layout")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F122 changed CPIO end")

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
    source_result = SRC_BUILD / "build-result.json"
    for required in (
        source_raw,
        source_uncompressed,
        source_config,
        source_dtb,
        source_vmlinux,
        source_manifest,
        source_result,
        OVERLAY,
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
        raise SystemExit("F122 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F122 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F122 persistent entry contract failed")

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
    source_result_data = json.loads(source_result.read_text(encoding="ascii"))
    manifest = {
        "schema": f"openmitrastar.q3-persistent-composite-{BUILD_TAG}/v1",
        "classification": "F122_FROM_F121_5G_BEACON_LIFETIME_POWERSELECT",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_data["artifacts"]["webformat"]["sha256"],
            "raw_sha256": source_manifest_data["artifacts"]["decompressed_payload"]["sha256"],
            "full_slot_crc32": source_result_data.get("full_slot_crc32"),
        },
        "patch": patch_report,
        "change_scope": {
            "radio2g": "unchanged from F121",
            "radio5_start": "F121 carrier-probe preserved; beacon-lifetime profile changed to F46 powerselect modules",
            "radio5_modules": "qdrv.ko and wlan.ko replaced from F46 beacon-lifetime powerselect overlay",
            "radio5_feature": "q3-radio5-beacon-lifetime enabled",
            "bridge_topology": "unchanged from F121",
            "queues_dma_rates_rings": "unchanged except qdrv/wlan beacon-lifetime implementation",
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
            "candidate_accepted": bootbase_contract.get("candidate", {}).get("accepted"),
        },
        "persistent_entry_contract": {
            "file": entry_contract_path.name,
            "result": json.loads(entry_contract_path.read_text(encoding="utf-8")).get("result"),
        },
        "security": {"touches_router": False, "flash": False, "opens_uart": False},
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = OUT / "SHA256SUMS"
    sum_files = [
        raw_path,
        uncompressed_path,
        lzma_path,
        uimage_path,
        web_path,
        config_path,
        dtb_path,
        vmlinux_path,
        manifest_path,
        entry_contract_path,
        contract_path,
    ]
    sums.write_text("".join(f"{sha256(path.read_bytes())}  {path.name}\n" for path in sum_files), encoding="ascii")
    result = {
        "status": "PASS",
        "build_tag": BUILD_TAG,
        "out": str(OUT.relative_to(ROOT)),
        "webformat": str(web_path.relative_to(ROOT)),
        "webformat_sha256": manifest["artifacts"]["webformat"]["sha256"],
        "full_slot_crc32": manifest["artifacts"]["webformat"]["crc32"],
        "qdrv_sha256": NEW_QDRV_SHA,
        "wlan_sha256": NEW_WLAN_SHA,
        "beacon_lifetime": True,
    }
    (OUT / "build-result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
