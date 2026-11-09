#!/usr/bin/env python3
"""Build F71 from F70 by adding the missing global qcsapi ELF interpreter.

F70 already embeds the OSABI-v4 OEM qcsapi runtime under
/usr/libexec/openmitrastar/qcsapi-runtime, but the binaries still request
/lib/ld-uClibc.so.0 as PT_INTERP.  Linux therefore cannot execute them through
the normal path, and invoking the loader by hand is not equivalent enough for
this userspace.  F71 keeps the F70 kernel, modules, qdrv, rates, rings, queues
and 2.4 GHz scripts unchanged, and adds only:

* /lib/ld-uClibc.so.0 -> /usr/libexec/.../ld-uClibc-0.9.29.so
* /usr/sbin/call_qcsapi wrapper with LD_LIBRARY_PATH pointed at the embedded
  runtime.
"""
from __future__ import annotations

import hashlib
import json
import lzma
import shutil
import stat
import struct
import subprocess
import sys
import time
import zlib
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f70-2g-mcs15-qguard64r-nosplit/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f70-2g-mcs15-qguard64r-nosplit-LZMA-OFFLINE-NO-FLASH"
BUILD_TAG = "f71-5g-qcsapi-interp"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
TEMPLATE = ROOT / "Firmware_para_HGW-500BNA-QCv2_ES_s00.00_g001_100WNU0b24_mitrastar_webformat.bin"
BOOTBASE = ROOT / "tools/bootbase_contract_emulator.py"
LEGACY_LZMA = ROOT / "work/volatile-loader/build/Quantenna-GPL/host/utilities/lzma"
PARTS_DIR = ROOT / "hgw500bna-qcv2-firmware-dump-verified"
SLOT_BYTES = 7_995_392
UIMAGE_MAGIC = 0x27051956
UIMAGE_HEADER = 64
RAS_OFFSET = 0x2000
CPIO_MAGIC = b"070701"

QCSAPI_RUNTIME = "/usr/libexec/openmitrastar/qcsapi-runtime"
INTERP_TARGET = f"{QCSAPI_RUNTIME}/lib/ld-uClibc-0.9.29.so"
CALL_QCSAPI_WRAPPER = b"""#!/bin/ash
runtime=/usr/libexec/openmitrastar/qcsapi-runtime
export LD_LIBRARY_PATH="$runtime/lib${LD_LIBRARY_PATH:+:$LD_LIBRARY_PATH}"
exec "$runtime/bin/call_qcsapi" "$@"
"""


@dataclass
class CpioEntry:
    name: str
    mode: int
    data: bytes
    ino: int = 0
    uid: int = 0
    gid: int = 0
    nlink: int = 1
    mtime: int = 0
    devmajor: int = 0
    devminor: int = 0
    rdevmajor: int = 0
    rdevminor: int = 0


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def crc32(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def align4(value: int) -> int:
    return (value + 3) & ~3


def parse_uimage_header(blob: bytes) -> list[int | bytes]:
    values = list(struct.unpack(">7I4B32s", blob[:UIMAGE_HEADER]))
    if values[0] != UIMAGE_MAGIC:
        raise SystemExit("bad uImage magic")
    header = bytearray(blob[:UIMAGE_HEADER])
    header[4:8] = b"\0\0\0\0"
    if zlib.crc32(header) & 0xFFFFFFFF != values[1]:
        raise SystemExit("uImage header CRC mismatch")
    return values


def write_uimage(source_uimage: Path, raw: bytes, out: Path, compression: int) -> None:
    values = parse_uimage_header(source_uimage.read_bytes())
    values[1] = 0
    values[3] = len(raw)
    values[6] = zlib.crc32(raw) & 0xFFFFFFFF
    values[10] = compression
    header = bytearray(struct.pack(">7I4B32s", *values))
    values[1] = zlib.crc32(header) & 0xFFFFFFFF
    out.write_bytes(struct.pack(">7I4B32s", *values) + raw)


def write_webformat(uimage: Path, out: Path) -> None:
    source = uimage.read_bytes()
    values = parse_uimage_header(source)
    payload = source[UIMAGE_HEADER:]
    image = bytearray(TEMPLATE.read_bytes()[:RAS_OFFSET])
    image.extend(payload)
    values[1] = 0
    values[3] = len(payload)
    values[6] = zlib.crc32(payload) & 0xFFFFFFFF
    values[8] = 0x13
    header = bytearray(struct.pack(">7I4B32s", *values))
    values[1] = zlib.crc32(header) & 0xFFFFFFFF
    image[:UIMAGE_HEADER] = struct.pack(">7I4B32s", *values)
    out.write_bytes(image)


def wsl_path(path: Path) -> str:
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    rest = resolved.as_posix()[3:]
    return f"/mnt/{drive}/{rest}"


def encode_lzma_legacy(raw_path: Path) -> bytes:
    proc = subprocess.run(
        [
            "wsl",
            "-d",
            "podman-openmitrastar-analysis",
            "--",
            wsl_path(LEGACY_LZMA),
            "--keep",
            "--best",
            wsl_path(raw_path),
            "-c",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if proc.returncode != 0:
        raise SystemExit(proc.stderr.decode("utf-8", errors="replace") or "legacy lzma failed")
    return proc.stdout


def parse_first_cpio(raw: bytes) -> tuple[int, list[CpioEntry], bytes]:
    start = raw.find(CPIO_MAGIC)
    if start < 0:
        raise SystemExit("initramfs cpio magic not found")
    entries: list[CpioEntry] = []
    offset = start
    while offset + 110 <= len(raw) and raw[offset : offset + 6] == CPIO_MAGIC:
        fields = [int(raw[offset + 6 + i * 8 : offset + 14 + i * 8], 16) for i in range(13)]
        (
            ino,
            mode,
            uid,
            gid,
            nlink,
            mtime,
            filesize,
            devmajor,
            devminor,
            rdevmajor,
            rdevminor,
            namesize,
            _check,
        ) = fields
        name_start = offset + 110
        name_end = name_start + namesize
        name = raw[name_start : name_end - 1].decode("utf-8")
        data_start = align4(name_end)
        data_end = data_start + filesize
        next_offset = align4(data_end)
        entries.append(
            CpioEntry(
                name=name,
                mode=mode,
                data=raw[data_start:data_end],
                ino=ino,
                uid=uid,
                gid=gid,
                nlink=nlink,
                mtime=mtime,
                devmajor=devmajor,
                devminor=devminor,
                rdevmajor=rdevmajor,
                rdevminor=rdevminor,
            )
        )
        offset = next_offset
        if name == "TRAILER!!!":
            return start, entries, raw[offset:]
    raise SystemExit("cpio trailer not found")


def serialize_entry(entry: CpioEntry) -> bytes:
    name = entry.name.encode("utf-8") + b"\0"
    data = entry.data
    check = 0
    header = CPIO_MAGIC + (
        f"{entry.ino:08x}{entry.mode:08x}{entry.uid:08x}{entry.gid:08x}"
        + f"{entry.nlink:08x}{entry.mtime:08x}{len(data):08x}"
        + f"{entry.devmajor:08x}{entry.devminor:08x}{entry.rdevmajor:08x}"
        + f"{entry.rdevminor:08x}{len(name):08x}{check:08x}"
    ).encode("ascii")
    out = bytearray(header)
    out.extend(name)
    out.extend(b"\0" * (align4(len(out)) - len(out)))
    out.extend(data)
    out.extend(b"\0" * (align4(len(out)) - len(out)))
    return bytes(out)


def patch_cpio(raw: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = parse_first_cpio(raw)
    names = {entry.name for entry in entries}
    required = {
        f"usr/libexec/openmitrastar/qcsapi-runtime/bin/call_qcsapi",
        f"usr/libexec/openmitrastar/qcsapi-runtime/lib/ld-uClibc-0.9.29.so",
        f"usr/libexec/openmitrastar/qcsapi-runtime/lib/libqcsapi.so.1.0.1",
        f"usr/libexec/openmitrastar/qcsapi-runtime/manifest.sha256",
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
    additions = [
        CpioEntry(
            name="lib/ld-uClibc.so.0",
            mode=stat.S_IFLNK | 0o777,
            data=INTERP_TARGET.encode("ascii"),
            ino=max_ino + 1,
            nlink=1,
            mtime=mtime,
        ),
        CpioEntry(
            name="usr/sbin/call_qcsapi",
            mode=stat.S_IFREG | 0o755,
            data=CALL_QCSAPI_WRAPPER,
            ino=max_ino + 2,
            nlink=1,
            mtime=mtime,
        ),
    ]
    patched_cpio = b"".join(serialize_entry(entry) for entry in [*entries, *additions, trailer])
    patched = raw[:start] + patched_cpio + remainder
    return patched, {
        "cpio_start": start,
        "old_raw_bytes": len(raw),
        "new_raw_bytes": len(patched),
        "delta_bytes": len(patched) - len(raw),
        "added": [
            {"path": item.name, "mode": f"0{item.mode:o}", "bytes": len(item.data), "sha256": sha256(item.data)}
            for item in additions
        ],
        "preserved_remainder_bytes": len(remainder),
    }


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_raw = SRC_BUILD / f"{SRC_BASE}.decompressed.bin"
    source_uncompressed = SRC_BUILD / f"{SRC_BASE}.uncompressed.uImage"
    source_config = SRC_BUILD / f"{SRC_BASE}.config"
    source_manifest = SRC_BUILD / "manifest.json"
    for required in (source_raw, source_uncompressed, source_config, source_manifest, TEMPLATE, BOOTBASE, LEGACY_LZMA):
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
    write_uimage(source_uncompressed, raw, uncompressed_path, compression=0)

    encoded = encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
        raise SystemExit("LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > SLOT_BYTES:
        raise SystemExit("webformat exceeds linux_live slot")

    contract = subprocess.run(
        [
            sys.executable,
            str(BOOTBASE),
            "--candidate-slot",
            str(web_path),
            "--candidate-name",
            f"linux_live-{BUILD_TAG}",
            "--parts-dir",
            str(PARTS_DIR),
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
        "schema": "openmitrastar.q3-persistent-composite-f71-qcsapi-interp/v1",
        "classification": "F71_FIXED_SIZE_FROM_F70_QCSAPI_INTERP_WRAPPER_ONLY",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": sha256(source_manifest.read_bytes()),
            "webformat_sha256": json.loads(source_manifest.read_text(encoding="utf-8"))["artifacts"]["webformat"]["sha256"],
        },
        "change_scope": {
            "qcsapi_runtime": "adds global ELF interpreter symlink and call_qcsapi wrapper",
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
                "sha256": sha256(path.read_bytes()),
                **({"crc32": crc32(path.read_bytes())} if key == "webformat" else {}),
            }
            for key, path in artifacts.items()
        },
        "slot": {"name": "linux_live", "bytes": SLOT_BYTES, "candidate_bytes": web_path.stat().st_size, "fits": True},
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
            fh.write(f"{sha256(path.read_bytes())}  {path.name}\n")

    tftp_copy = ROOT / "work/tftp/omvl" / web_path.name
    tftp_copy.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(web_path, tftp_copy)
    full_slot = web_path.read_bytes() + b"\xff" * (SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f71-qcsapi-interp-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": crc32(web_path.read_bytes()),
        "full_slot_sha256": sha256(full_slot),
        "full_slot_crc32": crc32(full_slot),
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
