#!/usr/bin/env python3
"""Build F93 from F90 with hostapd-compatible fixed-size HT40+/SGI config.

F92 proved that this router's embedded hostapd rejects an explicit
secondary_channel=1 line, while the same runtime derives HT40+ correctly from
ht_capab alone.  F93 keeps the F90 modules, rates, queues and flash layout,
adds only ht_capab, and compensates the added bytes by shortening an inert
comment in usr/sbin/om-radio-start so the entry size, CPIO end and raw payload
size stay exactly fixed.
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
BUILD_TAG = "f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f90-2g-mcs15-trace-after-f89/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f90-2g-mcs15-trace-after-f89-LZMA-OFFLINE-NO-FLASH"
PATCH_ENTRY = "usr/sbin/om-radio-start"

OLD_CONFIG_BLOCK = (
    "\t\t'ieee80211n=1' \\\n"
    "\t\t'wmm_enabled=1' \\\n"
)
NEW_CONFIG_BLOCK = (
    "\t\t'ieee80211n=1' \\\n"
    "\t\t'ht_capab=[HT40+][SHORT-GI-20][SHORT-GI-40][DSSS_CCK-40]' \\\n"
    "\t\t'wmm_enabled=1' \\\n"
)
OLD_COMMENT = (
    "# Q3 enables the block layer for read-only Origin import.  On this ARC/uClibc\n"
    "# combination hostapd's daemon(3) path returns ENODEV even though foreground\n"
    "# nl80211 AP setup is healthy.  Keep hostapd in foreground and let the service\n"
    "# supervisor own its PID instead of using -B.\n"
)
NEW_COMMENT = (
    "# Q3 keeps hostapd in foreground because daemon(3) returns ENODEV on this ARC/uClibc image while "
    "nl80211 AP setup is healthy. The supervisor owns its PID. F93 keeps HT40 derived by hostapd "
    "without secondary config OK.\n"
)


def patch_radio_start(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    missing = [marker for marker in (OLD_CONFIG_BLOCK, OLD_COMMENT) if marker not in text]
    if missing:
        raise SystemExit(f"F90 om-radio-start missing expected F93 patch markers: {missing!r}")
    if "secondary_channel=1" in text or "SHORT-GI-40" in text:
        raise SystemExit("F90 om-radio-start already contains F93 HT40/SGI markers")
    if len(NEW_CONFIG_BLOCK) - len(OLD_CONFIG_BLOCK) != len(OLD_COMMENT) - len(NEW_COMMENT):
        raise SystemExit("F93 fixed-size compensation is not balanced")
    patched = text.replace(OLD_CONFIG_BLOCK, NEW_CONFIG_BLOCK, 1).replace(OLD_COMMENT, NEW_COMMENT, 1)
    patched_bytes = patched.encode("ascii")
    if len(patched_bytes) != len(data):
        raise SystemExit("F93 patch must preserve usr/sbin/om-radio-start size")
    return patched_bytes, {
        "entry": PATCH_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": 0,
        "old_sha256": f71.sha256(data),
        "new_sha256": f71.sha256(patched_bytes),
        "applied": ["radio2g-hostapd-ht40plus-shortgi-hostapd-compat-fixedsize"],
        "fix": "advertise 2.4 GHz HT40+ and short guard interval without explicit secondary_channel",
        "added_hostapd_lines": [
            "ht_capab=[HT40+][SHORT-GI-20][SHORT-GI-40][DSSS_CCK-40]",
        ],
        "removed_hostapd_lines": [
            "secondary_channel=1",
        ],
        "size_compensation": "shortened an inert hostapd foreground-mode comment by 62 bytes",
    }


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    patch_report = None
    for entry in entries:
        if entry.name != PATCH_ENTRY:
            patched_entries.append(entry)
            continue
        patched_data, patch_report = patch_radio_start(entry.data)
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
        raise SystemExit(f"missing CPIO entry: {PATCH_ENTRY}")
    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if len(result) != len(raw):
        raise SystemExit("F93 patch changed decompressed payload size")
    if new_start != start or new_cpio_end != old_cpio_end:
        raise SystemExit("F93 patch changed CPIO placement")
    if new_remainder != remainder:
        raise SystemExit("F93 patch changed post-CPIO remainder")
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
    for required in (source_raw, source_uncompressed, source_config, source_manifest, f71.TEMPLATE, f71.BOOTBASE, f71.LEGACY_LZMA):
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
        "schema": "openmitrastar.q3-persistent-composite-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92/v1",
        "classification": "F93_FIXED_SIZE_FROM_F90_2G_HOSTAPD_HT40PLUS_SGI_COMPAT_EXPERIMENT",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
        },
        "change_scope": {
            "radio2g_hostapd": "advertise HT40+ and short GI in generated wlan0 hostapd.conf without explicit secondary_channel",
            "radio2g_script_size": "usr/sbin/om-radio-start preserved at the exact F90 byte length",
            "radio2g_modules": "unchanged binaries from F90",
            "radio2g_rates": "unchanged from F90: forced MCS15 with tx_rate_trace=1",
            "radio2g_dma_rings_queues_bridge": "unchanged from F90",
            "radio5g_default": "unchanged bounded post-hostapd default from F90",
            "qdrv": "unchanged from F90",
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
        "slot": {"name": "linux_live", "bytes": f71.SLOT_BYTES, "candidate_bytes": web_path.stat().st_size, "fits": True},
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
        "schema": "openmitrastar.f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92-build/v1",
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
