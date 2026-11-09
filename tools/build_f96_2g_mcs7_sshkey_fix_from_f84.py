#!/usr/bin/env python3
"""Build F96 from F84 by restoring the current root SSH factory key.

F84 is the last 2.4 GHz MCS7 branch with L3 traffic evidence. Later F9x
variants proved higher PHY but broke data-plane traffic, and the F83/F84
branch skipped the F82 factory-key fix. F96 changes only the fixed-size
factory authorized_keys CPIO entry so clean boots keep SSH login usable.
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
BUILD_TAG = "f96-2g-mcs7-sshkey-fix-from-f84"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f84-2g-mcs7-param-fix-5g-post-hostapd-stage/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f84-2g-mcs7-param-fix-5g-post-hostapd-stage-LZMA-OFFLINE-NO-FLASH"
KEY_ENTRY = "usr/share/openmitrastar/keys/factory-authorized_keys"
LOCAL_PUBLIC_KEY = Path.home() / ".ssh/id_ed25519.pub"


def normalized_ed25519_key(path: Path) -> bytes:
    line = ""
    for candidate in path.read_text(encoding="ascii").splitlines():
        fields = candidate.strip().split()
        if len(fields) >= 2 and fields[0] == "ssh-ed25519":
            line = f"{fields[0]} {fields[1]}\n"
            break
    if not line:
        raise SystemExit(f"missing ssh-ed25519 public key: {path}")
    return line.encode("ascii")


def patch_cpio(raw: bytes, new_key: bytes) -> tuple[bytes, dict[str, object]]:
    start, entries, remainder = f71.parse_first_cpio(raw)
    old_cpio_end = len(raw) - len(remainder)
    patched_entries: list[f71.CpioEntry] = []
    patch_report = None
    for entry in entries:
        if entry.name != KEY_ENTRY:
            patched_entries.append(entry)
            continue
        if len(new_key) != len(entry.data):
            raise SystemExit(
                f"factory key size mismatch old={len(entry.data)} new={len(new_key)}; "
                "refuse to shift initramfs layout"
            )
        patched_entries.append(f71.CpioEntry(
            name=entry.name,
            mode=entry.mode,
            data=new_key,
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
        patch_report = {
            "entry": KEY_ENTRY,
            "old_bytes": len(entry.data),
            "new_bytes": len(new_key),
            "delta_bytes": 0,
            "old_sha256": f71.sha256(entry.data),
            "new_sha256": f71.sha256(new_key),
            "applied": ["factory-authorized-root-key"],
            "fix": "replace factory authorized_keys with current local root ed25519 public key",
        }
    if patch_report is None:
        raise SystemExit(f"missing CPIO entry: {KEY_ENTRY}")

    patched_cpio = b"".join(f71.serialize_entry(entry) for entry in patched_entries)
    result = raw[:start] + patched_cpio + remainder
    new_start, _new_entries, new_remainder = f71.parse_first_cpio(result)
    new_cpio_end = len(result) - len(new_remainder)
    if len(result) != len(raw):
        raise SystemExit("F96 patch changed decompressed payload size")
    if new_start != start or new_cpio_end != old_cpio_end:
        raise SystemExit("F96 patch changed CPIO placement")
    if new_remainder != remainder:
        raise SystemExit("F96 patch changed post-CPIO remainder")
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
        LOCAL_PUBLIC_KEY, f71.BOOTBASE, f71.LEGACY_LZMA,
    ):
        if not required.is_file():
            raise SystemExit(f"missing input: {required}")

    source_raw_bytes = source_raw.read_bytes()
    raw, patch_report = patch_cpio(source_raw_bytes, normalized_ed25519_key(LOCAL_PUBLIC_KEY))
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
        "rootfs": raw_path,
        "uncompressed_uimage": uncompressed_path,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "kconfig": config_path,
    }
    source_manifest_json = json.loads(source_manifest.read_text(encoding="utf-8"))
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f96-2g-mcs7-sshkey-fix-from-f84/v1",
        "classification": "F96_FIXED_OFFSET_FROM_F84_2G_MCS7_FACTORY_ROOT_KEY_FIX",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
        },
        "change_scope": {
            "ssh": "factory root authorized_keys updated to current local ed25519 public key",
            "radio2g_loader": "unchanged from F84 MCS7 profile",
            "radio2g_modules": "unchanged from F84",
            "radio5_manual_script": "unchanged from F84 post-hostapd stage stop",
            "radio5_modules": "unchanged from F84",
            "qdrv": "unchanged from F84",
            "bridge_topology": "unchanged from F84",
            "queues_dma_rates_rings": "unchanged from F84",
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
            },
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
        "schema": "openmitrastar.f96-2g-mcs7-sshkey-fix-from-f84-build/v1",
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
