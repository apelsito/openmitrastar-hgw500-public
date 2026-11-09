#!/usr/bin/env python3
"""Reproducibly build the kernel and SquashFS assets consumed by F164."""
from __future__ import annotations

import hashlib
import json
import shlex
import subprocess
import sys
from pathlib import Path

import build_f71_qcsapi_interp_from_f70 as f71
import build_f163_emac_rxrestart16_from_f162 as f163


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/kernel-port/f164-squashfs-layout-20260901"
SOURCE_RAW = f163.OUT / f"{f163.BASE_OUT}.decompressed.bin"
PAD_ENTRY = "usr/share/openmitrastar/radio5g/f110-fixed-size.pad"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f164-squashfs-kernel"
ROOTFS_STAGE = "/home/user/openmitrastar-build/f164-squashfs-root"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_wsl(script: str, timeout: int = 900) -> None:
    proc = subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout or f"WSL failed rc={proc.returncode}")
    if proc.stdout:
        print(proc.stdout, end="")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    raw = SOURCE_RAW.read_bytes()
    start, entries, remainder = f71.parse_first_cpio(raw)
    pads = [entry for entry in entries if entry.name == PAD_ENTRY]
    if len(pads) != 1:
        raise SystemExit(f"expected one fixed-size pad, found {len(pads)}")
    kept = [entry for entry in entries if entry.name != PAD_ENTRY]
    cpio = b"".join(f71.serialize_entry(entry) for entry in kept)
    cpio_path = OUT / "f163-rootfs-no-padding.cpio"
    cpio_path.write_bytes(cpio)
    assets_wsl = f"{WS_ROOT}/{OUT.relative_to(ROOT).as_posix()}"

    shell = f"""
set -eu
workspace={shlex.quote(WS_ROOT)}
src={shlex.quote(KERNEL_SRC)}
out={shlex.quote(KERNEL_OUT)}
rootfs={shlex.quote(ROOTFS_STAGE)}
assets={shlex.quote(assets_wsl)}
tc="$workspace/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
rm -rf "$rootfs" "$out"
mkdir -p "$rootfs" "$out"
cd "$rootfs"
cpio -idm --no-absolute-filenames < "$assets/f163-rootfs-no-padding.cpio" > "$assets/rootfs-cpio-extract.log" 2>&1
test ! -e "$rootfs/{PAD_ENTRY}"
mksquashfs "$rootfs" "$assets/rootfs-product-xz-128k.squashfs" -noappend -all-root -comp xz -b 131072 -no-xattrs -no-exports -all-time 1785024000 -mkfs-time 1785024000 -no-progress > "$assets/rootfs-product-xz-build.log"
unsquashfs -s "$assets/rootfs-product-xz-128k.squashfs" > "$assets/rootfs-product-xz-superblock.txt"
cp "$workspace/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
cp "$workspace/work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c" "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
cp "$workspace/work/kernel-port/linux-5.10/drivers/mtd/maps/physmap-core.c" "$src/drivers/mtd/maps/physmap-core.c"
cp "$workspace/work/mission-state/q3-persistent-composite-f163-emac-rxrestart16-from-f162/build/{f163.BASE_OUT}.config" "$out/.config"
"$src/scripts/config" --file "$out/.config" --set-str INITRAMFS_SOURCE "" --enable SQUASHFS --enable SQUASHFS_XZ --enable XZ_DEC --enable SQUASHFS_DECOMP_SINGLE --disable SQUASHFS_DECOMP_MULTI --disable SQUASHFS_DECOMP_MULTI_PERCPU --disable SQUASHFS_ZLIB --disable XZ_DEC_BCJ --disable XZ_DEC_X86 --disable XZ_DEC_POWERPC --disable XZ_DEC_IA64 --disable XZ_DEC_ARM --disable XZ_DEC_ARMTHUMB --disable XZ_DEC_SPARC --set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_squashfs
make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j12 vmlinux uImage.bin dtbs > "$assets/kernel-build.log" 2>&1
cp "$out/.config" "$assets/kernel-squashfs.config"
cp "$out/vmlinux" "$assets/kernel-squashfs.vmlinux"
cp "$out/arch/arc/boot/uImage.bin" "$assets/kernel-squashfs.uncompressed.uImage"
cp "$out/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$assets/topaz_mitrastar_squashfs.dtb"
"""
    run_wsl(shell)

    uimage = OUT / "kernel-squashfs.uncompressed.uImage"
    raw_kernel = OUT / "kernel-squashfs.raw.bin"
    raw_kernel.write_bytes(uimage.read_bytes()[64:])
    lzma_path = OUT / "kernel-squashfs.lzma"
    lzma_path.write_bytes(f71.encode_lzma_legacy(raw_kernel))

    manifest = {
        "schema": "openmitrastar.f164-squashfs-assets/v1",
        "source_firmware": str(SOURCE_RAW.relative_to(ROOT)),
        "source_overrides": {
            "dts": {
                "path": "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts",
                "sha256": sha256(ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"),
            },
            "physmap": {
                "path": "work/kernel-port/linux-5.10/drivers/mtd/maps/physmap-core.c",
                "sha256": sha256(ROOT / "work/kernel-port/linux-5.10/drivers/mtd/maps/physmap-core.c"),
            },
            "emac": {
                "path": "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c",
                "sha256": sha256(ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"),
            },
        },
        "cpio": {
            "start": start,
            "end": len(raw) - len(remainder),
            "entries_before": len(entries),
            "entries_after": len(kept),
            "removed_pad_bytes": len(pads[0].data),
            "file": cpio_path.name,
            "sha256": sha256(cpio_path),
        },
        "artifacts": {},
    }
    for path in (
        OUT / "rootfs-product-xz-128k.squashfs", uimage, raw_kernel, lzma_path,
        OUT / "kernel-squashfs.config", OUT / "kernel-squashfs.vmlinux",
        OUT / "topaz_mitrastar_squashfs.dtb",
    ):
        manifest["artifacts"][path.name] = {"bytes": path.stat().st_size, "sha256": sha256(path)}
    (OUT / "assets-manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
