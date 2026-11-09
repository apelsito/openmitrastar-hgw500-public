#!/usr/bin/env python3
"""Build F110: F104 2.4 GHz baseline plus RC1 5 GHz manual stack.

F104 is the current measured 2.4 GHz baseline.  This builder keeps the F104
kernel, 2.4 GHz modules, loader parameters, bridge setup, SSH path and flash
layout unchanged, then replaces only the 5 GHz payload with the RC1 product
bundle.  5 GHz remains manual-only at boot.
"""
from __future__ import annotations

import json
import lzma
import os
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import verify_persistent_entry_contract as entry_contract


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f110-2g-f104-rc1-5g-manual"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f104-2g-be-guard16-from-f103/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f104-2g-be-guard16-from-f103-LZMA-OFFLINE-NO-FLASH"
RC1 = ROOT / "work/rc1-radio-drivers-20260824-extract/openmitrastar-linux510-radio-drivers-product-rc1-20260824"
RELEASE = "5.10.260-openmitrastar-radiohw"
RADIO5_DIR = f"lib/modules/{RELEASE}/openmitrastar/radio5g"
EPOCH = int(time.mktime((2026, 8, 27, 0, 0, 0, 0, 0, 0)))

FEATURE_OVERRIDES = {
    "etc/openmitrastar/features/q3-radio5-autostart": b"Q3_RADIO5_AUTOSTART=0\n",
    "usr/share/openmitrastar/radio5g/q3-radio5-autostart.feature": b"Q3_RADIO5_AUTOSTART=0\n",
    "etc/openmitrastar/features/q3-radio5-beacon-lifetime": b"Q3_RADIO5_BEACON_LIFETIME=0\n",
    "etc/openmitrastar/features/q3-radio5-beacon-preflight": b"Q3_RADIO5_BEACON_PREFLIGHT=0\n",
    "etc/openmitrastar/features/q3-radio5-qdrv9ba6-discriminator": b"Q3_RADIO5_QDRV9BA6=0\n",
    "etc/openmitrastar/features/q3-radio5-tqe512-discriminator": b"Q3_RADIO5_TQE_RING_ENTRIES=256\n",
}
REMOVED_PREFIXES = (
    "usr/libexec/openmitrastar/qcsapi-runtime",
    "usr/libexec/openmitrastar/w3-no-ioss",
)
REMOVED_EXACT = {
    "lib/ld-uClibc.so.0",
    "usr/sbin/call_qcsapi",
    "usr/share/openmitrastar/radio5g/direct-symbols-SHA256SUMS",
    "usr/share/openmitrastar/radio5g/direct-symbols-module-manifest.tsv",
    "usr/share/openmitrastar/radio5g/module-manifest.tsv",
    "usr/share/openmitrastar/radio5g/q3-dual-radio-build-manifest.json",
    "usr/share/openmitrastar/radio5g/runtime-contract.json",
    "usr/share/openmitrastar/radio5g/runtime.env",
}
PAD_ENTRY = "usr/share/openmitrastar/radio5g/f110-fixed-size.pad"


def cpio_entry(name: str, mode: int, data: bytes, ino: int) -> f71.CpioEntry:
    return f71.CpioEntry(
        name=name,
        mode=mode,
        data=data,
        ino=ino,
        uid=0,
        gid=0,
        nlink=2 if stat.S_ISDIR(mode) else 1,
        mtime=EPOCH,
    )


def ensure_dirs(payload: dict[str, tuple[int, bytes]], path: str) -> None:
    parts = path.split("/")[:-1]
    current = []
    for part in parts:
        current.append(part)
        dirname = "/".join(current)
        payload.setdefault(dirname, (stat.S_IFDIR | 0o755, b""))


def read_file(path: Path) -> bytes:
    if not path.is_file():
        raise SystemExit(f"missing RC1 input: {path}")
    return path.read_bytes()


def rc1_payload() -> dict[str, tuple[int, bytes]]:
    radio5 = RC1 / "radio5g"
    payload: dict[str, tuple[int, bytes]] = {}

    for module in sorted((radio5 / "modules").glob("*.ko")):
        target = f"{RADIO5_DIR}/{module.name}"
        payload[target] = (stat.S_IFREG | 0o644, read_file(module))

    for firmware in sorted((radio5 / "firmware").glob("*")):
        if not firmware.is_file():
            continue
        data = read_file(firmware)
        payload[f"lib/firmware/{firmware.name}"] = (stat.S_IFREG | 0o644, data)

    payload["usr/sbin/ram-insmod-qtn"] = (
        stat.S_IFREG | 0o755,
        read_file(radio5 / "ram-insmod-qtn"),
    )
    payload["usr/sbin/om-radio5-start"] = (
        stat.S_IFREG | 0o755,
        read_file(radio5 / "om-radio5-start-product"),
    )
    payload["usr/sbin/om-radio5-stop"] = (
        stat.S_IFREG | 0o755,
        read_file(radio5 / "om-radio5-stop-product"),
    )
    payload["usr/share/openmitrastar/radio5g/artifacts.sha256"] = (
        stat.S_IFREG | 0o644,
        read_file(radio5 / "artifacts.sha256"),
    )
    payload["usr/share/openmitrastar/radio5g/driver-contract.env"] = (
        stat.S_IFREG | 0o644,
        read_file(radio5 / "driver-contract.env"),
    )
    module_order = "\n".join(module.name for module in sorted((radio5 / "modules").glob("*.ko"))) + "\n"
    payload["usr/share/openmitrastar/radio5g/modules.order"] = (
        stat.S_IFREG | 0o644,
        module_order.encode("ascii"),
    )
    payload["usr/share/openmitrastar/radio5g/rc1-manifest.json"] = (
        stat.S_IFREG | 0o644,
        read_file(RC1 / "manifest.json"),
    )
    payload["usr/share/openmitrastar/radio5g/rc1-readme.md"] = (
        stat.S_IFREG | 0o644,
        read_file(RC1 / "README.md"),
    )

    for name, data in FEATURE_OVERRIDES.items():
        payload[name] = (stat.S_IFREG | 0o644, data)

    for name in list(payload):
        ensure_dirs(payload, name)
    return payload


def should_remove(name: str) -> bool:
    return name in REMOVED_EXACT or any(name == prefix or name.startswith(prefix + "/") for prefix in REMOVED_PREFIXES)


def pad_entry_for_bytes(needed: int, ino: int) -> f71.CpioEntry:
    if needed <= 0:
        raise SystemExit("internal error: padding requested without positive byte count")
    for size in range(max(0, needed - 512), needed + 1):
        entry = cpio_entry(PAD_ENTRY, stat.S_IFREG | 0o400, b"\0" * size, ino)
        if len(f71.serialize_entry(entry)) == needed:
            return entry
    raise SystemExit(f"cannot create exact fixed-size CPIO padding for {needed} bytes")


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    source_entries = {entry.name: entry for entry in entries}
    if entries[-1].name != "TRAILER!!!":
        raise SystemExit("source CPIO trailer missing")

    payload = rc1_payload()
    old_by_name = {entry.name: f71.sha256(entry.data) for entry in entries if entry.name in payload}
    max_ino = max(entry.ino for entry in entries)
    next_ino = max_ino + 1
    old_cpio_len = len(raw) - len(remainder) - start
    patched: list[f71.CpioEntry] = []
    seen: set[str] = set()
    removed: list[dict[str, object]] = []

    for entry in entries[:-1]:
        if should_remove(entry.name) and entry.name not in payload:
            removed.append({"path": entry.name, "bytes": len(entry.data), "serialized_bytes": len(f71.serialize_entry(entry))})
            continue
        replacement = payload.get(entry.name)
        if replacement is None:
            patched.append(entry)
            continue
        mode, data = replacement
        patched.append(cpio_entry(entry.name, mode, data, entry.ino))
        seen.add(entry.name)

    added_names = sorted(set(payload) - seen)
    for name in added_names:
        mode, data = payload[name]
        patched.append(cpio_entry(name, mode, data, next_ino))
        next_ino += 1

    without_trailer = b"".join(f71.serialize_entry(entry) for entry in patched)
    trailer_size = len(f71.serialize_entry(entries[-1]))
    pad_needed = old_cpio_len - len(without_trailer) - trailer_size
    if pad_needed < 0:
        raise SystemExit(f"F110 CPIO grew past fixed entry boundary by {-pad_needed} bytes")
    if pad_needed:
        pad = pad_entry_for_bytes(pad_needed, next_ino)
        patched.append(pad)
        next_ino += 1
    else:
        pad = None
    patched.append(entries[-1])
    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched)
    if len(patched_cpio) != old_cpio_len:
        raise SystemExit("F110 fixed-size CPIO padding failed")
    result = raw[:start] + patched_cpio + remainder
    new_start, new_entries, new_remainder = f71.parse_first_cpio(result)
    if new_start != start:
        raise SystemExit("F110 changed CPIO start")
    if new_remainder != remainder:
        raise SystemExit("F110 changed post-CPIO kernel remainder")

    names = {entry.name for entry in new_entries}
    required = {
        f"{RADIO5_DIR}/qdrv.ko",
        f"{RADIO5_DIR}/wlan.ko",
        f"{RADIO5_DIR}/fwt_ctrl.ko",
        f"{RADIO5_DIR}/wlan_scan_sta.ko",
        f"{RADIO5_DIR}/wlan_tkip.ko",
        "lib/firmware/auc_driver.default.0.bin",
        "usr/sbin/om-radio5-start",
        "usr/share/openmitrastar/radio5g/driver-contract.env",
    }
    missing = sorted(required - names)
    if missing:
        raise SystemExit("F110 missing required RC1 entries: " + ", ".join(missing))

    # Guard the 2.4 GHz contract: do not replace Realtek module payloads or the
    # F104 radio loader profile while staging the 5 GHz RC1 payload.
    protected = [
        "usr/sbin/om-radio-modules",
        f"lib/modules/{RELEASE}/openmitrastar/radio2g/rtl_pci.ko",
        f"lib/modules/{RELEASE}/openmitrastar/radio2g/rtl8192ee.ko",
    ]
    new_by_name = {entry.name: f71.sha256(entry.data) for entry in new_entries}
    for name in protected:
        if name in source_entries and new_by_name.get(name) != f71.sha256(source_entries[name].data):
            raise SystemExit(f"F110 changed protected 2.4 entry: {name}")

    rc1_contract = (RC1 / "radio5g/driver-contract.env").read_text(encoding="ascii")
    qdrv_sha = next(line.split("=", 1)[1].strip() for line in rc1_contract.splitlines() if line.startswith("QDRV_SHA256="))
    return result, {
        "cpio_start": start,
        "old_cpio_end": len(raw) - len(remainder),
        "new_cpio_end": len(result) - len(remainder),
        "old_raw_bytes": len(raw),
        "new_raw_bytes": len(result),
        "delta_bytes": len(result) - len(raw),
        "remainder_bytes": len(remainder),
        "remainder_sha256": f71.sha256(remainder),
        "replaced_count": len(seen),
        "added_count": len(added_names),
        "added": added_names,
        "removed_count": len(removed),
        "removed": removed,
        "padding": None if pad is None else {
            "entry": pad.name,
            "bytes": len(pad.data),
            "serialized_bytes": len(f71.serialize_entry(pad)),
            "sha256": f71.sha256(pad.data),
        },
        "feature_overrides": {name: data.decode("ascii").strip() for name, data in FEATURE_OVERRIDES.items()},
        "rc1_qdrv_sha256": qdrv_sha,
        "rc1_manifest_sha256": f71.sha256((RC1 / "manifest.json").read_bytes()),
        "old_replaced_sha256": old_by_name,
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
        RC1 / "manifest.json",
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
        raise SystemExit("F110 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F110 webformat exceeds linux_live slot")

    entry_contract_path = OUT / "entry-contract.json"
    if entry_contract.main_from_paths(source_raw, raw_path, entry_contract_path) != 0:
        raise SystemExit("F110 persistent entry contract failed")

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
    rc1_manifest_json = json.loads((RC1 / "manifest.json").read_text(encoding="utf-8"))
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f110-2g-f104-rc1-5g-manual/v1",
        "classification": "F110_FROM_F104_RC1_RADIO5_MANUAL_NO_AUTOSTART",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
            "candidate_sha256": source_result_json["candidate_sha256"],
            "full_slot_crc32": source_result_json["full_slot_crc32"],
        },
        "rc1": {
            "bundle_dir": str(RC1.relative_to(ROOT)),
            "manifest_sha256": f71.sha256((RC1 / "manifest.json").read_bytes()),
            "classification": rc1_manifest_json.get("classification"),
            "hardware_live_validated": rc1_manifest_json.get("hardware_live_validated"),
            "qdrv_sha256": rc1_manifest_json.get("radio5g", {}).get("qdrv_sha256"),
        },
        "change_scope": {
            "radio2g": "unchanged from F104 measured baseline",
            "radio5g": "RC1 modules, firmware, start/stop scripts and driver contract installed",
            "radio5_autostart": "disabled; manual /usr/sbin/om-radio5-start only",
            "legacy_5g_feature_flags": "beacon lifetime/preflight/qdrv9/tqe512 discriminators disabled for RC1 hash contract",
            "bridge": "unchanged at boot; wifi0 remains absent until manual 5G start",
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

    full_slot = web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f110-2g-f104-rc1-5g-manual-build/v1",
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
