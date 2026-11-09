#!/usr/bin/env python3
"""Package F97 by rebuilding only the kernel around the proven F96 initramfs."""
from __future__ import annotations

import json
import lzma
import shutil
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f97-emac-periodic-rxrestart-from-f96"
LANE = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}"
OUT = LANE / "build"
BASE = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"

F96_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f96-2g-mcs7-sshkey-fix-from-f84/build"
F96_BASE = "openmitrastar-linux510-q3-persistent-f96-2g-mcs7-sshkey-fix-from-f84-LZMA-OFFLINE-NO-FLASH"
INITRAMFS = OUT / "f96-proven-initramfs.cpio"
EMAC_DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
EMAC_HEADER = ROOT / "work/kernel-port/linux-5.10/include/linux/soc/qtn/topaz-ethernet.h"


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    uncompressed = OUT / f"{BASE}.uncompressed.uImage"
    raw_path = OUT / f"{BASE}.decompressed.bin"
    lzma_path = OUT / f"{BASE}.lzma"
    uimage_path = OUT / f"{BASE}.uImage"
    web_path = OUT / f"{BASE}.webformat.bin"
    config_path = OUT / f"{BASE}.config"
    dtb_path = OUT / f"{BASE}.dtb"
    vmlinux_path = OUT / f"{BASE}.vmlinux"

    f96_manifest = F96_BUILD / "manifest.json"
    f96_result = F96_BUILD / "build-result.json"
    required = [
        uncompressed, config_path, dtb_path, vmlinux_path, INITRAMFS,
        f96_manifest, f96_result, EMAC_DRIVER, EMAC_HEADER,
        f71.TEMPLATE, f71.BOOTBASE, f71.LEGACY_LZMA,
    ]
    for path in required:
        if not path.is_file():
            raise SystemExit(f"missing F97 input: {path}")

    source = uncompressed.read_bytes()
    if len(source) <= 64:
        raise SystemExit("F97 uncompressed uImage is too small")
    raw = source[64:]
    raw_path.write_bytes(raw)

    cpio_start, _entries, remainder = f71.parse_first_cpio(raw)
    cpio_end = len(raw) - len(remainder)
    embedded_cpio = raw[cpio_start:cpio_end]
    if f71.sha256(embedded_cpio) != f71.sha256(INITRAMFS.read_bytes()):
        raise SystemExit("F97 rebuilt kernel does not embed the proven F96 initramfs")

    encoded = f71.encode_lzma_legacy(raw_path)
    if lzma.decompress(encoded, format=lzma.FORMAT_ALONE) != raw:
        raise SystemExit("F97 LZMA round-trip failed")
    lzma_path.write_bytes(encoded)
    f71.write_uimage(uncompressed, encoded, uimage_path, compression=3)
    f71.write_webformat(uimage_path, web_path)
    if web_path.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F97 webformat exceeds linux_live slot")

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
        "uncompressed_uimage": uncompressed,
        "lzma": lzma_path,
        "uimage": uimage_path,
        "webformat": web_path,
        "kconfig": config_path,
        "dtb": dtb_path,
        "vmlinux": vmlinux_path,
        "initramfs": INITRAMFS,
    }
    f96_manifest_json = json.loads(f96_manifest.read_text(encoding="utf-8"))
    f96_result_json = json.loads(f96_result.read_text(encoding="utf-8"))
    manifest = {
        "schema": "openmitrastar.q3-persistent-composite-f97-emac-periodic-rxrestart-from-f96/v1",
        "classification": "F97_REKERNEL_FROM_F96_EMAC_PERIODIC_RX_RESTART",
        "source": {
            "f96_build_dir": str(F96_BUILD.relative_to(ROOT)),
            "f96_manifest_sha256": f71.sha256(f96_manifest.read_bytes()),
            "f96_webformat_sha256": f96_result_json["candidate_sha256"],
            "f96_raw_sha256": f96_manifest_json["artifacts"]["decompressed_payload"]["sha256"],
            "f96_initramfs_sha256": f71.sha256(INITRAMFS.read_bytes()),
        },
        "change_scope": {
            "kernel": "rebuilt from F96 initramfs with qtn-topaz-emac RX restart liveness fix",
            "emac": "RX DMA restart is cooldown-based and no longer limited to two lifetime restarts",
            "rootfs_initramfs": "byte-identical F96 initramfs embedded in the rebuilt kernel",
            "ssh": "unchanged from F96 factory root authorized_keys",
            "radio2g_loader": "unchanged from F96 MCS7 no-guard no-split profile",
            "radio2g_modules": "unchanged from F96",
            "radio5_manual_script": "unchanged from F96/F84 post-hostapd stage stop",
            "radio5_modules": "unchanged from F96",
            "qdrv": "unchanged from F96",
            "queues_dma_rates_rings": "unchanged outside EMAC RX watchdog recovery",
        },
        "emac_patch": {
            "driver": {
                "file": str(EMAC_DRIVER.relative_to(ROOT)),
                "sha256": f71.sha256(EMAC_DRIVER.read_bytes()),
            },
            "header": {
                "file": str(EMAC_HEADER.relative_to(ROOT)),
                "sha256": f71.sha256(EMAC_HEADER.read_bytes()),
            },
            "markers": [
                "QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS",
                "OMEMAC rx restart reason=stalled-cur-rx",
                "rx_restart_throttled",
            ],
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
                "source": "rebuilt F97 kernel payload with F96 embedded CPIO",
            },
            "initramfs": {
                "file": INITRAMFS.name,
                "bytes": INITRAMFS.stat().st_size,
                "sha256": f71.sha256(INITRAMFS.read_bytes()),
                "source": "F96 embedded CPIO",
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
        "schema": "openmitrastar.f97-emac-periodic-rxrestart-from-f96-build/v1",
        "status": "PASS",
        "candidate": str(web_path),
        "candidate_sha256": f71.sha256(web_path.read_bytes()),
        "candidate_bytes": web_path.stat().st_size,
        "candidate_crc32": f71.crc32(web_path.read_bytes()),
        "full_slot_sha256": f71.sha256(full_slot),
        "full_slot_crc32": f71.crc32(full_slot),
        "build_dir": str(OUT),
        "tftp_copy": str(tftp_copy),
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
