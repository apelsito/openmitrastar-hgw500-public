#!/usr/bin/env python3
"""Build F95 from F93 with the corrected RTL8192EE descriptor path fixed-size.

F94 grew the decompressed CPIO payload and hung before the first kernel log on
hardware.  F95 keeps the same driver and loader intent but compensates the
added bytes by compacting inert JSON manifests so the F93 raw payload size,
CPIO end and post-CPIO remainder stay byte-for-byte compatible.
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
BUILD_TAG = "f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92-LZMA-OFFLINE-NO-FLASH"
REALTEK_BUNDLE = ROOT / "outputs/kernel-port/realtek-loop/all64-mcs15-ht40sgi-descfix-f94-RAM-ONLY-NO-FLASH"

MODULE_REPLACEMENTS = {
    "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko": REALTEK_BUNDLE / "modules/rtl_pci.ko",
    "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko": REALTEK_BUNDLE / "modules/rtl8192ee.ko",
}
RADIO2G_HASHES = "usr/share/openmitrastar/radio2g/artifacts.sha256"
RADIO2G_LOADER = "usr/sbin/om-radio-modules"
COMPENSATION_ENTRIES = (
    "usr/share/openmitrastar/radio2g/bundle-manifest.json",
    "usr/share/openmitrastar/radio5g/q3-dual-radio-build-manifest.json",
    "usr/share/openmitrastar/q3-w3-direct-emac.json",
)

OLD_PARAMS = (
    "hgw500_force_data_mcs7=0 hgw500_force_data_mcs15=1 "
    "hgw500_force_data_11m=0 hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=1"
)
NEW_PARAMS = (
    "hgw500_force_data_mcs7=0 hgw500_force_data_mcs15=1 "
    "hgw500_force_data_ht40sgi=1 hgw500_force_data_11m=0 "
    "hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=1"
)
OLD_VERIFY = (
    "hgw500_force_data_mcs7=N hgw500_force_data_mcs15=Y \\\n"
    "\t\t\thgw500_force_data_11m=N hgw500_txbd_be_data_split=N \\\n"
    "\t\t\thgw500_tx_rate_trace=Y"
)
NEW_VERIFY = (
    "hgw500_force_data_mcs7=N hgw500_force_data_mcs15=Y \\\n"
    "\t\t\thgw500_force_data_ht40sgi=Y hgw500_force_data_11m=N \\\n"
    "\t\t\thgw500_txbd_be_data_split=N hgw500_tx_rate_trace=Y"
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
    missing = [needle for needle in (OLD_PARAMS, OLD_VERIFY) if needle not in text]
    if missing:
        raise SystemExit(f"F93 om-radio-modules missing expected F94 markers: {missing!r}")
    patched = text.replace(OLD_PARAMS, NEW_PARAMS, 1).replace(OLD_VERIFY, NEW_VERIFY, 1)
    patched = patched.replace("profile=mcs7-noguard-nosplit", "profile=mcs15-ht40sgi-noguard-nosplit")
    patched = patched.replace("profile=all64-mcs7-eapol-mgntq-noguard-nosplit", "profile=all64-mcs15-ht40sgi-eapol-mgntq-noguard-nosplit")
    patched_bytes = patched.encode("ascii")
    return patched_bytes, {
        "entry": RADIO2G_LOADER,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": len(patched_bytes) - len(data),
        "old_sha256": f71.sha256(data),
        "new_sha256": f71.sha256(patched_bytes),
        "applied": ["radio2g-enable-mcs15-ht40sgi-descfix"],
        "fix": "load RTL8192EE with hgw500_force_data_ht40sgi=1 and verify the parameter",
    }


def patch_hashes(data: bytes, replacement_hashes: dict[str, str]) -> tuple[bytes, dict[str, object]]:
    lines = data.decode("ascii").splitlines()
    changed: list[dict[str, str]] = []
    out: list[str] = []
    for line in lines:
        if not line.strip():
            out.append(line)
            continue
        old_hash, path = line.split(None, 1)
        normalized = path.lstrip("/")
        new_hash = replacement_hashes.get(normalized)
        if new_hash:
            changed.append({"path": path, "old_sha256": old_hash, "new_sha256": new_hash})
            out.append(f"{new_hash} {path}")
        else:
            out.append(line)
    if sorted(item["path"].lstrip("/") for item in changed) != sorted(replacement_hashes):
        raise SystemExit("F94 radio2g hash update did not touch every replacement")
    patched = ("\n".join(out) + "\n").encode("ascii")
    return patched, {
        "entry": RADIO2G_HASHES,
        "old_bytes": len(data),
        "new_bytes": len(patched),
        "delta_bytes": len(patched) - len(data),
        "old_sha256": f71.sha256(data),
        "new_sha256": f71.sha256(patched),
        "updated": changed,
    }


def compact_json_entry(entry: f71.CpioEntry, target_size: int | None) -> tuple[f71.CpioEntry, dict[str, object]]:
    obj = json.loads(entry.data.decode("ascii"))
    compact = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    if target_size is not None:
        if len(compact) > target_size:
            raise SystemExit(
                f"F95 compensation entry {entry.name} compact JSON exceeds target size "
                f"{len(compact)} > {target_size}"
            )
        compact = compact.rstrip(b"\n") + (b" " * (target_size - len(compact))) + b"\n"
        if len(compact) != target_size:
            raise SystemExit(f"F95 compensation entry {entry.name} target sizing failed")
    return replace_entry(entry, compact), {
        "entry": entry.name,
        "old_bytes": len(entry.data),
        "new_bytes": len(compact),
        "delta_bytes": len(compact) - len(entry.data),
        "old_sha256": f71.sha256(entry.data),
        "new_sha256": f71.sha256(compact),
        "method": "json-compact-fixed-size-padding" if target_size is not None else "json-compact",
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    reports: dict[str, object] = {}
    replacement_hashes = {
        name: f71.sha256(path.read_bytes())
        for name, path in MODULE_REPLACEMENTS.items()
    }
    seen = set()
    for entry in entries:
        if entry.name in MODULE_REPLACEMENTS:
            replacement = MODULE_REPLACEMENTS[entry.name].read_bytes()
            seen.add(entry.name)
            reports[entry.name] = {
                "old_bytes": len(entry.data),
                "new_bytes": len(replacement),
                "delta_bytes": len(replacement) - len(entry.data),
                "old_sha256": f71.sha256(entry.data),
                "new_sha256": f71.sha256(replacement),
            }
            patched_entries.append(replace_entry(entry, replacement))
        elif entry.name == RADIO2G_HASHES:
            patched_hashes, report = patch_hashes(entry.data, replacement_hashes)
            reports[RADIO2G_HASHES] = report
            patched_entries.append(replace_entry(entry, patched_hashes))
        elif entry.name == RADIO2G_LOADER:
            patched_loader, report = patch_loader(entry.data)
            reports[RADIO2G_LOADER] = report
            patched_entries.append(replace_entry(entry, patched_loader))
        else:
            patched_entries.append(entry)
    missing = sorted(set(MODULE_REPLACEMENTS) - seen)
    for required in (RADIO2G_HASHES, RADIO2G_LOADER):
        if required not in reports:
            missing.append(required)
    if missing:
        raise SystemExit(f"missing F94 CPIO entries: {missing!r}")

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    interim = raw[:start] + interim_cpio + remainder
    interim_start, _interim_entries, interim_remainder = f71.parse_first_cpio(interim)
    if interim_start != start or interim_remainder != remainder:
        raise SystemExit("F95 interim patch changed CPIO framing")
    bytes_to_remove = len(interim) - len(raw)
    if bytes_to_remove <= 0 or bytes_to_remove % 4 != 0:
        raise SystemExit(f"F95 fixed-size compensation expected positive 4-byte delta, got {bytes_to_remove}")

    compensated: list[f71.CpioEntry] = []
    remaining = bytes_to_remove
    compensation_reports: dict[str, object] = {}
    for entry in patched_entries:
        if entry.name not in COMPENSATION_ENTRIES or remaining == 0:
            compensated.append(entry)
            continue
        target_size = None
        compacted, report = compact_json_entry(entry, target_size)
        saving = len(entry.data) - len(compacted.data)
        if saving <= 0:
            raise SystemExit(f"F95 compensation entry {entry.name} did not shrink")
        if target_size is None and saving > remaining:
            target_size = len(entry.data) - remaining
            compacted, report = compact_json_entry(entry, target_size)
            saving = remaining
        if target_size is None and saving % 4 != 0:
            aligned_saving = saving - (saving % 4)
            if aligned_saving <= 0:
                raise SystemExit(f"F95 compensation entry {entry.name} aligned saving is zero")
            target_size = len(entry.data) - aligned_saving
            compacted, report = compact_json_entry(entry, target_size)
            saving = aligned_saving
        if saving % 4 != 0:
            raise SystemExit(f"F95 compensation entry {entry.name} produced non-aligned saving {saving}")
        remaining -= saving
        compensation_reports[entry.name] = report
        compensated.append(compacted)
    if remaining != 0:
        raise SystemExit(f"F95 fixed-size compensation incomplete, remaining={remaining}")

    patched_entries = compensated
    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start:
        raise SystemExit("F94 patch changed CPIO start")
    if new_remainder != remainder:
        raise SystemExit("F94 patch changed post-CPIO remainder")
    if len(result) != len(raw):
        raise SystemExit("F95 fixed-size patch changed decompressed payload size")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F95 fixed-size patch changed CPIO end")
    reports["cpio"] = {
        "start": start,
        "old_end": len(raw) - len(remainder),
        "new_end": len(result) - len(new_remainder),
        "old_raw_bytes": len(raw),
        "new_raw_bytes": len(result),
        "delta_bytes": len(result) - len(raw),
        "uncompensated_delta_bytes": bytes_to_remove,
        "remainder_bytes": len(remainder),
        "remainder_sha256": f71.sha256(remainder),
    }
    reports["fixed_size_compensation"] = {
        "entries": compensation_reports,
        "removed_bytes": bytes_to_remove,
        "raw_bytes_preserved": True,
        "cpio_end_preserved": True,
    }
    return result, reports


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{SRC_BASE}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{SRC_BASE}.config"
    source_manifest = SRC_BUILD / "manifest.json"
    realtek_manifest = REALTEK_BUNDLE / "manifest.json"
    required_inputs = [
        source_raw,
        source_uncompressed,
        source_config,
        source_manifest,
        realtek_manifest,
        f71.TEMPLATE,
        f71.BOOTBASE,
        f71.LEGACY_LZMA,
        *MODULE_REPLACEMENTS.values(),
    ]
    for required in required_inputs:
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

    raw_path.write_bytes(raw)
    shutil.copy2(source_config, config_path)
    f71.write_uimage(source_uncompressed, raw, uncompressed_path, compression=0)
    encoded = f71.encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
        raise SystemExit("LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F95 persistent entry contract failed")

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

    artifacts = {
        "rootfs": raw_path,
        "decompressed_payload": raw_path,
        "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "kconfig": config_path,
    }
    source_manifest_json = json.loads(source_manifest.read_text(encoding="utf-8"))
    realtek_manifest_json = json.loads(realtek_manifest.read_text(encoding="utf-8"))
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93/v1",
        "classification": "F95_FROM_F93_2G_MCS15_HT40SGI_DESCRIPTOR_FIX_FIXEDSIZE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
        },
        "realtek_bundle": {
            "path": str(REALTEK_BUNDLE.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(realtek_manifest.read_bytes()),
            "rtl_pci_sha256": patch_report[MODULE_REPLACEMENTS.keys().__iter__().__next__()]["new_sha256"],
            "rtl8192ee_sha256": patch_report["lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko"]["new_sha256"],
            "kernel_release": realtek_manifest_json.get("kernel_release"),
        },
        "change_scope": {
            "radio2g_modules": "replaced only rtl_pci.ko and rtl8192ee.ko from the F94 Realtek incremental bundle",
            "radio2g_descriptor": "corrected TX_RATE, DATA_BW and SHORTGI descriptor bit ownership in rtl8192ee",
            "radio2g_loader": "enabled hgw500_force_data_ht40sgi=1 together with existing forced MCS15 and tx_rate_trace=1",
            "fixed_size_contract": "preserved F93 raw payload size, CPIO end and post-CPIO remainder by compacting inert JSON manifests",
            "radio2g_hostapd": "unchanged from F93: HT40+/short-GI via ht_capab and no explicit secondary_channel",
            "radio2g_dma_rings_queues_bridge": "unchanged policy from F93",
            "radio5g_default": "unchanged from F93",
            "qdrv": "unchanged from F93",
            "flash_layout": "unchanged",
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

    tftp_copy = ROOT / "work/tftp/omvl" / web_path.name
    tftp_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(web_path, tftp_copy)
    full_slot = web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93-build/v1",
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
