#!/usr/bin/env python3
"""Compose the F164 kernel + SquashFS Bootbase webformat image."""
from __future__ import annotations

import hashlib
import json
import lzma
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71


ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "outputs/kernel-port/f164-squashfs-layout-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f164-squashfs-product/build"
BASE = "openmitrastar-linux510-q3-persistent-f164-squashfs-product-LZMA-OFFLINE-NO-FLASH"
ROOTFS_OFFSET = 0x180000
ROOTFS_WINDOW = f71.SLOT_BYTES - ROOTFS_OFFSET
SOURCE_DATE_EPOCH = 1785024000


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    source_uimage = ASSETS / "kernel-squashfs.uncompressed.uImage"
    source_raw = ASSETS / "kernel-squashfs.raw.bin"
    source_lzma = ASSETS / "kernel-squashfs.lzma"
    rootfs = ASSETS / "rootfs-product-xz-128k.squashfs"
    config = ASSETS / "kernel-squashfs.config"
    dtb = ASSETS / "topaz_mitrastar_squashfs.dtb"
    vmlinux = ASSETS / "kernel-squashfs.vmlinux"
    for path in (source_uimage, source_raw, source_lzma, rootfs, config, dtb, vmlinux):
        if not path.is_file():
            raise SystemExit(f"missing F164 input: {path}")

    uimage = source_uimage.read_bytes()
    values = list(struct.unpack(">7I4B32s", uimage[:64]))
    kernel_raw = source_raw.read_bytes()
    kernel_lzma = source_lzma.read_bytes()
    rootfs_data = rootfs.read_bytes()
    if uimage[64:] != kernel_raw:
        raise SystemExit("F164 uncompressed uImage payload mismatch")
    if lzma.decompress(kernel_lzma, format=lzma.FORMAT_ALONE) != kernel_raw:
        raise SystemExit("F164 kernel LZMA round-trip failed")
    if rootfs_data[:4] != b"hsqs":
        raise SystemExit("F164 rootfs SquashFS magic missing")

    kernel_region = ROOTFS_OFFSET - f71.RAS_OFFSET
    if len(kernel_lzma) > kernel_region:
        raise SystemExit(
            f"F164 kernel exceeds pre-rootfs region by {len(kernel_lzma) - kernel_region} bytes"
        )
    if len(rootfs_data) > ROOTFS_WINDOW:
        raise SystemExit(
            f"F164 SquashFS exceeds rootfs window by {len(rootfs_data) - ROOTFS_WINDOW} bytes"
        )

    payload = kernel_lzma + b"\0" * (kernel_region - len(kernel_lzma)) + rootfs_data
    image = bytearray(f71.TEMPLATE.read_bytes()[:f71.RAS_OFFSET])
    image.extend(payload)
    values[1] = 0
    values[2] = SOURCE_DATE_EPOCH
    values[3] = len(payload)
    values[6] = zlib.crc32(payload) & 0xFFFFFFFF
    values[8] = 0x13
    values[10] = 3
    values[11] = b"Linux-5.10-OpenMitraStar-SquashFS"[:32].ljust(32, b"\0")
    header = bytearray(struct.pack(">7I4B32s", *values))
    values[1] = zlib.crc32(header) & 0xFFFFFFFF
    image[:64] = struct.pack(">7I4B32s", *values)

    web = OUT / f"{BASE}.webformat.bin"
    web.write_bytes(image)
    if web.stat().st_size > f71.SLOT_BYTES:
        raise SystemExit("F164 image exceeds linux_live slot")
    if web.read_bytes()[ROOTFS_OFFSET:ROOTFS_OFFSET + 4] != b"hsqs":
        raise SystemExit("F164 SquashFS is not at the declared slot offset")

    for source, suffix in (
        (source_uimage, ".uncompressed.uImage"),
        (source_raw, ".kernel.raw.bin"),
        (source_lzma, ".kernel.lzma"),
        (rootfs, ".rootfs.squashfs"),
        (config, ".config"),
        (dtb, ".dtb"),
        (vmlinux, ".vmlinux"),
    ):
        shutil.copy2(source, OUT / f"{BASE}{suffix}")

    contract = subprocess.run(
        [
            sys.executable, str(f71.BOOTBASE), "--candidate-slot", str(web),
            "--candidate-name", "linux_live-f164-squashfs-product",
            "--parts-dir", str(f71.PARTS_DIR),
        ],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if contract.returncode:
        raise SystemExit(contract.stderr or contract.stdout)
    contract_path = OUT / "bootbase-contract.json"
    contract_path.write_text(contract.stdout, encoding="utf-8")
    contract_data = json.loads(contract.stdout)

    full_slot = bytes(image) + b"\xff" * (f71.SLOT_BYTES - len(image))
    manifest = {
        "schema": "openmitrastar.f164-squashfs-product/v1",
        "classification": "F164_OFFLINE_SQUASHFS_PRODUCT_PROTOTYPE_NO_FLASH",
        "source": {
            "firmware": "F163",
            "rootfs": "F163 CPIO with f110-fixed-size.pad removed",
        },
        "layout": {
            "slot_bytes": f71.SLOT_BYTES,
            "ras_header_bytes": f71.RAS_OFFSET,
            "kernel_lzma_offset": f"0x{f71.RAS_OFFSET:06x}",
            "kernel_lzma_bytes": len(kernel_lzma),
            "kernel_region_bytes": kernel_region,
            "kernel_headroom_bytes": kernel_region - len(kernel_lzma),
            "rootfs_offset": f"0x{ROOTFS_OFFSET:06x}",
            "rootfs_window_bytes": ROOTFS_WINDOW,
            "rootfs_squashfs_bytes": len(rootfs_data),
            "rootfs_headroom_bytes": ROOTFS_WINDOW - len(rootfs_data),
            "candidate_bytes": len(image),
            "slot_headroom_bytes": f71.SLOT_BYTES - len(image),
            "mtd_mapping": "read-only mtd-rom 0x90960000+0x00620000, Linux root=31:3",
        },
        "kernel": {
            "load": f"0x{values[4]:08x}",
            "entry": f"0x{values[5]:08x}",
            "compression": "lzma",
            "initramfs_source": "empty",
            "squashfs": True,
            "squashfs_xz": True,
        },
        "rootfs": {
            "format": "SquashFS 4.0",
            "compression": "xz",
            "block_size": 131072,
            "read_only": True,
            "writable_runtime": ["tmpfs:/run", "tmpfs:/tmp", "read-only:/persist initially"],
        },
        "artifacts": {
            "webformat": {"file": web.name, "bytes": web.stat().st_size, "sha256": sha256(web), "crc32": f71.crc32(web.read_bytes())},
            "full_slot": {"bytes": len(full_slot), "sha256": hashlib.sha256(full_slot).hexdigest(), "crc32": f"{zlib.crc32(full_slot) & 0xffffffff:08x}"},
            "kernel_lzma": {"file": f"{BASE}.kernel.lzma", "bytes": len(kernel_lzma), "sha256": hashlib.sha256(kernel_lzma).hexdigest()},
            "rootfs_squashfs": {"file": f"{BASE}.rootfs.squashfs", "bytes": len(rootfs_data), "sha256": hashlib.sha256(rootfs_data).hexdigest()},
            "dtb": {"bytes": dtb.stat().st_size, "sha256": sha256(dtb)},
            "config": {"bytes": config.stat().st_size, "sha256": sha256(config)},
        },
        "contracts": {
            "bootbase": contract_data.get("result"),
            "slot_fit": len(image) <= f71.SLOT_BYTES,
            "kernel_before_rootfs": len(kernel_lzma) <= kernel_region,
            "rootfs_magic_at_offset": True,
            "hardware_boot": "NOT_RUN",
            "flash": False,
        },
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only",
            "rollback": "mtd3/linux_safety via UART ATGO",
            "mtd5": "unchanged",
            "mtd6": "logical view represented by the rootfs mtd-rom window, never a physical write target",
        },
    }
    manifest_path = OUT / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    (OUT / "LAYOUT.md").write_text(
        "# F164 SquashFS layout\n\n"
        "- `0x000000..0x001fff`: Bootbase/RAS header area.\n"
        f"- `0x002000..0x{ROOTFS_OFFSET - 1:06x}`: LZMA kernel stream plus zero padding.\n"
        f"- `0x{ROOTFS_OFFSET:06x}..`: SquashFS-XZ root filesystem.\n"
        f"- Candidate size: `{len(image)}` bytes.\n"
        f"- Free slot tail: `{f71.SLOT_BYTES - len(image)}` bytes.\n\n"
        "This is an offline prototype. Do not flash until the dedicated boot and rollback gate is ready.\n",
        encoding="ascii",
    )
    sums = sorted(p for p in OUT.iterdir() if p.is_file() and p.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
