#!/usr/bin/env python3
"""Prepare a standalone metadata directory for restoring the F66 qguard image.

This is offline-only. It does not open UART, SSH to the router, start TFTP, or
write flash. The output is consumed by the existing Bootbase mtd4 writer through
OM_Q3_FLASH_* environment overrides.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f65/build"
ORIG_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f66-2g-queue-guard/build"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f66-2g-qguard16r-restore/build"
BASE_IN = "openmitrastar-linux510-q3-persistent-f65-isolated-5g-LZMA-OFFLINE-NO-FLASH"
BASE = "openmitrastar-linux510-q3-persistent-f66-2g-qguard16r-LZMA-OFFLINE-NO-FLASH"
OLD_LOADER = ROOT / "work/mission-state/w4-rootfs-product/rootfs/usr/sbin/om-radio-modules"
BOOTBASE = ROOT / "tools/bootbase_contract_emulator.py"
PARTS_DIR = ROOT / "hgw500bna-qcv2-firmware-dump-verified"
TFTP_COPY = ROOT / "work/tftp/omvl" / f"{BASE}.webformat.bin"
SLOT_BYTES = 7_995_392


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_path(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def crc32_bytes(data: bytes) -> str:
    return f"{zlib.crc32(data) & 0xFFFFFFFF:08x}"


def copy_artifact(suffix: str) -> Path:
    src = ORIG_BUILD / f"{BASE}.{suffix}"
    if not src.is_file():
        raise SystemExit(f"missing restore artifact: {src}")
    dst = OUT / src.name
    shutil.copy2(src, dst)
    return dst


def extract_compact_loader(raw_path: Path) -> bytes:
    source_raw = SRC_BUILD / f"{BASE_IN}.decompressed.bin"
    if not source_raw.is_file():
        raise SystemExit(f"missing F65 raw source: {source_raw}")
    old = OLD_LOADER.read_bytes()
    source = source_raw.read_bytes()
    count = source.count(old)
    if count != 1:
        raise SystemExit(f"expected one old loader occurrence in F65, found {count}")
    offset = source.index(old)
    span = raw_path.read_bytes()[offset : offset + len(old)]
    compact = span.split(b"\0", 1)[0]
    if not compact.startswith((b"#!/bin/sh", b"#!/bin/ash")) or b"profile=qguard16r" not in compact:
        raise SystemExit("extracted qguard loader does not look valid")
    return compact


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    files = {
        "decompressed_payload": copy_artifact("decompressed.bin"),
        "uncompressed_uimage": copy_artifact("uncompressed.uImage"),
        "lzma": copy_artifact("lzma"),
        "uimage": copy_artifact("uImage"),
        "webformat": copy_artifact("webformat.bin"),
        "kconfig": copy_artifact("config"),
    }
    web = files["webformat"]
    compact_loader = extract_compact_loader(files["decompressed_payload"])
    loader_path = OUT / "om-radio-modules.fixedsize"
    loader_path.write_bytes(compact_loader)

    contract = subprocess.run(
        [
            sys.executable,
            str(BOOTBASE),
            "--candidate-slot",
            str(web),
            "--candidate-name",
            "linux_live-f66-qguard16r-restore",
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

    old_size = OLD_LOADER.stat().st_size
    report = {
        "schema": "openmitrastar.f66-qguard16r-restore-metadata/v1",
        "source": "existing-d9da-f66-artifacts",
        "changed_file": "usr/sbin/om-radio-modules",
        "old_loader_size": old_size,
        "compact_loader_size": len(compact_loader),
        "padding_bytes": old_size - len(compact_loader),
        "loader_sha256": sha256_bytes(compact_loader),
        "initramfs_sha256": sha256_path(files["decompressed_payload"]),
        "webformat_sha256": sha256_path(web),
        "webformat_crc32": crc32_bytes(web.read_bytes()),
        "bootbase_contract": contract_json.get("result"),
        "candidate_accepted": contract_json.get("candidate", {}).get("accepted_by_contract"),
        "markers": {
            "queue_guard": b"hgw500_tx_queue_guard=1" in compact_loader,
            "queue_guard_high_16": b"hgw500_tx_queue_guard_high=16" in compact_loader,
            "queue_guard_low_8": b"hgw500_tx_queue_guard_low=8" in compact_loader,
            "reclaim_poll": b"hgw500_tx_reclaim_poll=1" in compact_loader,
            "mcs7": b"hgw500_force_data_mcs7=1" in compact_loader,
            "autorate": b"hgw500_force_data_mcs7=0" in compact_loader,
            "be_data_split": b"hgw500_txbd_be_data_split=1" in compact_loader,
        },
        "hardware_actions": False,
        "flash_supported": False,
    }
    report_path = OUT / "f66-qguard16r-restore-report.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")

    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f66/v1",
        "classification": "F66_FIXED_SIZE_FROM_F65_2G_QUEUE_GUARD_RESTORE",
        "source": "q3-persistent-composite-f66-2g-queue-guard",
        "artifacts": {
            key: {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_path(path),
                **({"crc32": crc32_bytes(path.read_bytes())} if key == "webformat" else {}),
            }
            for key, path in files.items()
        },
        "slot": {
            "name": "linux_live",
            "bytes": SLOT_BYTES,
            "candidate_bytes": web.stat().st_size,
            "fits": web.stat().st_size <= SLOT_BYTES,
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
        for path in sorted([*files.values(), loader_path, contract_path, report_path, manifest_path], key=lambda item: item.name):
            fh.write(f"{sha256_path(path)}  {path.name}\n")

    TFTP_COPY.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(web, TFTP_COPY)
    result = {
        "schema": "openmitrastar.f66-qguard16r-restore-prepare/v1",
        "status": "PASS",
        "build_dir": str(OUT),
        "candidate": str(web),
        "candidate_sha256": sha256_path(web),
        "candidate_bytes": web.stat().st_size,
        "candidate_crc32": crc32_bytes(web.read_bytes()),
        "tftp_copy": str(TFTP_COPY),
        "full_slot_crc32": crc32_bytes(web.read_bytes() + b"\xff" * (SLOT_BYTES - web.stat().st_size)),
        "full_slot_sha256": sha256_bytes(web.read_bytes() + b"\xff" * (SLOT_BYTES - web.stat().st_size)),
        "markers": report["markers"],
        "flash": False,
        "router_mutations": False,
    }
    result_path = OUT / "restore-prepare-result.json"
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
