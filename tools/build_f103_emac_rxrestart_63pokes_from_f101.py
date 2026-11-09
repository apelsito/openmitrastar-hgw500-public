#!/usr/bin/env python3
"""Build F103 from F101 by throttling EMAC poll fallback RX restarts.

F102 proved that removing ``qtn,irq-poll-fallback`` is not a safe operational
baseline: the router can boot once, but loses the management datapath after
stress.  F103 keeps the fallback worker enabled and changes only the ARC branch
immediate that gates the destructive RX DMA restart:

    same_cur_rx_pokes >= 8  ->  same_cur_rx_pokes >= 63

That changes the restart trigger from roughly 2 s to roughly 15.75 s at the
existing 250 ms poke cadence.  It leaves CPIO, DTB, modules, rates, bridge,
queues and flash layout unchanged.
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
BUILD_TAG = "f103-emac-rxrestart-63pokes-from-f101"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

SRC_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f101-2g-hwcrypto-from-f100/build"
SRC_BASE = "openmitrastar-linux510-q3-persistent-f101-2g-hwcrypto-from-f100-LZMA-OFFLINE-NO-FLASH"

# qtn_emac_irq_poll_work+0x394:
#   ld.as r0,[r13,170]
#   brhs  r0,0x8,+16
#   mov   r19,0
#   mov   r18,0
#   b     rearm_poll
OLD_CONTEXT = bytes.fromhex(
    "aa 15 00 16"
    "11 08 15 02"
    "4a 23 00 20"
    "4a 22 00 20"
    "93 01 00 00"
)
NEW_CONTEXT = bytes.fromhex(
    "aa 15 00 16"
    "11 08 d5 0f"
    "4a 23 00 20"
    "4a 22 00 20"
    "93 01 00 00"
)


def patch_one(blob: bytes, label: str) -> tuple[bytes, dict[str, object]]:
    count = blob.count(OLD_CONTEXT)
    if count != 1:
        raise SystemExit(f"{label}: expected one F101 rxrestart branch context, found {count}")
    offset = blob.find(OLD_CONTEXT)
    patched = blob[:offset] + NEW_CONTEXT + blob[offset + len(OLD_CONTEXT) :]
    if len(patched) != len(blob):
        raise SystemExit(f"{label}: patch changed size")
    if OLD_CONTEXT in patched:
        raise SystemExit(f"{label}: old rxrestart branch context still present")
    return patched, {
        "label": label,
        "offset": offset,
        "old_context_hex": OLD_CONTEXT.hex(),
        "new_context_hex": NEW_CONTEXT.hex(),
        "old_branch": "brhs r0,0x8,+16",
        "new_branch": "brhs r0,0x3f,+16",
        "old_same_cur_rx_pokes": 8,
        "new_same_cur_rx_pokes": 63,
        "old_approx_trigger_ms": 8 * 250,
        "new_approx_trigger_ms": 63 * 250,
        "old_sha256": f71.sha256(blob),
        "new_sha256": f71.sha256(patched),
        "bytes": len(blob),
        "delta_bytes": 0,
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
        f71.TEMPLATE,
        f71.BOOTBASE,
        f71.LEGACY_LZMA,
    ):
        if not required.is_file():
            raise SystemExit(f"missing input: {required}")

    source_raw_bytes = source_raw.read_bytes()
    cpio_start, _source_entries, source_remainder = f71.parse_first_cpio(source_raw_bytes)
    cpio_end = len(source_raw_bytes) - len(source_remainder)
    raw, raw_patch = patch_one(source_raw_bytes, "decompressed-payload")
    if raw[:cpio_end] != source_raw_bytes[:cpio_end]:
        raise SystemExit("F103 patch changed initramfs CPIO bytes")

    vmlinux, vmlinux_patch = patch_one(source_vmlinux.read_bytes(), "vmlinux")
    raw_path = OUT / f"{BASE_OUT}.decompressed.bin"
    uncompressed_path = OUT / f"{BASE_OUT}.uncompressed.uImage"
    lzma_path = OUT / f"{BASE_OUT}.lzma"
    uimage_path = OUT / f"{BASE_OUT}.uImage"
    web_path = OUT / f"{BASE_OUT}.webformat.bin"
    config_path = OUT / f"{BASE_OUT}.config"
    dtb_path = OUT / f"{BASE_OUT}.dtb"
    vmlinux_path = OUT / f"{BASE_OUT}.vmlinux"

    raw_path.write_bytes(raw)
    vmlinux_path.write_bytes(vmlinux)
    shutil.copy2(source_config, config_path)
    shutil.copy2(source_dtb, dtb_path)
    f71.write_uimage(source_uncompressed, raw, uncompressed_path, compression=0)
    encoded = f71.encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
        raise SystemExit("F103 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed_path, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F103 webformat exceeds linux_live slot")

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
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f103-emac-rxrestart-63pokes-from-f101/v1",
        "classification": "F103_FROM_F101_EMAC_BINARY_RXRESTART_THRESHOLD_63POKES_FIXEDSIZE",
        "source": {
            "build_dir": str(SRC_BUILD.relative_to(ROOT)),
            "manifest_sha256": f71.sha256(source_manifest.read_bytes()),
            "webformat_sha256": source_manifest_json["artifacts"]["webformat"]["sha256"],
            "raw_sha256": f71.sha256(source_raw_bytes),
            "candidate_sha256": source_result_json["candidate_sha256"],
            "full_slot_crc32": source_result_json["full_slot_crc32"],
        },
        "change_scope": {
            "kernel_emac": "binary fixed-size branch immediate patch in qtn_emac_irq_poll_work: rx restart threshold 8->63 same-cur-rx pokes",
            "emac_poll_fallback": "unchanged from F101: still enabled by qtn,irq-poll-fallback",
            "initramfs_cpio": "unchanged byte-for-byte",
            "dtb": "unchanged from F101",
            "radio2g_modules": "unchanged from F101",
            "radio2g_loader_rates_crypto": "unchanged from F101",
            "radio5_modules": "unchanged from F101",
            "qdrv": "unchanged from F101",
            "queues_dma_rings_bridge": "unchanged from F101",
            "flash_layout": "unchanged",
        },
        "patch": {
            "raw": raw_patch,
            "vmlinux": vmlinux_patch,
            "cpio": {
                "start": cpio_start,
                "end": cpio_end,
                "sha256_before": f71.sha256(source_raw_bytes[:cpio_end]),
                "sha256_after": f71.sha256(raw[:cpio_end]),
                "unchanged": raw[:cpio_end] == source_raw_bytes[:cpio_end],
            },
        },
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
        "security": {"touches_router": False, "opens_uart": False, "flash": False},
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

    full_slot = web_path.read_bytes() + b"\xff" * (f71.SLOT_BYTES - web_path.stat().st_size)
    result = {
        "schema": "openmitrastar.f103-emac-rxrestart-63pokes-from-f101-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": f71.sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": f71.sha256(full_slot),
        "full_slot_crc32": f71.crc32(full_slot),
        "build_dir": str(OUT),
        "tftp_copy": str(tftp_copy),
        "patch": manifest["patch"],
        "bootbase_result": contract_json.get("result"),
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
