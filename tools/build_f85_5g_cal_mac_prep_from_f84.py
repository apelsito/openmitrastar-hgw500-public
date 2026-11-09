#!/usr/bin/env python3
"""Build F85 from F84 by preparing Quantenna calibration/MAC at boot.

F84 fixes 2.4 GHz boot, bridge and throughput while preserving F83 post-hostapd staging. Its 5 GHz module stage still
fails after a clean boot because S53/S54 skip their producers while the 5 GHz
autostart feature gate is closed.  The manual 5 GHz stage needs those read-only
runtime files before loading qdrv.

F85 keeps S55 autostart gated, but lets S53/S54 prepare calibration and MAC
whenever RADIO5G_ENABLE=1.  This writes only /run runtime state at boot and
does not start RF or qdrv automatically.
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
BUILD_TAG = "f85-5g-cal-mac-prep-after-f84"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f84-2g-mcs7-param-fix-5g-post-hostapd-stage/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f84-2g-mcs7-param-fix-5g-post-hostapd-stage-LZMA-OFFLINE-NO-FLASH"

PATCHES = {
    "etc/init.d/S53-qtn-calibration": (
        """feature=${OM_RADIO5_FEATURE:-/etc/openmitrastar/features/q3-radio5-autostart}

case "${1:-start}" in
start)
\tfeature_value=$(sed -n '1{s/\\r$//;p;}' "$feature" 2>/dev/null || true)
\t[ "$feature_value" = Q3_RADIO5_AUTOSTART=1 ] || {
\t\tprintf '%s\\n' 'OMQTNCAL_SKIPPED reason=autostart-gate-closed'
\t\texit 0
\t}
""",
        """case "${1:-start}" in
start)
\tradio5_enable=$(/usr/sbin/om-config-get RADIO5G_ENABLE 2>/dev/null || printf 1)
\t[ "$radio5_enable" = 1 ] || {
\t\tprintf '%s\\n' 'OMQTNCAL_SKIPPED reason=radio5-disabled'
\t\texit 0
\t}
""",
    ),
    "etc/init.d/S54-qtn-mac": (
        """feature=${OM_RADIO5_FEATURE:-/etc/openmitrastar/features/q3-radio5-autostart}

case "${1:-start}" in
start)
\tfeature_value=$(sed -n '1{s/\\r$//;p;}' "$feature" 2>/dev/null || true)
\t[ "$feature_value" = Q3_RADIO5_AUTOSTART=1 ] || {
\t\tprintf '%s\\n' 'OMQTN_MAC_SKIPPED reason=autostart-gate-closed'
\t\texit 0
\t}
""",
        """case "${1:-start}" in
start)
\tradio5_enable=$(/usr/sbin/om-config-get RADIO5G_ENABLE 2>/dev/null || printf 1)
\t[ "$radio5_enable" = 1 ] || {
\t\tprintf '%s\\n' 'OMQTN_MAC_SKIPPED reason=radio5-disabled'
\t\texit 0
\t}
""",
    ),
}


def strip_comments(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#") and not line.startswith("#!"):
            continue
        kept.append(line)
    return "".join(kept)


def patch_entry(name: str, data: bytes) -> tuple[bytes, dict[str, object]]:
    if name not in PATCHES:
        return data, {}
    old, new = PATCHES[name]
    text = data.decode("ascii")
    if old not in text:
        raise SystemExit(f"{name} missing feature-gated producer block")
    patched = text.replace(old, new, 1)
    patched_bytes = patched.encode("ascii")
    if len(patched_bytes) > len(data):
        patched_bytes = strip_comments(patched).encode("ascii")
    if len(patched_bytes) > len(data):
        raise SystemExit(f"{name} grew by {len(patched_bytes) - len(data)} bytes")
    padding = len(data) - len(patched_bytes)
    if padding:
        patched_bytes += (b"\n# f85 fixed-size padding " + b"#" * padding)[:padding]
    if len(patched_bytes) != len(data):
        raise SystemExit(f"{name} fixed-size padding failed")
    return patched_bytes, {
        "entry": name,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": 0,
        "old_sha256": f71.sha256(data),
        "new_sha256": f71.sha256(patched_bytes),
        "padding_bytes": padding,
        "fix": "prepare 5g calibration/MAC when RADIO5G_ENABLE=1 even if autostart remains gated",
    }


def patch_cpio(raw: bytes) -> tuple[bytes, list[dict[str, object]]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    reports: list[dict[str, object]] = []
    seen = set()
    for entry in entries:
        patched_data, report = patch_entry(entry.name, entry.data)
        if report:
            seen.add(entry.name)
            reports.append(report)
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
    missing = set(PATCHES) - seen
    if missing:
        raise SystemExit(f"missing CPIO entries: {sorted(missing)}")
    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if len(result) != len(raw):
        raise SystemExit("F85 patch changed decompressed payload size")
    if new_start != start or new_cpio_end != old_cpio_end:
        raise SystemExit("F85 patch changed CPIO placement")
    if new_remainder != remainder:
        raise SystemExit("F85 patch changed post-CPIO remainder")
    for report in reports:
        report.update({
            "cpio_start": start,
            "cpio_end": old_cpio_end,
            "raw_bytes": len(raw),
            "remainder_bytes": len(remainder),
            "remainder_sha256": f71.sha256(remainder),
        })
    return result, reports


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
    raw, patch_reports = patch_cpio(source_raw_bytes)
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
        "schema": "openmitrastar.q3-persistent-composite-f85-5g-cal-mac-prep-after-f84/v1",
        "classification": "F85_FIXED_OFFSET_FROM_F84_5G_CAL_MAC_PREP_AT_BOOT",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
        },
        "change_scope": {
            "radio2g": "unchanged from F84",
            "radio5g_autostart": "still feature-gated by S55; no automatic qdrv/RF start",
            "radio5g_preparation": "S53/S54 now prepare calibration and MAC when RADIO5G_ENABLE=1",
            "qdrv": "unchanged from F84",
            "flash_layout": "unchanged",
        },
        "patches": patch_reports,
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
        "schema": "openmitrastar.f85-5g-cal-mac-prep-after-f84-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": f71.sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": f71.sha256(full_slot),
        "full_slot_crc32": f71.crc32(full_slot),
        "build_dir": str(OUT),
        "tftp_copy": str(tftp_copy),
        "patches": patch_reports,
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

