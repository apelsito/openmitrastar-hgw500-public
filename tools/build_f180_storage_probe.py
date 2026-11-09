#!/usr/bin/env python3
"""Build F180 with a read-only rootfs/store split inside physical mtd4."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import shlex
import shutil

import build_f170_lyoko_foundation_runtime_fix as rootfs_engine
import build_f71_qcsapi_interp_from_f70 as f71
import compose_f164_squashfs_product as compose_engine


ROOT = Path(__file__).resolve().parents[1]
F179_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f179-integrated-napi-package-manager/build"
F179_BASE = "openmitrastar-linux510-q3-persistent-f179-integrated-napi-package-manager-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f180-storage-readonly-probe-20260901"
EMPTY_OVERLAY = ASSETS / "release-overlay"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f180-storage-readonly-probe/build"
BASE = "openmitrastar-linux510-q3-persistent-f180-storage-readonly-probe-LZMA-OFFLINE-NO-FLASH"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_storage_probe.dts"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f180-storage-readonly-probe"
ROOTFS_WINDOW = 0x460000
STORE_OFFSET = 0xDC0000
STORE_SIZE = 0x1C0000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path: Path) -> str:
    return f"{WS_ROOT}/{path.resolve().relative_to(ROOT.resolve()).as_posix()}"


@contextlib.contextmanager
def rootfs_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS",
        "OUT", "BASE", "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA",
    )
    old = {name: getattr(rootfs_engine, name) for name in names}
    try:
        rootfs_engine.SOURCE_BUILD = F179_BUILD
        rootfs_engine.SOURCE_BASE = F179_BASE
        rootfs_engine.FOUNDATION = EMPTY_OVERLAY
        rootfs_engine.OVERLAY = EMPTY_OVERLAY
        rootfs_engine.ASSETS = ASSETS
        rootfs_engine.OUT = OUT
        rootfs_engine.BASE = BASE
        rootfs_engine.PRODUCT_VERSION = "lyoko-foundation-1.3-f180"
        rootfs_engine.ASSETS_SCHEMA = "openmitrastar.f180-storage-assets/v1"
        rootfs_engine.DIFF_SCHEMA = "openmitrastar.f180-storage-rootfs-diff/v1"
        yield
    finally:
        for name, value in old.items():
            setattr(rootfs_engine, name, value)


@contextlib.contextmanager
def compose_context():
    names = ("ASSETS", "OUT", "BASE", "ROOTFS_WINDOW")
    old = {name: getattr(compose_engine, name) for name in names}
    try:
        compose_engine.ASSETS = ASSETS
        compose_engine.OUT = OUT
        compose_engine.BASE = BASE
        compose_engine.ROOTFS_WINDOW = ROOTFS_WINDOW
        yield
    finally:
        for name, value in old.items():
            setattr(compose_engine, name, value)


def build_kernel() -> None:
    assets = wsl_path(ASSETS)
    variant = wsl_path(DTS)
    canonical = wsl_path(ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts")
    emac = wsl_path(ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c")
    physmap = wsl_path(ROOT / "work/kernel-port/linux-5.10/drivers/mtd/maps/physmap-core.c")
    config = wsl_path(F179_BUILD / f"{F179_BASE}.config")
    shell = f"""
set -eu
src={shlex.quote(KERNEL_SRC)}
out={shlex.quote(KERNEL_OUT)}
assets={shlex.quote(assets)}
tc={shlex.quote(WS_ROOT + '/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')}
restore={shlex.quote(canonical)}
trap 'cp "$restore" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"' EXIT HUP INT TERM
rm -rf "$out"
mkdir -p "$out"
cp {shlex.quote(variant)} "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
cp {shlex.quote(emac)} "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
cp {shlex.quote(physmap)} "$src/drivers/mtd/maps/physmap-core.c"
cp {shlex.quote(config)} "$out/.config"
"$src/scripts/config" --file "$out/.config" --set-str INITRAMFS_SOURCE "" --set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_squashfs
make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j12 vmlinux uImage.bin dtbs > "$assets/kernel-build.log" 2>&1
cp "$out/.config" "$assets/kernel-squashfs.config"
cp "$out/vmlinux" "$assets/kernel-squashfs.vmlinux"
cp "$out/arch/arc/boot/uImage.bin" "$assets/kernel-squashfs.uncompressed.uImage"
cp "$out/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$assets/topaz_mitrastar_squashfs.dtb"
"""
    rootfs_engine.run_wsl(shell)
    uimage = ASSETS / "kernel-squashfs.uncompressed.uImage"
    raw = ASSETS / "kernel-squashfs.raw.bin"
    raw.write_bytes(uimage.read_bytes()[64:])
    (ASSETS / "kernel-squashfs.lzma").write_bytes(f71.encode_lzma_legacy(raw))


def main() -> int:
    EMPTY_OVERLAY.mkdir(parents=True, exist_ok=True)
    with rootfs_context():
        rootfs_assets = rootfs_engine.prepare_assets()
    build_kernel()
    with compose_context():
        rc = compose_engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f179 = json.loads((F179_BUILD / "manifest.json").read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f180-storage-readonly-probe/v1",
        "classification": "F180_STORAGE_SPLIT_READONLY_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {"firmware": "F179", "installed_firmware": "F170"},
        "change_scope": {
            "rootfs_live": "read-only MTD window 0x90960000+0x00460000, still Linux root=31:3",
            "lyoko_store": "new read-only MTD window 0x90dc0000+0x001c0000",
            "mounts": "store is not mounted or formatted",
            "kernel_datapath_rootfs": "F179 plus release identity and DTS layout only",
        },
        "foundation_assets": rootfs_assets,
        "parents": {
            "f179_webformat_sha256": f179["artifacts"]["webformat"]["sha256"],
            "f179_rootfs_sha256": f179["artifacts"]["rootfs_squashfs"]["sha256"],
            "f179_kernel_lzma_sha256": f179["artifacts"]["kernel_lzma"]["sha256"],
        },
        "storage": {
            "rootfs_offset": "0x00960000",
            "rootfs_size": f"0x{ROOTFS_WINDOW:08x}",
            "store_offset": f"0x{STORE_OFFSET:08x}",
            "store_size": f"0x{STORE_SIZE:08x}",
            "store_mode": "read-only-probe",
            "store_mount": "none",
            "store_write": False,
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot root=31:3, mtd3 rootfs size 0x460000, mtd4 lyoko_store size 0x1c0000 and no writes",
        },
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO",
            "protected_partitions": "physical mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "lyoko_store": "read-only and unformatted",
        },
    })
    manifest["layout"]["rootfs_window_bytes"] = ROOTFS_WINDOW
    manifest["layout"]["rootfs_headroom_bytes"] = ROOTFS_WINDOW - manifest["artifacts"]["rootfs_squashfs"]["bytes"]
    manifest["layout"]["mtd_mapping"] = "read-only rootfs 0x90960000+0x00460000 and store 0x90dc0000+0x001c0000"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
