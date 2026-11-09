#!/usr/bin/env python3
"""Build an offline Linux 5.10 safety-slot image from the proven F170 baseline."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import shlex
import shutil
import subprocess

import build_f71_qcsapi_interp_from_f70 as f71
import compose_f164_squashfs_product as compose_engine


ROOT = Path(__file__).resolve().parents[1]
F170_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f170-lyoko-foundation-runtime-fix/build"
F170_BASE = "openmitrastar-linux510-q3-persistent-f170-lyoko-foundation-runtime-fix-LZMA-OFFLINE-NO-FLASH"
CONFIG = F170_BUILD / f"{F170_BASE}.config"
ROOTFS = F170_BUILD / f"{F170_BASE}.rootfs.squashfs"
LIVE_DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
SAFETY_DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_safety_squashfs.dts"
EMAC = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
PHYSMAP = ROOT / "work/kernel-port/linux-5.10/drivers/mtd/maps/physmap-core.c"
ASSETS = ROOT / "outputs/kernel-port/f194-linux510-safety-slot-20260901"
OUT = ROOT / "work/mission-state/q3-recovery-f194-linux510-safety-slot/build"
BASE = "openmitrastar-linux510-q3-recovery-f194-safety-slot-LZMA-OFFLINE-NO-FLASH"
OEM_PARTS = ROOT / "hgw500bna-qcv2-firmware-dump-verified"
DISTRO = "podman-mem9-tidb"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
CONTROL_OUT = "/home/user/openmitrastar-build/f194-control-live"
SAFETY_OUT = "/home/user/openmitrastar-build/f194-safety-slot"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path: Path) -> str:
    return f"{WS_ROOT}/{path.resolve().relative_to(ROOT.resolve()).as_posix()}"


def run_wsl(script: str, timeout: int = 1800) -> str:
    proc = subprocess.run(
        ["wsl.exe", "-d", DISTRO, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)
    return proc.stdout


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


def build_kernel_pair() -> dict[str, object]:
    ASSETS.mkdir(parents=True, exist_ok=True)
    emac64 = ASSETS / "qtn-topaz-emac-napi64.c"
    source = EMAC.read_text(encoding="utf-8")
    transforms = (
        (
            "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t128\n"
            "#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t128\n",
            "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t128\n",
        ),
        (
            '\t\t"napi_weight=%u\\npoll_ticks=%u\\npoll_napi_schedules=%u\\npoll_forced_napi=%u\\n"',
            '\t\t"poll_ticks=%u\\npoll_napi_schedules=%u\\npoll_forced_napi=%u\\n"',
        ),
        (
            "READ_ONCE(emac->irq_napi_schedules), QTN_TOPAZ_EMAC_NAPI_WEIGHT,\n"
            "\t\tREAD_ONCE(emac->poll_ticks),",
            "READ_ONCE(emac->irq_napi_schedules), READ_ONCE(emac->poll_ticks),",
        ),
        (
            "netif_napi_add(ndev, &emac->napi, qtn_emac_poll,\n"
            "\t\t\t QTN_TOPAZ_EMAC_NAPI_WEIGHT);",
            "netif_napi_add(ndev, &emac->napi, qtn_emac_poll, 64);",
        ),
    )
    reconstructed = source
    for old, new in transforms:
        if reconstructed.count(old) != 1:
            raise SystemExit(f"cannot derive exact F170 EMAC source; missing transform: {old!r}")
        reconstructed = reconstructed.replace(old, new)
    if hashlib.sha256(reconstructed.encode()).hexdigest() != "f6f9794fba104dd3a46835bc3300f885fefc6c9ab69976daf3485646dfc76018":
        raise SystemExit("reconstructed F170 EMAC source hash mismatch")
    emac64.write_text(reconstructed, encoding="utf-8")
    shell = f"""
set -eu
workspace={shlex.quote(WS_ROOT)}
src={shlex.quote(KERNEL_SRC)}
control={shlex.quote(CONTROL_OUT)}
safety={shlex.quote(SAFETY_OUT)}
assets={shlex.quote(wsl_path(ASSETS))}
config={shlex.quote(wsl_path(CONFIG))}
live_dts={shlex.quote(wsl_path(LIVE_DTS))}
safety_dts={shlex.quote(wsl_path(SAFETY_DTS))}
emac64={shlex.quote(wsl_path(emac64))}
physmap={shlex.quote(wsl_path(PHYSMAP))}
tc="$workspace/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-"
backup=$(mktemp -d)
cp "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts" "$backup/live.dts"
cp "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c" "$backup/emac.c"
trap 'cp "$backup/live.dts" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"; cp "$backup/emac.c" "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"; rm -rf "$backup"' EXIT HUP INT TERM
cp "$emac64" "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
cp "$physmap" "$src/drivers/mtd/maps/physmap-core.c"
build_one() {{
  out=$1; dts=$2; prefix=$3
  rm -rf "$out"; mkdir -p "$out"
  cp "$dts" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
  cp "$config" "$out/.config"
  "$src/scripts/config" --file "$out/.config" --set-str INITRAMFS_SOURCE "" --set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_squashfs
  make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
  SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j12 vmlinux uImage.bin dtbs > "$assets/$prefix-build.log" 2>&1
  cp "$out/.config" "$assets/$prefix.config"
  cp "$out/vmlinux" "$assets/$prefix.vmlinux"
  cp "$out/arch/arc/boot/uImage.bin" "$assets/$prefix.uncompressed.uImage"
  cp "$out/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$assets/$prefix.dtb"
}}
build_one "$control" "$live_dts" control-live
build_one "$safety" "$safety_dts" safety-slot
"""
    run_wsl(shell)
    for prefix in ("control-live", "safety-slot"):
        uimage = ASSETS / f"{prefix}.uncompressed.uImage"
        raw = ASSETS / f"{prefix}.raw.bin"
        raw.write_bytes(uimage.read_bytes()[64:])
        (ASSETS / f"{prefix}.lzma").write_bytes(f71.encode_lzma_legacy(raw))
    f170_kernel = F170_BUILD / f"{F170_BASE}.kernel.lzma"
    control = ASSETS / "control-live.lzma"
    if sha256(control) != sha256(f170_kernel):
        raise SystemExit("control rebuild does not reproduce the installed F170 kernel")
    for source_path, target in (
        (ASSETS / "safety-slot.uncompressed.uImage", ASSETS / "kernel-squashfs.uncompressed.uImage"),
        (ASSETS / "safety-slot.raw.bin", ASSETS / "kernel-squashfs.raw.bin"),
        (ASSETS / "safety-slot.lzma", ASSETS / "kernel-squashfs.lzma"),
        (ASSETS / "safety-slot.config", ASSETS / "kernel-squashfs.config"),
        (ASSETS / "safety-slot.vmlinux", ASSETS / "kernel-squashfs.vmlinux"),
        (ASSETS / "safety-slot.dtb", ASSETS / "topaz_mitrastar_squashfs.dtb"),
    ):
        shutil.copy2(source_path, target)
    shutil.copy2(ROOTFS, ASSETS / "rootfs-product-xz-128k.squashfs")
    return {
        "control_kernel_sha256": sha256(control),
        "f170_kernel_sha256": sha256(f170_kernel),
        "safety_kernel_sha256": sha256(ASSETS / "safety-slot.lzma"),
        "live_dtb_sha256": sha256(ASSETS / "control-live.dtb"),
        "safety_dtb_sha256": sha256(ASSETS / "safety-slot.dtb"),
    }


def main() -> int:
    control = build_kernel_pair()
    with compose_context():
        rc = compose_engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f170 = json.loads((F170_BUILD / "manifest.json").read_text(encoding="ascii"))
    candidate = OUT / f"{BASE}.webformat.bin"
    safety_slot = OUT / f"{BASE}.mtd3-full-slot.bin"
    safety_slot.write_bytes(candidate.read_bytes() + b"\xff" * (0x7A0000 - candidate.stat().st_size))
    if sha256(safety_slot) != manifest["artifacts"]["full_slot"]["sha256"]:
        raise SystemExit("F194 safety full-slot hash mismatch")

    contract_parts = ASSETS / "bootbase-safety-contract-parts"
    if contract_parts.exists():
        shutil.rmtree(contract_parts)
    contract_parts.mkdir(parents=True)
    for index in (0, 1, 2, 5):
        shutil.copy2(OEM_PARTS / f"hgw500_mtdblock{index}.bin", contract_parts / f"hgw500_mtdblock{index}.bin")
    shutil.copy2(safety_slot, contract_parts / "hgw500_mtdblock3.bin")
    f170_image = F170_BUILD / f"{F170_BASE}.webformat.bin"
    (contract_parts / "hgw500_mtdblock4.bin").write_bytes(f170_image.read_bytes() + b"\xff" * (0x7A0000 - f170_image.stat().st_size))
    safety_contract_path = OUT / "safety-bootbase-contract.json"
    proc = subprocess.run(
        [
            "python", str(ROOT / "tools/bootbase_contract_emulator.py"),
            "--parts-dir", str(contract_parts), "--json-out", str(safety_contract_path),
        ],
        cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120, check=False,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)
    safety_contract = json.loads(safety_contract_path.read_text(encoding="utf-8"))
    decision = safety_contract["decision"]
    if safety_contract.get("result") != "PASS" or decision.get("handoff_slot") != "linux_safety":
        raise SystemExit("F194 safety Bootbase contract did not select linux_safety")
    manifest.update({
        "schema": "openmitrastar.f194-linux510-safety-slot/v1",
        "classification": "F194_LINUX510_SAFETY_SLOT_OFFLINE_NOT_AUTHORIZED",
        "candidate_eligible": False,
        "flash_supported": False,
        "release_eligible": False,
        "target_slot": "mtd3/linux_safety",
        "source": {"runtime": "F170", "rootfs": "byte-identical F170", "installed_firmware": "F170"},
        "change_scope": {
            "single_variable": "built-in DTB rootfs window moved from physical mtd4 to physical mtd3",
            "napi_weight": 64,
            "rootfs": "byte-identical F170",
            "boot_environment": "must remain unchanged",
        },
        "control_rebuild": control,
        "rootfs_window": {"address": "0x901c0000", "size": "0x00620000", "root_device": "31:3"},
        "safety_bootbase_contract": {
            "result": safety_contract["result"],
            "bootselect": decision["bootselect"],
            "selected_slot": decision["selected_slot"],
            "handoff_slot": decision["handoff_slot"],
            "fallback_slot": decision["fallback_slot"],
            "path": safety_contract_path.name,
        },
        "parents": {
            "f170_kernel_lzma_sha256": f170["artifacts"]["kernel_lzma"]["sha256"],
            "f170_rootfs_sha256": f170["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "physical_validation": {"status": "NOT_RUN", "required": "exceptionally authorized mtd3 write, readback and cold-boot recovery proof"},
        "safety": {
            "normal_iteration_target": "mtd4/linux_live only",
            "mtd3_write": "forbidden without separate recovery authorization",
            "mtd0_mtd1_mtd2_mtd4_mtd5": "must remain unchanged during recovery provisioning",
            "bootenv_write": False,
        },
    })
    manifest["layout"]["mtd_mapping"] = "read-only rootfs_safety 0x901c0000+0x00620000, Linux root=31:3"
    manifest["artifacts"]["safety_full_slot"] = {
        "file": safety_slot.name,
        "bytes": safety_slot.stat().st_size,
        "sha256": sha256(safety_slot),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
