#!/usr/bin/env python3
"""Build F207 from F205 with a read-only mtd4 store split and SPI probe."""
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
F205_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f205-runtime-signature-from-f203/build"
F205_BASE = "openmitrastar-linux510-q3-persistent-f205-runtime-signature-from-f203-LZMA-OFFLINE-NO-FLASH"
ASSETS = ROOT / "outputs/kernel-port/f207-storage-readonly-probe-20260901"
OVERLAY = ASSETS / "combined-overlay"
SPI_OVERLAY = ROOT / "versions/lyoko-spi-probe-1.0/overlay"
SPI_SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-spi-probe"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f207-storage-readonly-probe-from-f205/build"
BASE = "openmitrastar-linux510-q3-persistent-f207-storage-readonly-probe-from-f205-LZMA-OFFLINE-NO-FLASH"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_storage_probe.dts"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f207-storage-readonly-probe"
MODULE_BUILD = "/home/user/openmitrastar-build/f207-spi-readonly-probe-module"
ROOTFS_WINDOW = 0x460000
LIVE_OFFSET = 0x7E0000
STORE_OFFSET = 0xDC0000
STORE_SIZE = 0x1C0000
STORE_SLOT_OFFSET = STORE_OFFSET - LIVE_OFFSET


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
        rootfs_engine.SOURCE_BUILD = F205_BUILD
        rootfs_engine.SOURCE_BASE = F205_BASE
        rootfs_engine.FOUNDATION = OVERLAY
        rootfs_engine.OVERLAY = OVERLAY
        rootfs_engine.ASSETS = ASSETS
        rootfs_engine.OUT = OUT
        rootfs_engine.BASE = BASE
        rootfs_engine.PRODUCT_VERSION = "lyoko-foundation-2.9-f207"
        rootfs_engine.ASSETS_SCHEMA = "openmitrastar.f207-storage-assets/v1"
        rootfs_engine.DIFF_SCHEMA = "openmitrastar.f207-storage-rootfs-diff/v1"
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
    config = wsl_path(F205_BUILD / f"{F205_BASE}.config")
    spi_source = wsl_path(SPI_SOURCE)
    shell = f"""
set -eu
src={shlex.quote(KERNEL_SRC)}
out={shlex.quote(KERNEL_OUT)}
assets={shlex.quote(assets)}
mod={shlex.quote(MODULE_BUILD)}
spi_source={shlex.quote(spi_source)}
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
rm -rf "$mod"
mkdir -p "$mod"
cp "$spi_source/qtn-topaz-spi-probe.c" "$mod/"
cp "$spi_source/Makefile" "$mod/"
make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" modules_prepare
make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" M="$mod" modules >"$assets/spi-module-build.log" 2>&1
cp "$mod/qtn-topaz-spi-probe.ko" "$assets/"
"${{tc}}readelf" -h "$assets/qtn-topaz-spi-probe.ko" >"$assets/spi-module-readelf.txt"
"${{tc}}objdump" -dr "$assets/qtn-topaz-spi-probe.ko" >"$assets/spi-module-objdump.txt"
grep -q 'ARC700, v4 ABI' "$assets/spi-module-readelf.txt"
strings "$assets/qtn-topaz-spi-probe.ko" | grep -q 'OMSPIPROBE'
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


def publish_kernel_assets() -> None:
    assets = wsl_path(ASSETS)
    shell = f"""
set -eu
out={shlex.quote(KERNEL_OUT)}
assets={shlex.quote(assets)}
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


def prepare_overlay() -> None:
    if OVERLAY.exists():
        shutil.rmtree(OVERLAY)
    shutil.copytree(SPI_OVERLAY, OVERLAY)
    module = ASSETS / "qtn-topaz-spi-probe.ko"
    if not module.is_file():
        raise SystemExit("missing F207 SPI probe module")
    target = OVERLAY / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/diagnostics/qtn-topaz-spi-probe.ko"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(module, target)


def main() -> int:
    ASSETS.mkdir(parents=True, exist_ok=True)
    build_kernel()
    prepare_overlay()
    with rootfs_context():
        rootfs_assets = rootfs_engine.prepare_assets()
    publish_kernel_assets()
    with compose_context():
        rc = compose_engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f205 = json.loads((F205_BUILD / "manifest.json").read_text(encoding="ascii"))
    candidate = OUT / manifest["artifacts"]["webformat"]["file"]
    candidate_bytes = candidate.read_bytes()
    full_bytes = candidate_bytes + b"\xff" * (0x7A0000 - len(candidate_bytes))
    store_erased = all(value == 0xFF for value in full_bytes[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_bytes) > STORE_SLOT_OFFSET:
        raise SystemExit("F207 candidate overlaps or initializes lyoko_store")
    manifest.update({
        "schema": "openmitrastar.f207-storage-readonly-probe/v1",
        "classification": "F207_F205_STORAGE_SPLIT_SPI_READONLY_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "release_eligible": False,
        "source": {"firmware": "F205", "installed_firmware": "F170"},
        "change_scope": {
            "rootfs_live": "read-only MTD window 0x90960000+0x00460000, still Linux root=31:3",
            "lyoko_store": "new read-only MTD window 0x90dc0000+0x001c0000",
            "mounts": "store is not mounted or formatted",
            "spi_probe": "nonfatal read-only JEDEC/status module rebuilt against F207 kernel",
            "userspace_packages_radios_security": "F205 plus SPI probe init/module only",
        },
        "foundation_assets": rootfs_assets,
        "parents": {
            "f205_webformat_sha256": f205["artifacts"]["webformat"]["sha256"],
            "f205_rootfs_sha256": f205["artifacts"]["rootfs_squashfs"]["sha256"],
            "f205_kernel_lzma_sha256": f205["artifacts"]["kernel_lzma"]["sha256"],
        },
        "storage": {
            "rootfs_offset": "0x00960000",
            "rootfs_size": f"0x{ROOTFS_WINDOW:08x}",
            "store_offset": f"0x{STORE_OFFSET:08x}",
            "store_size": f"0x{STORE_SIZE:08x}",
            "store_mode": "read-only-probe",
            "store_mount": "none",
            "store_write": False,
            "store_erased_ff": store_erased,
            "store_slot_offset": f"0x{STORE_SLOT_OFFSET:08x}",
            "candidate_ends_before_store": len(candidate_bytes) <= STORE_SLOT_OFFSET,
        },
        "spi_probe": {
            "module_sha256": sha256(ASSETS / "qtn-topaz-spi-probe.ko"),
            "expected_jedec_id": "0xc22018",
            "expected_device": "MX25L12836E",
            "mtd_registration": False,
            "erase": False,
            "write": False,
            "state_file": "/run/openmitrastar/spi-probe.state",
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot, rootfs mtd3 0x460000, lyoko_store mtd4 0x1c0000, JEDEC 0xc22018 and zero writes",
        },
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO",
            "protected_partitions": "physical mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "lyoko_store": "read-only and unformatted",
            "module_registers_mtd": False,
            "module_has_write_path": False,
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
