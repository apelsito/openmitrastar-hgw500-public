#!/usr/bin/env python3
"""Build F77 from F76 with the best observed 2.4 GHz speed profile.

F76 is still the 5 GHz diagnostic base: autostart disabled and manual
``OM_RADIO5_STAGE_STOP=modules`` markers.  F77 changes only
``usr/sbin/om-radio-modules`` for the 2.4 GHz module parameters, restoring the
best measured AELITA profile from the 2026-08-25 probes:

* force data MCS7, not MCS15;
* disable TX queue guard and reclaim poll;
* keep all-64 TXBD width and BE split disabled.

This is an offline build. It does not open UART, SSH to the router, or flash.
"""
from __future__ import annotations

import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f77-2g-mcs7-noguard-5g-stage-guard"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f76-2g-stable-5g-control-stage-guard/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f76-2g-stable-5g-control-stage-guard-LZMA-OFFLINE-NO-FLASH"
MODULES_ENTRY = "usr/sbin/om-radio-modules"

REPLACEMENTS = (
    (
        "hgw500_tx_queue_guard=1 hgw500_tx_queue_guard_high=64 "
        "hgw500_tx_queue_guard_low=32 hgw500_tx_reclaim_poll=1",
        "hgw500_tx_queue_guard=0 hgw500_tx_queue_guard_high=64 "
        "hgw500_tx_queue_guard_low=32 hgw500_tx_reclaim_poll=0",
        "rtl_pci-load-disable-qguard-reclaim",
    ),
    ("hgw500_tx_queue_guard=Y", "hgw500_tx_queue_guard=N", "rtl_pci-verify-qguard-off"),
    ("hgw500_tx_reclaim_poll=Y", "hgw500_tx_reclaim_poll=N", "rtl_pci-verify-reclaim-off"),
    (
        "hgw500_force_data_mcs7=N hgw500_force_data_mcs15=Y",
        "hgw500_force_data_mcs7=Y hgw500_force_data_mcs15=N",
        "rtl8192ee-force-mcs7",
    ),
    (
        "profile=all64-mcs7-eapol-mgntq-qguard64r-nosplit-mcs15",
        "profile=all64-mcs7-eapol-mgntq-noguard-nosplit",
        "rtl_pci-profile-label",
    ),
    (
        "profile=qguard64r-nosplit-mcs15",
        "profile=mcs7-noguard-nosplit",
        "rtl8192ee-profile-label",
    ),
)


def patch_modules_script(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    patched = text
    applied: list[dict[str, object]] = []
    for old, new, label in REPLACEMENTS:
        count = patched.count(old)
        if count == 0:
            raise SystemExit(f"F77 missing expected marker {label}: {old}")
        patched = patched.replace(old, new)
        applied.append({"label": label, "count": count, "old": old, "new": new})

    patched_bytes = patched.encode("ascii")
    if len(patched_bytes) > len(data):
        raise SystemExit(f"F77 om-radio-modules grew by {len(patched_bytes) - len(data)} bytes")
    padding = len(data) - len(patched_bytes)
    if padding:
        patched_bytes += (b"\n# f77 fixed-size padding " + b"#" * padding)[:padding]
    if len(patched_bytes) != len(data):
        raise SystemExit("F77 fixed-size script padding failed")

    return patched_bytes, {
        "entry": MODULES_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": 0,
        "old_sha256": f71.sha256(data),
        "new_sha256": f71.sha256(patched_bytes),
        "applied": applied,
        "padding_bytes": padding,
        "fix": "restore best observed 2.4 GHz speed profile while preserving F76 5 GHz stage guard",
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    patch_report = None
    for entry in entries:
        if entry.name != MODULES_ENTRY:
            patched_entries.append(entry)
            continue
        patched_data, patch_report = patch_modules_script(entry.data)
        patched_entries.append(f71.CpioEntry(
            name=entry.name,
            mode=entry.mode,
            data=patched_data,
            ino=entry.ino,
            uid=entry.uid,
            gid=entry.gid,
            nlink=entry.nlink,
            mtime=entry.mtime,
            devmajor=entry.devmajor,
            devminor=entry.devminor,
            rdevmajor=entry.rdevmajor,
            rdevminor=entry.rdevminor,
        ))
    if patch_report is None:
        raise SystemExit(f"missing CPIO entry: {MODULES_ENTRY}")

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if len(result) != len(raw):
        raise SystemExit("F77 patch changed decompressed payload size")
    if new_start != start or new_cpio_end != old_cpio_end:
        raise SystemExit("F77 patch changed CPIO placement")
    if new_remainder != remainder:
        raise SystemExit("F77 patch changed post-CPIO remainder")
    patch_report.update({
        "cpio_start": start,
        "cpio_end": old_cpio_end,
        "raw_bytes": len(raw),
        "remainder_bytes": len(remainder),
        "remainder_sha256": f71.sha256(remainder),
    })
    return result, patch_report


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{SRC_BASE}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{SRC_BASE}.config"
    source_manifest = SRC_BUILD / "manifest.json"
    for required in (
        source_raw, source_uncompressed, source_config, source_manifest,
        f71.TEMPLATE, f71.BOOTBASE, f71.LEGACY_LZMA,
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
        "decompressed_payload": raw_path,
        "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "kconfig": config_path,
    }
    source_manifest_json = json.loads(source_manifest.read_text(encoding="utf-8"))
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f77-2g-fast-5g-stage-guard/v1",
        "classification": "F77_FIXED_OFFSET_FROM_F76_2G_FAST_PROFILE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
        },
        "change_scope": {
            "radio2g_loader": "MCS7, no queue guard, no reclaim poll, BE split off",
            "radio2g_modules": "unchanged from F76",
            "radio5_manual_script": "unchanged from F76; stage guard preserved",
            "radio5_modules": "unchanged from F76",
            "qdrv": "unchanged from F76",
            "bridge_topology": "unchanged from F76",
            "boot_flash": "unchanged from F76",
        },
        "evidence_basis": {
            "best_observed_2g_profile": "2026-08-25 AELITA throughput probes around 7.5-7.85 Mbps",
            "current_f75_2g_profile": "F75 measured 6.57 Mbps with qguard/reclaim and MCS15 forced",
            "hardware_proof": False,
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
        "slot": {
            "name": "linux_live",
            "bytes": f71.SLOT_BYTES,
            "candidate_bytes": web_path.stat().st_size,
            "fits": True,
        },
        "bootbase_contract": {
            "file": contract_path.name,
            "result": contract_json.get("result"),
            "candidate_accepted": contract_json.get("candidate", {}).get("accepted_by_contract"),
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
        "schema": "openmitrastar.f77-2g-fast-5g-stage-guard-build/v1",
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
        for path in sorted([*artifacts.values(), contract_path, manifest_path, result_path], key=lambda item: item.name):
            fh.write(f"{f71.sha256(path.read_bytes())}  {path.name}\n")

    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
