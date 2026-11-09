#!/usr/bin/env python3
"""Build F72 from F70 with a scoped qcsapi loader wrapper only.

F71 added a global /lib/ld-uClibc.so.0 symlink for qcsapi.  If early userland
also resolves that interpreter path, the change is too wide for a bootable
candidate.  F72 keeps the same F70 kernel, radio modules, queues, rates, rings
and topology, and only exposes /usr/sbin/call_qcsapi as a wrapper that invokes
the embedded qcsapi runtime loader explicitly.
"""
from __future__ import annotations

import json
import lzma
import shutil
import stat
import subprocess
import sys
import time
import zlib
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f72-5g-qcsapi-exec-loader"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

QCSAPI_RUNTIME = "/usr/libexec/openmitrastar/qcsapi-runtime"
CALL_QCSAPI_WRAPPER = b"""#!/bin/ash
runtime=/usr/libexec/openmitrastar/qcsapi-runtime
exec "$runtime/lib/ld-uClibc-0.9.29.so" --library-path "$runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}" "$runtime/bin/call_qcsapi" "$@"
"""


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    names = {entry.name for entry in entries}
    required = {
        f"{QCSAPI_RUNTIME.strip('/')}/bin/call_qcsapi",
        f"{QCSAPI_RUNTIME.strip('/')}/lib/ld-uClibc-0.9.29.so",
        f"{QCSAPI_RUNTIME.strip('/')}/lib/libqcsapi.so.1.0.1",
        f"{QCSAPI_RUNTIME.strip('/')}/manifest.sha256",
    }
    missing = sorted(required - names)
    if missing:
        raise SystemExit(f"F70 qcsapi runtime missing expected entries: {missing}")
    for forbidden in ("lib/ld-uClibc.so.0", "usr/sbin/call_qcsapi"):
        if forbidden in names:
            raise SystemExit(f"F70 already contains patch target: {forbidden}")

    trailer = entries.pop()
    if trailer.name != "TRAILER!!!":
        raise SystemExit("internal cpio parser lost trailer")

    max_ino = max(entry.ino for entry in entries)
    mtime = int(time.mktime((2026, 8, 26, 0, 0, 0, 0, 0, 0)))
    addition = f71.CpioEntry(
        name="usr/sbin/call_qcsapi",
        mode=stat.S_IFREG | 0o755,
        data=CALL_QCSAPI_WRAPPER,
        ino=max_ino + 1,
        nlink=1,
        mtime=mtime,
    )
    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in [*entries, addition, trailer])
    patched = raw[:start] + patched_cpio + remainder
    return patched, {
        "cpio_start": start,
        "old_raw_bytes": len(raw),
        "new_raw_bytes": len(patched),
        "delta_bytes": len(patched) - len(raw),
        "added": [
            {
                "path": addition.name,
                "mode": f"0{addition.mode:o}",
                "bytes": len(addition.data),
                "sha256": f71.sha256(addition.data),
            }
        ],
        "explicit_loader": f"{QCSAPI_RUNTIME}/lib/ld-uClibc-0.9.29.so",
        "global_interpreter_symlink": False,
        "preserved_remainder_bytes": len(remainder),
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

    raw, patch_report = patch_cpio(source_raw.read_bytes())
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
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f72-qcsapi-exec-loader/v1",
        "classification": "F72_FIXED_SIZE_FROM_F70_QCSAPI_EXEC_LOADER_WRAPPER_ONLY",
        "source": {
            "build_dir": str(f71.SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": json.loads(source_manifest.read_text(encoding="utf-8"))["artifacts"]["webformat"]["sha256"],
        },
        "change_scope": {
            "qcsapi_runtime": "adds only /usr/sbin/call_qcsapi explicit-loader wrapper",
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
    with (OUT / "SHA256SUMS").open("w", encoding="ascii", newline="\n") as fh:
        for path in sorted([*artifacts.values(), contract_path, manifest_path], key=lambda item: item.name):
            fh.write(f"{f71.sha256(path.read_bytes())}  {path.name}\n")

    tftp_copy = ROOT / "work/tftp/omvl" / web_path.name
    tftp_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(web_path, tftp_copy)
    full_slot = web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f72-qcsapi-exec-loader-build/v1",
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
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
