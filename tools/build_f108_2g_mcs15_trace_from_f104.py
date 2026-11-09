#!/usr/bin/env python3
"""Build F108 from F104 by switching 2.4 GHz data descriptors to MCS15.

F104 is the current stable flash baseline: Linux 5.10 boots, SSH is reachable,
2.4 GHz associates and BE guard 16/8 drains.  Live UART still shows the data
descriptor path forced to MCS7.  F108 keeps F104's EMAC, bridge, BE guard,
reclaim poll, DMA/ring policy and 5 GHz contents unchanged, and changes only
the rtl8192ee module parameters in ``usr/sbin/om-radio-modules``:

* hgw500_force_data_mcs7=1 -> 0
* hgw500_force_data_mcs15=0 -> 1
* hgw500_tx_rate_trace=0 -> 1

The patch is fixed-size; CPIO framing and the post-CPIO kernel remainder are
preserved.
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
BUILD_TAG = "f108-2g-mcs15-trace-from-f104"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
SCHEMA = "openmitrastar.q3-persistent-composite-f108-2g-mcs15-trace-from-f104/v1"
CLASSIFICATION = "F108_FROM_F104_2G_MCS15_TRACE_FIXEDSIZE"
RESULT_SCHEMA = "openmitrastar.f108-2g-mcs15-trace-from-f104-build/v1"
PATCH_APPLIED = ["radio2g-force-mcs15-from-f104", "radio2g-rate-trace-default-on"]
VERIFY_MARKERS = (
    b"hgw500_force_data_mcs7=0",
    b"hgw500_force_data_mcs15=1",
    b"hgw500_tx_rate_trace=1",
    b"hgw500_force_data_mcs7=N",
    b"hgw500_force_data_mcs15=Y",
    b"hgw500_tx_rate_trace=Y",
)
CHANGE_SCOPE = {
    "radio2g_loader": "changed only rtl8192ee forced data MCS selector to MCS15 and enabled bounded tx_rate_trace",
    "radio2g_modules": "unchanged binaries from F104",
    "radio2g_queue_reclaim": "unchanged from F104: BE guard 16/8 and hgw500_tx_reclaim_poll=1",
    "radio2g_dma_rings_crypto": "unchanged from F104: TXBD64, dma_wmb, page_units=2, swenc=0",
    "kernel_emac": "unchanged from F104",
    "bridge": "unchanged from F104",
    "radio5_modules": "unchanged from F104; still manual/off in current product gate",
    "qdrv": "unchanged from F104",
    "flash_layout": "unchanged",
    "rootfs_initramfs": "fixed-size CPIO patch; raw payload size, CPIO end and post-CPIO remainder preserved",
}

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f104-2g-be-guard16-from-f103/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f104-2g-be-guard16-from-f103-LZMA-OFFLINE-NO-FLASH"
PATCH_ENTRY = "usr/sbin/om-radio-modules"

OLD_LOAD = (
    "hgw500_force_data_mcs7=1 hgw500_force_data_mcs15=0 "
    "hgw500_force_data_11m=0 hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=0"
)
NEW_LOAD = (
    "hgw500_force_data_mcs7=0 hgw500_force_data_mcs15=1 "
    "hgw500_force_data_11m=0 hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=1"
)
OLD_VERIFY = (
    "hgw500_force_data_mcs7=Y hgw500_force_data_mcs15=N \\\n"
    "\t\t\thgw500_force_data_11m=N hgw500_txbd_be_data_split=N \\\n"
    "\t\t\thgw500_tx_rate_trace=N; do"
)
NEW_VERIFY = (
    "hgw500_force_data_mcs7=N hgw500_force_data_mcs15=Y \\\n"
    "\t\t\thgw500_force_data_11m=N hgw500_txbd_be_data_split=N \\\n"
    "\t\t\thgw500_tx_rate_trace=Y; do"
)
PROFILE_REPLACEMENTS = (
    ("profile=all64-mcs7-eapol-mgntq-guard16-nosplit", "profile=all64-mc15-eapol-mgntq-guard16-nosplit"),
    ("profile=mcs7-noguard-nosplit", "profile=mc15-noguard-nosplit"),
    ("profile=mcs7-noguard-nosplit", "profile=mc15-noguard-nosplit"),
)


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


def patch_loader(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    required = [OLD_LOAD, OLD_VERIFY] + [old for old, _new in PROFILE_REPLACEMENTS[:2]]
    missing = [needle for needle in required if needle not in text]
    if missing:
        raise SystemExit(f"F104 om-radio-modules missing expected F108 markers: {missing!r}")

    patched = text.replace(OLD_LOAD, NEW_LOAD, 1).replace(OLD_VERIFY, NEW_VERIFY, 1)
    profile_changes: list[dict[str, str]] = []
    for old, new in PROFILE_REPLACEMENTS:
        if old in patched:
            patched = patched.replace(old, new, 1)
            profile_changes.append({"old": old, "new": new})

    patched_bytes = patched.encode("ascii")
    if len(patched_bytes) != len(data):
        raise SystemExit("F108 loader patch changed entry size")
    for marker in VERIFY_MARKERS:
        if marker not in patched_bytes:
            raise SystemExit(f"F108 marker missing after patch: {marker!r}")

    return patched_bytes, {
        "entry": PATCH_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": 0,
        "old_sha256": f71.sha256(data),
        "new_sha256": f71.sha256(patched_bytes),
        "applied": PATCH_APPLIED,
        "load_replacement": {"old": OLD_LOAD, "new": NEW_LOAD},
        "verify_replacement": {"old": OLD_VERIFY, "new": NEW_VERIFY},
        "profile_replacements": profile_changes,
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    report: dict[str, object] | None = None
    for entry in entries:
        if entry.name == PATCH_ENTRY:
            patched_loader, report = patch_loader(entry.data)
            patched_entries.append(replace_entry(entry, patched_loader))
        else:
            patched_entries.append(entry)
    if report is None:
        raise SystemExit(f"missing CPIO entry: {PATCH_ENTRY}")

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start:
        raise SystemExit("F108 patch changed CPIO start")
    if new_remainder != remainder:
        raise SystemExit("F108 patch changed post-CPIO remainder")
    if len(result) != len(raw):
        raise SystemExit("F108 patch changed decompressed payload size")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F108 patch changed CPIO end")

    report["cpio"] = {
        "start": start,
        "old_end": old_cpio_end,
        "new_end": new_cpio_end,
        "old_raw_bytes": len(raw),
        "new_raw_bytes": len(result),
        "delta_bytes": 0,
        "remainder_bytes": len(remainder),
        "remainder_sha256": f71.sha256(remainder),
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
        raise SystemExit("F108 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F108 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F108 persistent entry contract failed")

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
        "schema": SCHEMA,
        "classification": CLASSIFICATION,
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
            "candidate_sha256": source_result_json["candidate_sha256"],
            "full_slot_crc32": source_result_json["full_slot_crc32"],
        },
        "change_scope": CHANGE_SCOPE,
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
        "schema": RESULT_SCHEMA,
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
