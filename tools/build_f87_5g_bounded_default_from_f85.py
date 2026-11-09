#!/usr/bin/env python3
"""Build F87 from F85 with bounded 5 GHz as the default manual start.

F86 proved that leaving the 5 GHz AP running at the post-hostapd point can
hardlock management shortly after a successful ready marker.  F87 keeps the
known-stable F85 behavior but prevents accidental unbounded full starts:
`/usr/sbin/om-radio5-start` defaults to `OM_RADIO5_STAGE_STOP=post-hostapd`.

The full experimental tail remains available only with:
  OM_RADIO5_UNBOUNDED_START=1 /usr/sbin/om-radio5-start
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
BUILD_TAG = "f87-5g-bounded-default-after-f86"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f85-5g-cal-mac-prep-after-f84/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f85-5g-cal-mac-prep-after-f84-LZMA-OFFLINE-NO-FLASH"
PATCH_ENTRY = "usr/sbin/om-radio5-start"

OLD = "stage_stop=${OM_RADIO5_STAGE_STOP:-}\n"
NEW = """stage_stop=${OM_RADIO5_STAGE_STOP:-}
if [ -z "$stage_stop" ] && [ "${OM_RADIO5_UNBOUNDED_START:-0}" != 1 ]; then
\tstage_stop=post-hostapd
\tlog 'OMRADIO5_BOUNDED_DEFAULT stage=post-hostapd reason=f86-safe-ready-persistent-hardlock'
fi
"""


def strip_comments(text: str) -> str:
    kept: list[str] = []
    for line in text.splitlines(keepends=True):
        stripped = line.lstrip()
        if stripped.startswith("#") and not line.startswith("#!"):
            continue
        kept.append(line)
    return "".join(kept)


def patch_start_script(data: bytes) -> tuple[bytes, dict[str, object]]:
    text = data.decode("ascii")
    if OLD not in text:
        raise SystemExit("F87 om-radio5-start missing stage_stop assignment")
    patched = text.replace(OLD, NEW, 1)
    patched_bytes = patched.encode("ascii")
    if len(patched_bytes) > len(data):
        patched_bytes = strip_comments(patched).encode("ascii")
    if len(patched_bytes) > len(data):
        raise SystemExit(f"F87 patch grew om-radio5-start by {len(patched_bytes) - len(data)} bytes")
    padding = len(data) - len(patched_bytes)
    if padding:
        patched_bytes += (b"\n# f87 fixed-size padding " + b"#" * padding)[:padding]
    if len(patched_bytes) != len(data):
        raise SystemExit("F87 fixed-size padding failed")
    return patched_bytes, {
        "entry": PATCH_ENTRY,
        "old_bytes": len(data),
        "new_bytes": len(patched_bytes),
        "delta_bytes": 0,
        "padding_bytes": padding,
        "old_sha256": f71.sha256(data),
        "new_sha256": f71.sha256(patched_bytes),
        "fix": "default manual 5 GHz start is bounded to post-hostapd stop; unbounded full path requires OM_RADIO5_UNBOUNDED_START=1",
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
        patched_data, patch_report = patch_start_script(entry.data)
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
        raise SystemExit("F87 patch changed decompressed payload size")
    if new_start != start or new_cpio_end != old_cpio_end:
        raise SystemExit("F87 patch changed CPIO placement")
    if new_remainder != remainder:
        raise SystemExit("F87 patch changed post-CPIO remainder")
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
        "schema": "openmitrastar.q3-persistent-composite-f87-5g-bounded-default-after-f86/v1",
        "classification": "F87_FIXED_OFFSET_FROM_F85_5G_BOUNDED_DEFAULT",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
        },
        "change_scope": {
            "radio2g": "unchanged from F85",
            "radio5g_default": "manual start defaults to bounded post-hostapd stop",
            "radio5g_unbounded": "still available only with OM_RADIO5_UNBOUNDED_START=1",
            "qdrv": "unchanged from F85",
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
        "schema": "openmitrastar.f87-5g-bounded-default-after-f86-build/v1",
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
