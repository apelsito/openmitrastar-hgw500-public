#!/usr/bin/env python3
"""Build F73 from F70 with an offset-preserving /usr/sbin/call_qcsapi.

F71/F72 changed the initramfs CPIO length.  On this image family the first CPIO
archive is followed by a non-trivial remainder, so growing the CPIO shifts later
bytes and can produce a Bootbase-valid image that dies before Linux printk.

F73 keeps F70's decompressed payload length and CPIO end offset unchanged.  It
repurposes one non-critical web image entry whose name length exactly matches
``usr/sbin/call_qcsapi`` and replaces its payload with a padded shell wrapper
that invokes the embedded Quantenna qcsapi runtime loader explicitly.
"""
from __future__ import annotations

import json
import lzma
import shutil
import stat
import subprocess
import sys
import time
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f73-5g-qcsapi-path-fixed"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SOURCE_ENTRY = "www/img/icon_eye.png"
TARGET_ENTRY = "usr/sbin/call_qcsapi"
QCSAPI_RUNTIME = "/usr/libexec/openmitrastar/qcsapi-runtime"
WRAPPER_CORE = f"""#!/bin/ash
r={QCSAPI_RUNTIME}
exec "$r/lib/ld-uClibc-0.9.29.so" --library-path "$r/lib${{LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}}" "$r/bin/call_qcsapi" "$@"
""".encode("ascii")


def padded_wrapper(size: int) -> bytes:
    if len(WRAPPER_CORE) > size:
        raise SystemExit(f"wrapper is {len(WRAPPER_CORE)} bytes, target entry is only {size}")
    pad = size - len(WRAPPER_CORE)
    if pad == 0:
        return WRAPPER_CORE
    comment = b"# openmitrastar-f73-qcsapi-path-fixed padding\n"
    out = bytearray(WRAPPER_CORE)
    while len(out) + len(comment) <= size:
        out.extend(comment)
    if len(out) < size:
        out.extend(b"#" * (size - len(out)))
    return bytes(out)


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    names = {entry.name for entry in entries}
    required = {
        f"{QCSAPI_RUNTIME.strip('/')}/bin/call_qcsapi",
        f"{QCSAPI_RUNTIME.strip('/')}/lib/ld-uClibc-0.9.29.so",
        f"{QCSAPI_RUNTIME.strip('/')}/lib/libqcsapi.so.1.0.1",
        f"{QCSAPI_RUNTIME.strip('/')}/manifest.sha256",
        SOURCE_ENTRY,
    }
    missing = sorted(required - names)
    if missing:
        raise SystemExit(f"F70 missing expected entries: {missing}")
    if TARGET_ENTRY in names:
        raise SystemExit(f"F70 already contains target entry: {TARGET_ENTRY}")
    if len(SOURCE_ENTRY) != len(TARGET_ENTRY):
        raise SystemExit("source and target CPIO names must have identical byte length")

    patched_entries: list[f71.CpioEntry] = []
    source_size = 0
    source_sha = ""
    for entry in entries:
        if entry.name != SOURCE_ENTRY:
            patched_entries.append(entry)
            continue
        source_size = len(entry.data)
        source_sha = f71.sha256(entry.data)
        patched_entries.append(
            f71.CpioEntry(
                name=TARGET_ENTRY,
                mode=stat.S_IFREG | 0o755,
                data=padded_wrapper(source_size),
                ino=entry.ino,
                uid=entry.uid,
                gid=entry.gid,
                nlink=1,
                mtime=int(time.mktime((2026, 8, 26, 0, 0, 0, 0, 0, 0))),
                devmajor=entry.devmajor,
                devminor=entry.devminor,
                rdevmajor=entry.rdevmajor,
                rdevminor=entry.rdevminor,
            )
        )

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    patched = raw[:start] + patched_cpio + remainder
    new_start, new_entries, new_remainder = f71.parse_first_cpio(patched)
    new_cpio_end = len(patched) - len(new_remainder)
    if len(patched) != len(raw):
        raise SystemExit("fixed-offset patch changed decompressed payload size")
    if new_start != start or new_cpio_end != old_cpio_end:
        raise SystemExit("fixed-offset patch changed CPIO placement")
    if new_remainder != remainder:
        raise SystemExit("fixed-offset patch changed post-CPIO remainder")
    new_names = {entry.name for entry in new_entries}
    if TARGET_ENTRY not in new_names or SOURCE_ENTRY in new_names:
        raise SystemExit("fixed-offset patch did not replace the intended CPIO entry")

    wrapper = next(entry for entry in new_entries if entry.name == TARGET_ENTRY).data
    return patched, {
        "cpio_start": start,
        "cpio_end": old_cpio_end,
        "old_raw_bytes": len(raw),
        "new_raw_bytes": len(patched),
        "delta_bytes": 0,
        "remainder_bytes": len(remainder),
        "remainder_sha256": f71.sha256(remainder),
        "replaced": {
            "old_path": SOURCE_ENTRY,
            "old_mode": "0100777",
            "old_bytes": source_size,
            "old_sha256": source_sha,
            "new_path": TARGET_ENTRY,
            "new_mode": "0100755",
            "new_bytes": len(wrapper),
            "new_sha256": f71.sha256(wrapper),
            "wrapper_core_bytes": len(WRAPPER_CORE),
            "padding_bytes": len(wrapper) - len(WRAPPER_CORE),
        },
        "explicit_loader": f"{QCSAPI_RUNTIME}/lib/ld-uClibc-0.9.29.so",
        "global_interpreter_symlink": False,
        "boot_path_risk": "CPIO size, CPIO end offset and post-CPIO remainder are unchanged from F70",
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = f71.SRC_BUILD / f"{f71.SRC_BASE}.decompressed.bin"
    source_uncompressed = f71.SRC_BUILD / f"{f71.SRC_BASE}.uncompressed.uImage"
    source_config = f71.SRC_BUILD / f"{f71.SRC_BASE}.config"
    source_manifest = f71.SRC_BUILD / "manifest.json"
    for required in (
        source_raw,
        source_uncompressed,
        source_config,
        source_manifest,
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
        "schema": "openmitrastar.q3-persistent-composite-f73-qcsapi-path-fixed/v1",
        "classification": "F73_FIXED_OFFSET_FROM_F70_QCSAPI_PATH_WRAPPER_ONLY",
        "source": {
            "build_dir": str(f71.SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
        },
        "change_scope": {
            "qcsapi_runtime": "exposes /usr/sbin/call_qcsapi by replacing a non-critical UI image entry of identical CPIO name length and payload size",
            "global_ld_uclibc": "unchanged from F70; no /lib/ld-uClibc.so.0 symlink added",
            "radio2g_modules": "unchanged from F70",
            "radio5_modules": "unchanged from F70",
            "qdrv": "unchanged from F70",
            "queues_dma_rates_rings": "unchanged from F70",
            "bridge_topology": "unchanged from F70",
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
        "schema": "openmitrastar.f73-qcsapi-path-fixed-build/v1",
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
