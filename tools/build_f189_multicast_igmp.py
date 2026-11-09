#!/usr/bin/env python3
"""Build F189 with NAPI-128 plus built-in multicast and IGMP snooping support."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

import build_f71_qcsapi_interp_from_f70 as f71
import build_f170_lyoko_foundation_runtime_fix as rootfs_engine
import compose_f164_squashfs_product as compose_engine


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f188-diagnostics-ui-from-f187/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f188-diagnostics-ui-from-f187-LZMA-OFFLINE-NO-FLASH"
FOUNDATION = ROOT / "versions/lyoko-foundation-1.8-f189-network"
OVERLAY = FOUNDATION / "overlay"
CONFIG = ROOT / "outputs/kernel-port/f175-network-capabilities-config-20260901/f175-network.config"
ASSETS = ROOT / "outputs/kernel-port/f189-multicast-igmp-20260901"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f189-multicast-igmp-from-f188/build"
BASE = "openmitrastar-linux510-q3-persistent-f189-multicast-igmp-from-f188-LZMA-OFFLINE-NO-FLASH"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
KERNEL_OUT = "/home/user/openmitrastar-build/f189-multicast-igmp"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path: Path) -> str:
    return f"{WS_ROOT}/{path.resolve().relative_to(ROOT.resolve()).as_posix()}"


def run_wsl(script: str, timeout: int = 1200) -> str:
    result = subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
    )
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)
    return result.stdout


@contextlib.contextmanager
def rootfs_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS",
        "OUT", "BASE", "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA",
    )
    old = {name: getattr(rootfs_engine, name) for name in names}
    try:
        rootfs_engine.SOURCE_BUILD = SOURCE_BUILD
        rootfs_engine.SOURCE_BASE = SOURCE_BASE
        rootfs_engine.FOUNDATION = FOUNDATION
        rootfs_engine.OVERLAY = OVERLAY
        rootfs_engine.ASSETS = ASSETS
        rootfs_engine.OUT = OUT
        rootfs_engine.BASE = BASE
        rootfs_engine.PRODUCT_VERSION = "lyoko-foundation-1.8-f189-network"
        rootfs_engine.ASSETS_SCHEMA = "openmitrastar.f189-multicast-assets/v1"
        rootfs_engine.DIFF_SCHEMA = "openmitrastar.f189-multicast-rootfs-diff/v1"
        yield
    finally:
        for name, value in old.items():
            setattr(rootfs_engine, name, value)


@contextlib.contextmanager
def compose_context():
    names = ("ASSETS", "OUT", "BASE")
    old = {name: getattr(compose_engine, name) for name in names}
    try:
        compose_engine.ASSETS = ASSETS
        compose_engine.OUT = OUT
        compose_engine.BASE = BASE
        yield
    finally:
        for name, value in old.items():
            setattr(compose_engine, name, value)


def build_kernel() -> dict[str, object]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    shell = f"""
set -eu
workspace={shlex.quote(WS_ROOT)}
src={shlex.quote(KERNEL_SRC)}
out={shlex.quote(KERNEL_OUT)}
assets={shlex.quote(wsl_path(ASSETS))}
config={shlex.quote(wsl_path(CONFIG))}
tc="$workspace/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
rm -rf "$out"
mkdir -p "$out" "$assets"
cp "$workspace/work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
cp "$workspace/work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c" "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
cp "$workspace/work/kernel-port/linux-5.10/drivers/mtd/maps/physmap-core.c" "$src/drivers/mtd/maps/physmap-core.c"
cp "$config" "$out/.config"
make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
grep -qx 'CONFIG_IP_MULTICAST=y' "$out/.config"
grep -qx 'CONFIG_BRIDGE_IGMP_SNOOPING=y' "$out/.config"
grep -qx 'CONFIG_VLAN_8021Q=y' "$out/.config"
grep -qx '# CONFIG_IP_MROUTE is not set' "$out/.config"
grep -qx '# CONFIG_VLAN_8021Q_GVRP is not set' "$out/.config"
grep -qx '# CONFIG_VLAN_8021Q_MVRP is not set' "$out/.config"
grep -q 'QTN_TOPAZ_EMAC_NAPI_WEIGHT.*128' "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j12 vmlinux uImage.bin dtbs > "$assets/kernel-build.log" 2>&1
cp "$out/.config" "$assets/kernel-squashfs.config"
cp "$out/vmlinux" "$assets/kernel-squashfs.vmlinux"
cp "$out/arch/arc/boot/uImage.bin" "$assets/kernel-squashfs.uncompressed.uImage"
cp "$out/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$assets/topaz_mitrastar_squashfs.dtb"
"""
    run_wsl(shell)
    uimage = ASSETS / "kernel-squashfs.uncompressed.uImage"
    raw = ASSETS / "kernel-squashfs.raw.bin"
    raw.write_bytes(uimage.read_bytes()[64:])
    lzma = ASSETS / "kernel-squashfs.lzma"
    lzma.write_bytes(f71.encode_lzma_legacy(raw))
    config_text = (ASSETS / "kernel-squashfs.config").read_text(encoding="utf-8")
    required = (
        "CONFIG_IP_MULTICAST=y", "CONFIG_BRIDGE_IGMP_SNOOPING=y", "CONFIG_VLAN_8021Q=y",
        "# CONFIG_IP_MROUTE is not set", "# CONFIG_VLAN_8021Q_GVRP is not set", "# CONFIG_VLAN_8021Q_MVRP is not set",
    )
    if not all(f"{line}\n" in config_text for line in required):
        raise SystemExit("F189 resolved kernel config contract failed")
    return {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)} for path in (uimage, raw, lzma, ASSETS / "kernel-squashfs.config", ASSETS / "kernel-squashfs.vmlinux", ASSETS / "topaz_mitrastar_squashfs.dtb")}


def verify_napi_weight(vmlinux: Path) -> dict[str, object]:
    objdump = f"{WS_ROOT}/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-objdump"
    command = f'"{objdump}" -dr "{wsl_path(vmlinux)}" | sed -n \'/<qtn_emac_probe>/,/^$/p\''
    output = run_wsl(command, timeout=120)
    lines = output.splitlines()
    call = next((index for index, line in enumerate(lines) if "<netif_napi_add>" in line), None)
    if call is None or not any(re.search(r"\bmov_s\s+r3,0x80\b", line) for line in lines[max(0, call - 16):call + 2]):
        raise SystemExit("F189 binary lost NAPI weight 128")
    return {"result": "PASS", "weight": 128, "function": "qtn_emac_probe"}


def main() -> int:
    with rootfs_context():
        rootfs_assets = rootfs_engine.prepare_assets()
    kernel_assets = build_kernel()
    with compose_context():
        rc = compose_engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    napi = verify_napi_weight(OUT / f"{BASE}.vmlinux")
    registry = json.loads((OVERLAY / "etc/lyoko/capabilities.json").read_text(encoding="utf-8"))
    igmp = next(item for item in registry["items"] if item["id"] == "network.igmp")
    manifest.update({
        "schema": "openmitrastar.f189-multicast-igmp/v1",
        "classification": "F189_MULTICAST_IGMP_KERNEL_SUPPORT_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {"firmware": "F188", "installed_firmware": "F170"},
        "change_scope": {
            "kernel": "CONFIG_IP_MULTICAST=y and CONFIG_BRIDGE_IGMP_SNOOPING=y",
            "preserved": "CONFIG_VLAN_8021Q=y and NAPI weight 128",
            "disabled": "IP multicast routing, GVRP and MVRP",
            "runtime_policy": "no bridge multicast or VLAN policy enabled",
            "rootfs": "F188 plus release identity and IGMP capability state",
            "radios_packages_session_web": "otherwise byte-identical to F188",
        },
        "kernel_assets": kernel_assets,
        "napi_binary_contract": napi,
        "network_capability": igmp,
        "parents": {
            "f188_webformat_sha256": source["artifacts"]["webformat"]["sha256"],
            "f188_rootfs_sha256": source["artifacts"]["rootfs_squashfs"]["sha256"],
            "f175_config_sha256": sha256(CONFIG),
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "boot, bridge multicast state, IGMP joins/leaves, multicast traffic and dual-radio regression",
        },
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after exact authorization",
            "rollback": "mtd3/linux_safety via manual UART ATGO",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "policy_activation": "none in this candidate",
        },
        "foundation_assets": rootfs_assets,
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
