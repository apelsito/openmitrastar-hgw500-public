#!/usr/bin/env python3
"""Build F99 from F98 by replacing only rtl8192ee.ko.

F98 proved 2.4 GHz service but stayed slow: unicast TX was still reported as
MCS0/6.5 Mbit/s even with hgw500_force_data_mcs7=1.  F99 keeps the F98
firmware, loader, EMAC, bridge and 5 GHz stack unchanged, and replaces only the
RTL8192EE leaf module with the fixed-rate descriptor build.  The larger module
is compensated by compacting inert JSON manifests so the raw payload size, CPIO
end, post-CPIO remainder and persistent entry bytes remain fixed.
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
BUILD_TAG = "f99-2g-mcs7-fixedrate-from-f98"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F99_FROM_F98_2G_RTL8192EE_MCS7_FIXEDRATE_FIXEDSIZE"
MODULE_SCOPE = "replaced only rtl8192ee.ko with the F99 fixed-rate descriptor build"
RATE_SCOPE = "sets ptcb_desc hw_rate MCS7, 20 MHz packet bandwidth, long GI, driver rate enabled, fallback disabled"

F98_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f98-2g-reclaim-poll-from-f97/build"
F98_BASE = "openmitrastar-linux510-q3-persistent-f98-2g-reclaim-poll-from-f97-LZMA-OFFLINE-NO-FLASH"
REALTEK_BUNDLE = ROOT / "outputs/kernel-port/realtek-loop/all64-mcs7-fixedrate-f99-RAM-ONLY-NO-FLASH"

RTL8192EE_ENTRY = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko"
MODULE_REPLACEMENTS = {
    RTL8192EE_ENTRY: REALTEK_BUNDLE / "modules/rtl8192ee.ko",
}
RADIO2G_HASHES = "usr/share/openmitrastar/radio2g/artifacts.sha256"
RADIO2G_MANIFEST = "usr/share/openmitrastar/radio2g/bundle-manifest.json"
COMPENSATION_ENTRIES = (
    RADIO2G_MANIFEST,
    "usr/share/openmitrastar/radio5g/q3-dual-radio-build-manifest.json",
    "usr/share/openmitrastar/q3-w3-direct-emac.json",
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
        raise SystemExit("F99 radio2g hash update did not touch every replacement")
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


def patch_radio2g_manifest(data: bytes, replacement_hashes: dict[str, str]) -> tuple[bytes, dict[str, object]]:
    obj = json.loads(data.decode("ascii"))
    changed: list[dict[str, str]] = []

    def update_node(node: object) -> None:
        if isinstance(node, dict):
            path = node.get("path")
            if isinstance(path, str):
                normalized = path.lstrip("/")
                new_hash = replacement_hashes.get(normalized)
                if new_hash and node.get("sha256") != new_hash:
                    changed.append({"path": path, "old_sha256": str(node.get("sha256")), "new_sha256": new_hash})
                    node["sha256"] = new_hash
            for value in node.values():
                update_node(value)
        elif isinstance(node, list):
            for value in node:
                update_node(value)

    update_node(obj)
    patched = json.dumps(obj, indent=2, sort_keys=True).encode("ascii") + b"\n"
    return patched, {
        "entry": RADIO2G_MANIFEST,
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
                f"F99 compensation entry {entry.name} compact JSON exceeds target size "
                f"{len(compact)} > {target_size}"
            )
        compact = compact.rstrip(b"\n") + (b" " * (target_size - len(compact))) + b"\n"
        if len(compact) != target_size:
            raise SystemExit(f"F99 compensation entry {entry.name} target sizing failed")
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
    replacement_hashes = {
        name: f71.sha256(path.read_bytes())
        for name, path in MODULE_REPLACEMENTS.items()
    }
    patched_entries: list[f71.CpioEntry] = []
    reports: dict[str, object] = {}
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
        elif entry.name == RADIO2G_MANIFEST:
            patched_manifest, report = patch_radio2g_manifest(entry.data, replacement_hashes)
            reports[RADIO2G_MANIFEST] = report
            patched_entries.append(replace_entry(entry, patched_manifest))
        else:
            patched_entries.append(entry)

    missing = sorted(set(MODULE_REPLACEMENTS) - seen)
    for required in (RADIO2G_HASHES, RADIO2G_MANIFEST):
        if required not in reports:
            missing.append(required)
    if missing:
        raise SystemExit(f"missing F99 CPIO entries: {missing!r}")

    interim_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    interim = raw[:start] + interim_cpio + remainder
    interim_start, _interim_entries, interim_remainder = f71.parse_first_cpio(interim)
    if interim_start != start or interim_remainder != remainder:
        raise SystemExit("F99 interim patch changed CPIO framing")
    bytes_to_remove = len(interim) - len(raw)
    if bytes_to_remove <= 0 or bytes_to_remove % 4 != 0:
        raise SystemExit(f"F99 fixed-size compensation expected positive 4-byte delta, got {bytes_to_remove}")

    compensated: list[f71.CpioEntry] = []
    remaining = bytes_to_remove
    compensation_reports: dict[str, object] = {}
    for entry in patched_entries:
        if entry.name not in COMPENSATION_ENTRIES or remaining == 0:
            compensated.append(entry)
            continue
        compacted, report = compact_json_entry(entry, None)
        saving = len(entry.data) - len(compacted.data)
        if saving <= 0:
            raise SystemExit(f"F99 compensation entry {entry.name} did not shrink")
        if saving > remaining:
            target_size = len(entry.data) - remaining
            compacted, report = compact_json_entry(entry, target_size)
            saving = remaining
        elif saving % 4 != 0:
            aligned_saving = saving - (saving % 4)
            if aligned_saving <= 0:
                raise SystemExit(f"F99 compensation entry {entry.name} aligned saving is zero")
            target_size = len(entry.data) - aligned_saving
            compacted, report = compact_json_entry(entry, target_size)
            saving = aligned_saving
        if saving % 4 != 0:
            raise SystemExit(f"F99 compensation entry {entry.name} produced non-aligned saving {saving}")
        remaining -= saving
        compensation_reports[entry.name] = report
        compensated.append(compacted)
    if remaining != 0:
        raise SystemExit(f"F99 fixed-size compensation incomplete, remaining={remaining}")

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in compensated)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if new_start != start:
        raise SystemExit("F99 fixed-size patch changed CPIO start")
    if new_remainder != remainder:
        raise SystemExit("F99 fixed-size patch changed post-CPIO remainder")
    if len(result) != len(raw):
        raise SystemExit("F99 fixed-size patch changed decompressed payload size")
    if new_cpio_end != old_cpio_end:
        raise SystemExit("F99 fixed-size patch changed CPIO end")

    reports["cpio"] = {
        "start": start,
        "old_end": old_cpio_end,
        "new_end": new_cpio_end,
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
    source_raw = F98_BUILD / f"{F98_BASE}.decompressed.bin"
    source_uncompressed = F98_BUILD / f"{F98_BASE}.uncompressed.uImage"
    source_config = F98_BUILD / f"{F98_BASE}.config"
    source_dtb = F98_BUILD / f"{F98_BASE}.dtb"
    source_vmlinux = F98_BUILD / f"{F98_BASE}.vmlinux"
    source_manifest = F98_BUILD / "manifest.json"
    source_result = F98_BUILD / "build-result.json"
    realtek_manifest = REALTEK_BUNDLE / "manifest.json"
    required_inputs = [
        source_raw,
        source_uncompressed,
        source_config,
        source_dtb,
        source_vmlinux,
        source_manifest,
        source_result,
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
    dtb_path = OUT / f"{BASE_OUT}.dtb"
    vmlinux_path = OUT / f"{BASE_OUT}.vmlinux"

    raw_path.write_bytes(raw)
    shutil.copy2(source_config, config_path)
    shutil.copy2(source_dtb, dtb_path)
    shutil.copy2(source_vmlinux, vmlinux_path)
    f71.write_uimage(source_uncompressed, raw, uncompressed_path, compression=0)
    encoded = f71.encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
        raise SystemExit("F99 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F99 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F99 persistent entry contract failed")

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
    realtek_manifest_json = json.loads(realtek_manifest.read_text(encoding="utf-8"))
    manifest = {
        "schema": f"openmitrastar.q3-persistent-composite-{BUILD_TAG}/v1",
        "classification": CLASSIFICATION,
        "source": {
            "build_dir": str(F98_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
            "candidate_sha256": source_result_json["candidate_sha256"],
        },
        "realtek_bundle": {
            "path": str(REALTEK_BUNDLE.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(realtek_manifest.read_bytes()),
            "rtl8192ee_sha256": patch_report[RTL8192EE_ENTRY]["new_sha256"],
            "kernel_release": realtek_manifest_json.get("kernel_release"),
        },
        "change_scope": {
            "radio2g_module": MODULE_SCOPE,
            "radio2g_loader": "unchanged from F98: hgw500_force_data_mcs7=1 and hgw500_tx_reclaim_poll=1 remain active",
            "radio2g_hashes": "updated only the rtl8192ee.ko sha256 references",
            "radio2g_fixedrate": RATE_SCOPE,
            "radio2g_dma_rings_queues_bridge": "unchanged from F98",
            "kernel_emac": "unchanged from F98",
            "radio5_modules": "unchanged from F98",
            "qdrv": "unchanged from F98",
            "flash_layout": "unchanged",
            "rootfs_initramfs": "fixed-size CPIO patch; raw payload size, CPIO end and post-CPIO remainder preserved",
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
        "schema": f"openmitrastar.{BUILD_TAG}-build/v1",
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
