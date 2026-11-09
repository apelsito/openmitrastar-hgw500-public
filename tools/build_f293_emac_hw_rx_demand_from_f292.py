#!/usr/bin/env python3
"""Build F293 from F292 with hardware RX-demand telemetry only."""
from __future__ import annotations

import argparse
import atexit
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

import build_f170_lyoko_foundation_runtime_fix as foundation
import compose_f164_squashfs_product as compose_engine
from build_f196_device_personalized import verify_embedded_key
from init_lyoko_device_host_key import DEFAULT_ROOT, DEFAULT_TOOL, DEVICE_RE, inspect_key, restrict_acl


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac-f293-hw-rx-demand.c"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_storage_probe.dts"
PHYSMAP = ROOT / "work/kernel-port/linux-5.10/drivers/mtd/maps/physmap-core.c"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
ROOTFS_WINDOW = 0x460000
STORE_SLOT_OFFSET = 0x5E0000
STORE_SIZE = 0x1C0000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path: Path) -> str:
    value = path.resolve().as_posix()
    drive, tail = value.split(":/", 1)
    return f"/mnt/{drive.lower()}/{tail}"


def run_wsl(script: str, distro: str, timeout: int = 900) -> str:
    proc = subprocess.run(
        ["wsl.exe", "-d", distro, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=timeout,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout or f"WSL failed rc={proc.returncode}")
    return proc.stdout or ""


def build_kernel(assets: Path, source_config: Path, distro: str) -> None:
    kernel_out = "/home/user/openmitrastar-build/f293-emac-hw-rx-demand"
    canonical_dts = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
    shell = f'''
set -eu
src={shlex.quote(KERNEL_SRC)}
out={shlex.quote(kernel_out)}
assets={shlex.quote(wsl_path(assets))}
tc={shlex.quote(WS_ROOT + '/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')}
restore_dts={shlex.quote(wsl_path(canonical_dts))}
restore_driver={shlex.quote(wsl_path(ROOT / 'work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c'))}
trap 'cp "$restore_dts" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"; cp "$restore_driver" "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"' EXIT HUP INT TERM
rm -rf "$out"
mkdir -p "$out" "$assets"
cp {shlex.quote(wsl_path(DTS))} "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
cp {shlex.quote(wsl_path(DRIVER))} "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
grep -q '^#define QTN_TOPAZ_EMAC_RX_RING_COUNT[[:space:]]*256$' "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
grep -q '^#define QTN_TOPAZ_EMAC_NAPI_WEIGHT[[:space:]]*256$' "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
grep -q 'QTN_TOPAZ_EMAC_DMA_IRQ_RX_FAULTS' "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
cp {shlex.quote(wsl_path(source_config))} "$out/.config"
"$src/scripts/config" --file "$out/.config" --set-str INITRAMFS_SOURCE "" --set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_squashfs
make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j12 vmlinux uImage.bin dtbs > "$assets/kernel-build.log" 2>&1
cp "$out/.config" "$assets/kernel-squashfs.config"
cp "$out/vmlinux" "$assets/kernel-squashfs.vmlinux"
cp "$out/arch/arc/boot/uImage.bin" "$assets/kernel-squashfs.uncompressed.uImage"
cp "$out/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$assets/topaz_mitrastar_squashfs.dtb"
'''
    run_wsl(shell, distro)
    uimage = assets / "kernel-squashfs.uncompressed.uImage"
    raw = assets / "kernel-squashfs.raw.bin"
    raw.write_bytes(uimage.read_bytes()[64:])
    from build_f71_qcsapi_interp_from_f70 import encode_lzma_legacy
    (assets / "kernel-squashfs.lzma").write_bytes(encode_lzma_legacy(raw))


def verify_binary_contract(vmlinux: Path, distro: str) -> dict[str, object]:
    objdump = WS_ROOT + "/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-objdump"
    command = f'''"{objdump}" -dr {shlex.quote(wsl_path(vmlinux))} | sed -n -e '/<qtn_emac_probe>/,/^$/p' -e '/<qtn_emac_interrupt>/,/^$/p' -e '/<qtn_emac_irq_poll_work>/,/^$/p' '''
    text = run_wsl(command, distro, timeout=120)
    ring = [line for line in text.splitlines() if re.search(r"\b0x1400\b", line)]
    napi = [line for line in text.splitlines() if re.search(r"\b(?:0x100|256)\b", line)]
    rx_fault_mask = [line for line in text.splitlines() if re.search(r"\b0x1f1\b", line)]
    telemetry = (
        "rx_fault_observations=",
        "last_rx_fault_status=",
        "last_rx_fault_age_ms=",
        "rx_restart_last_dma_status=",
        "rx_restart_last_head_status=",
        "rx_restart_last_fault_age_ms=",
        "mac_rx_frames_valid=",
        "mac_rx_frames=",
        "mac_rx_frames_delta=",
        "mac_rx_progress_observations=",
        "mac_rx_progress_age_ms=",
        "mac_rx_read_failures=",
        "dma_missed_frames_total=",
        "rx_restart_last_mac_rx_frames=",
        "rx_restart_last_mac_rx_progress_age_ms=",
        "rx_restart_last_dma_missed_frames_total=",
    )
    if not ring:
        raise SystemExit("F293 binary contract missing 256-entry RX descriptor allocation")
    if not napi:
        raise SystemExit("F293 binary contract missing NAPI weight 256")
    if not rx_fault_mask:
        raise SystemExit("F293 binary contract missing RX fault pending mask 0x1f1")
    image = vmlinux.read_bytes()
    missing = [marker for marker in telemetry if marker.encode("ascii") not in image]
    if missing:
        raise SystemExit(f"F293 binary contract missing hardware RX-demand telemetry: {missing}")
    return {
        "schema": "openmitrastar.f293-emac-hw-rx-demand-binary-contract/v1",
        "result": "PASS",
        "rx_ring_descriptors": 256,
        "napi_weight": 256,
        "rx_pending_mask": "0x1f1",
        "hardware_rx_demand_telemetry": list(telemetry),
        "evidence": {"descriptor_allocation": ring[:2], "napi": napi[:3], "rx_fault_mask": rx_fault_mask[:3]},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="hgw500bna-qcv2-a2-primary")
    parser.add_argument("--identity-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--private-output-root", type=Path, default=Path.home() / ".openmitrastar/devices")
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--dropbearkey", default=DEFAULT_TOOL)
    parser.add_argument("--replace-existing", action="store_true")
    args = parser.parse_args()
    if not DEVICE_RE.fullmatch(args.device_id):
        raise SystemExit("invalid --device-id")

    source_text = DRIVER.read_text(encoding="utf-8")
    if "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t256" not in source_text:
        raise SystemExit("F293 requires the established 256-entry RX ring")
    if "#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t256" not in source_text:
        raise SystemExit("F293 requires the established NAPI weight 256")
    if source_text.count("QTN_TOPAZ_EMAC_DMA_IRQ_RX_FAULTS") < 5:
        raise SystemExit("F293 source is missing RX fault acknowledgement or NAPI scheduling")
    for marker in (
        "poll_last_rx_fault_jiffies",
        "poll_last_rx_fault_status",
        "rx_restart_last_dma_status",
        "rx_restart_last_head_status",
        "rx_restart_last_fault_age_ms",
        "qtn_emac_read_rx_stat",
        "poll_last_mac_rx_frames",
        "poll_mac_rx_progress_observations",
        "poll_dma_missed_frames_total",
        "rx_restart_last_mac_rx_progress_age_ms",
        "rx_restart_last_dma_missed_frames_total",
    ):
        if marker not in source_text:
            raise SystemExit(f"F293 source is missing telemetry field {marker}")

    private_root = args.private_output_root.resolve()
    firmware_root = private_root / args.device_id / "firmware"
    source = firmware_root / "f292-device-bound"
    source_base = f"openmitrastar-linux510-f292-{args.device_id}-PRIVATE-NO-FLASH"
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="ascii"))
    final_out = firmware_root / "f293-device-bound"
    if final_out.exists() and not args.replace_existing:
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")
    if final_out.exists():
        if final_out.name != "f293-device-bound" or final_out.parent != firmware_root:
            raise SystemExit(f"unsafe replacement target: {final_out}")
        shutil.rmtree(final_out)

    identity_dir = args.identity_root.resolve() / args.device_id
    identity = json.loads((identity_dir / "identity.json").read_text(encoding="utf-8"))
    key = identity_dir / "dropbear_ed25519_host_key"
    public_key = (identity_dir / identity["public_key_file"]).read_text(encoding="ascii").strip()
    if inspect_key(args.distro, args.dropbearkey, key) != identity["fingerprint"]:
        raise SystemExit("device identity mismatch")

    scratch = ROOT / ".codex_tmp" / f"f293-device-{args.device_id}"
    if scratch.exists():
        shutil.rmtree(scratch)

    def cleanup() -> None:
        if scratch.exists():
            shutil.rmtree(scratch)

    atexit.register(cleanup)
    source_build = scratch / "source-build"
    overlay = scratch / "foundation/overlay"
    assets = scratch / "assets"
    kernel_assets = scratch / "kernel-assets"
    output = scratch / "build"
    shutil.copytree(source, source_build)
    overlay.mkdir(parents=True, exist_ok=True)

    base = f"openmitrastar-linux510-f293-{args.device_id}-PRIVATE-NO-FLASH"
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS", "OUT", "BASE",
        "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA", "REMOVE_PATHS", "DISTRO",
    )
    old = {name: getattr(foundation, name) for name in names}
    old_rootfs_window = compose_engine.ROOTFS_WINDOW
    try:
        foundation.SOURCE_BUILD = source_build
        foundation.SOURCE_BASE = source_base
        foundation.FOUNDATION = overlay.parent
        foundation.OVERLAY = overlay
        foundation.ASSETS = assets
        foundation.OUT = output
        foundation.BASE = base
        foundation.PRODUCT_VERSION = "lyoko-foundation-6.5.1-f293-emac-hw-rx-demand-device"
        foundation.ASSETS_SCHEMA = "openmitrastar.f293-emac-hw-rx-demand-device-assets/v1"
        foundation.DIFF_SCHEMA = "openmitrastar.f293-emac-hw-rx-demand-device-rootfs-diff/v1"
        foundation.REMOVE_PATHS = ()
        foundation.DISTRO = args.distro
        compose_engine.ROOTFS_WINDOW = ROOTFS_WINDOW
        assets_report = foundation.prepare_assets()
        build_kernel(kernel_assets, source / f"{source_base}.config", args.distro)
        replacements = {
            "kernel-squashfs.uncompressed.uImage": ".uncompressed.uImage",
            "kernel-squashfs.raw.bin": ".kernel.raw.bin",
            "kernel-squashfs.lzma": ".kernel.lzma",
            "kernel-squashfs.config": ".config",
            "topaz_mitrastar_squashfs.dtb": ".dtb",
            "kernel-squashfs.vmlinux": ".vmlinux",
        }
        for asset_name in replacements:
            shutil.copy2(kernel_assets / asset_name, assets / asset_name)
        with foundation.variant_context():
            rc = foundation.engine.main()
    finally:
        compose_engine.ROOTFS_WINDOW = old_rootfs_window
        for name, value in old.items():
            setattr(foundation, name, value)
    if rc:
        raise SystemExit(rc)

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    rootfs = output / f"{base}.rootfs.squashfs"
    verify_embedded_key(rootfs, identity["fingerprint"], args.distro, args.dropbearkey, scratch)
    if set(assets_report["rootfs_diff"]["changed_paths"]) != {"etc/openmitrastar/release"}:
        raise SystemExit("F293 rootfs change is not release-identity-only")
    if sha256(output / f"{base}.kernel.lzma") == sha256(source / f"{source_base}.kernel.lzma"):
        raise SystemExit("F293 kernel did not change")
    for suffix in (".config", ".dtb"):
        if sha256(output / f"{base}{suffix}") != sha256(source / f"{source_base}{suffix}"):
            raise SystemExit(f"F293 unexpectedly changed {suffix}")
    binary_contract = verify_binary_contract(output / f"{base}.vmlinux", args.distro)
    candidate = output / manifest["artifacts"]["webformat"]["file"]
    candidate_data = candidate.read_bytes()
    full_slot = candidate_data + b"\xff" * (0x7A0000 - len(candidate_data))
    store_erased = all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F293 overlaps or initializes lyoko_store")

    manifest.update({
        "schema": "openmitrastar.f293-emac-hw-rx-demand-from-f292/v1",
        "classification": "PRIVATE_DEVICE_BOUND_HARDWARE_TEST_CANDIDATE",
        "candidate_eligible": True,
        "release_eligible": False,
        "flash_supported": True,
        "device_identity": source_manifest["device_identity"],
        "web_identity": source_manifest["web_identity"],
        "web_security": source_manifest["web_security"],
        "foundation_assets": assets_report,
        "native_qtn_control": source_manifest["native_qtn_control"],
        "native_rtl_control": source_manifest["native_rtl_control"],
        "config_apply": source_manifest["config_apply"],
        "transaction_hardening": source_manifest["transaction_hardening"],
        "dfs_observability": source_manifest["dfs_observability"],
        "network_observability": source_manifest["network_observability"],
        "hardware_provenance": source_manifest["hardware_provenance"],
        "package_catalog": source_manifest["package_catalog"],
        "package_runtime_fix": source_manifest["package_runtime_fix"],
        "opkg_compatibility": source_manifest["opkg_compatibility"],
        "led_control": source_manifest["led_control"],
        "config_store": source_manifest["config_store"],
        "transaction_review": source_manifest.get("transaction_review", {}),
        "package_web": source_manifest.get("package_web", {}),
        "hardware_inventory": source_manifest["hardware_inventory"],
        "developer_console": {
            **source_manifest["developer_console"],
            "firmware_line": "F293 Full",
        },
        "qtn_material_trial": source_manifest.get("qtn_material_trial", {}),
        "spi_probe": source_manifest["spi_probe"],
        "source": {
            "firmware": "F292 installed physical baseline",
            "kernel": "F290 physically tested datapath inherited by F292",
            "f292_manifest_sha256": sha256(source / "manifest.json"),
            "f290_evaluation": "outputs/f3-certification/f290-emac-restart-context-20260903/f290-evaluation.json",
            "f291_rejection": "outputs/f3-certification/f291-rejected-20260904/result.json",
        },
        "hypothesis": {
            "claim": "Sampling the Arasan MAC receive counter and DMA missed-frame counter during existing stall probes can distinguish real ingress demand from harmless idle without changing F290 recovery behavior.",
            "evidence": {
                "f290_restart_last_fault_status": "0x20",
                "f290_restart_last_fault_age_ms": 6150,
                "f290_restart_last_head_status": "0x80000000",
                "f291_failure": "Ethernet RX froze while Linux remained alive and no recovery fired",
            },
        },
        "change_scope": {
            "single_functional_variable": "add read-only Arasan MAC RX-demand and DMA missed-frame telemetry",
            "rx_ring": "unchanged at 256 descriptors",
            "napi_weight": "unchanged at 256",
            "tx_ring": "unchanged at 64 descriptors",
            "rx_buffer_size": "unchanged at 2048 bytes",
            "restart_policy": "decision conditions and recovery actions unchanged from F290; new counters do not gate recovery",
            "hardware_sampling": "FramesRxTotal and DMA missed frames sampled only during the existing 250 ms stall-poke path",
            "rootfs": "F292 rootfs with release identity updated only",
            "dtb": "byte-identical to F292",
            "radio_modules_firmware_web_packages": "byte-identical to F292",
        },
        "binary_contract": binary_contract,
        "physical_validation": {
            "status": "NOT_RUN",
            "improvement_claimed": False,
            "required": "capture hardware RX progress around a real 2.4 GHz stall, confirm F292-equivalent throughput and run 5 GHz sanity",
        },
        "storage": {
            **source_manifest["storage"],
            "store_erased_ff": store_erased,
            "candidate_ends_before_store": len(candidate_data) <= STORE_SLOT_OFFSET,
        },
        "safety": {
            "normal_write_target": "mtd4/linux_live only after explicit authorization",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "mtd6": "logical rootfs view; never a physical write target",
            "hardware_actions": "none",
        },
    })
    manifest["layout"]["mtd_mapping"] = source_manifest["layout"]["mtd_mapping"]
    manifest["contracts"]["hardware_boot"] = "NOT_RUN"
    manifest["contracts"]["flash"] = False
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )

    final_out.parent.mkdir(parents=True, exist_ok=True)
    restrict_acl(final_out.parent, directory=True)
    shutil.copytree(output, final_out)
    (final_out / "known_hosts.f293").write_text(f"192.168.1.90 {public_key}\n", encoding="ascii", newline="\n")
    restrict_acl(final_out, directory=True)
    for path in final_out.iterdir():
        if path.is_file():
            restrict_acl(path, directory=False)
    print(json.dumps({
        "status": "PASS",
        "output": str(final_out),
        "candidate": str(final_out / manifest["artifacts"]["webformat"]["file"]),
        "bytes": manifest["artifacts"]["webformat"]["bytes"],
        "sha256": manifest["artifacts"]["webformat"]["sha256"],
        "single_variable": manifest["change_scope"]["single_functional_variable"],
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }, indent=2))
    cleanup()
    atexit.unregister(cleanup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
