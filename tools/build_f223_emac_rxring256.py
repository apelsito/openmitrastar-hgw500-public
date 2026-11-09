#!/usr/bin/env python3
"""Build private F223 from F222 with only the EMAC RX ring doubled."""
from __future__ import annotations

import argparse
import atexit
import contextlib
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess

import compose_f164_squashfs_product as compose
import build_f71_qcsapi_interp_from_f70 as f71
from init_lyoko_device_host_key import DEFAULT_ROOT, DEFAULT_TOOL, DEVICE_RE, inspect_key, restrict_acl


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
ROOTFS_WINDOW = 0x460000
STORE_SLOT_OFFSET = 0x5E0000
STORE_SIZE = 0x1C0000
WS_ROOT = "/workspace/user-home/Desktop/MitraStar"
KERNEL_SRC = "/home/user/mitrastar-linux-5.10.260"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_storage_probe.dts"
PHYSMAP = ROOT / "work/kernel-port/linux-5.10/drivers/mtd/maps/physmap-core.c"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wsl_path(path: Path) -> str:
    value = path.resolve().as_posix()
    drive, tail = value.split(":/", 1)
    return f"/mnt/{drive.lower()}/{tail}"


def run_wsl(script: str, distro: str, timeout: int = 900) -> None:
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
    if proc.stdout:
        print(proc.stdout, end="")


def build_kernel(assets: Path, source_config: Path, distro: str) -> None:
    kernel_out = "/home/user/openmitrastar-build/f223-emac-rxring256"
    canonical_dts = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
    shell = f"""
set -eu
src={shlex.quote(KERNEL_SRC)}
out={shlex.quote(kernel_out)}
assets={shlex.quote(wsl_path(assets))}
tc={shlex.quote(WS_ROOT + '/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-')}
restore={shlex.quote(wsl_path(canonical_dts))}
trap 'cp "$restore" "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"' EXIT HUP INT TERM
rm -rf "$out"
mkdir -p "$out" "$assets"
cp {shlex.quote(wsl_path(DTS))} "$src/arch/arc/boot/dts/topaz_mitrastar_squashfs.dts"
cp {shlex.quote(wsl_path(DRIVER))} "$src/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
cp {shlex.quote(wsl_path(PHYSMAP))} "$src/drivers/mtd/maps/physmap-core.c"
cp {shlex.quote(wsl_path(source_config))} "$out/.config"
"$src/scripts/config" --file "$out/.config" --set-str INITRAMFS_SOURCE "" --set-str ARC_BUILTIN_DTB_NAME topaz_mitrastar_squashfs
make -s -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" olddefconfig
SOURCE_DATE_EPOCH=1785024000 KBUILD_BUILD_TIMESTAMP=@1785024000 KBUILD_BUILD_USER=openmitrastar KBUILD_BUILD_HOST=builder KBUILD_BUILD_VERSION=1 make -C "$src" O="$out" ARCH=arc CROSS_COMPILE="$tc" -j12 vmlinux uImage.bin dtbs > "$assets/kernel-build.log" 2>&1
cp "$out/.config" "$assets/kernel-squashfs.config"
cp "$out/vmlinux" "$assets/kernel-squashfs.vmlinux"
cp "$out/arch/arc/boot/uImage.bin" "$assets/kernel-squashfs.uncompressed.uImage"
cp "$out/arch/arc/boot/dts/topaz_mitrastar_squashfs.dtb" "$assets/topaz_mitrastar_squashfs.dtb"
"""
    run_wsl(shell, distro)
    uimage = assets / "kernel-squashfs.uncompressed.uImage"
    raw = assets / "kernel-squashfs.raw.bin"
    raw.write_bytes(uimage.read_bytes()[64:])
    (assets / "kernel-squashfs.lzma").write_bytes(f71.encode_lzma_legacy(raw))


def verify_binary_contract(vmlinux: Path, distro: str) -> dict[str, object]:
    vmlinux_wsl = "/mnt/c/" + vmlinux.as_posix().split(":/", 1)[1]
    objdump = "/workspace/user-home/Desktop/MitraStar/work/toolchains/arc-uclibc/arc-arc700-linux-uclibc/bin/arc-linux-objdump"
    command = f'"{objdump}" -dr "{vmlinux_wsl}" | sed -n "/<qtn_emac_probe>/,/^$/p"'
    proc = subprocess.run(
        ["wsl.exe", "-d", distro, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        timeout=120,
    )
    if proc.returncode:
        raise SystemExit(proc.stderr or proc.stdout)
    lines = proc.stdout.splitlines()
    ring_size = [line for line in lines if re.search(r"\b0x1400\b", line)]
    napi = [line for line in lines if re.search(r"\bmov_s\s+r3,0x80\b", line)]
    rx_log = [line for line in lines if re.search(r"\bmov\s+r5,0x1000\b", line)]
    if not ring_size:
        raise SystemExit("F223 binary contract missing 0x1400 descriptor allocation")
    if not napi:
        raise SystemExit("F223 binary contract missing NAPI weight 0x80")
    if not rx_log:
        raise SystemExit("F223 binary contract missing 0x1000 RX descriptor bytes")
    return {
        "schema": "openmitrastar.f223-rxring-binary-contract/v1",
        "result": "PASS",
        "rx_ring_descriptors": 256,
        "rx_descriptor_bytes": 4096,
        "total_descriptor_bytes": 5120,
        "napi_weight": 128,
        "evidence": {"descriptor_allocation": ring_size[:2], "napi": napi[:2], "rx_bytes": rx_log[:2]},
    }


@contextlib.contextmanager
def engine_context(assets: Path, output: Path, base: str):
    compose_old = {"ASSETS": compose.ASSETS, "OUT": compose.OUT, "BASE": compose.BASE, "ROOTFS_WINDOW": compose.ROOTFS_WINDOW}
    try:
        compose.ASSETS = assets
        compose.OUT = output
        compose.BASE = base
        compose.ROOTFS_WINDOW = ROOTFS_WINDOW
        yield
    finally:
        for name, value in compose_old.items():
            setattr(compose, name, value)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device-id", default="hgw500bna-qcv2-a2-primary")
    parser.add_argument("--identity-root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--private-output-root", type=Path, default=Path.home() / ".openmitrastar/devices")
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--dropbearkey", default=DEFAULT_TOOL)
    args = parser.parse_args()
    if not DEVICE_RE.fullmatch(args.device_id):
        raise SystemExit("invalid --device-id")

    source_text = DRIVER.read_text(encoding="utf-8")
    if "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t256" not in source_text:
        raise SystemExit("driver is not configured for a 256-entry RX ring")
    if "#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t128" not in source_text:
        raise SystemExit("F223 must retain NAPI weight 128")

    private_root = args.private_output_root.resolve()
    source = private_root / args.device_id / "firmware/f222-device-bound"
    source_base = f"openmitrastar-linux510-f222-{args.device_id}-PRIVATE-NO-FLASH"
    source_manifest_path = source / "manifest.json"
    source_manifest = json.loads(source_manifest_path.read_text(encoding="ascii"))
    source_rootfs = source / f"{source_base}.rootfs.squashfs"
    source_kernel = source / f"{source_base}.kernel.lzma"
    source_config = source / f"{source_base}.config"
    source_dtb = source / f"{source_base}.dtb"
    final_out = private_root / args.device_id / "firmware/f223-device-bound"
    if final_out.exists():
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")

    identity_dir = args.identity_root.resolve() / args.device_id
    identity = json.loads((identity_dir / "identity.json").read_text(encoding="utf-8"))
    key = identity_dir / "dropbear_ed25519_host_key"
    if inspect_key(args.distro, args.dropbearkey, key) != identity["fingerprint"]:
        raise SystemExit("device identity mismatch")

    scratch = ROOT / ".codex_tmp" / f"f223-rxring256-{args.device_id}"
    if scratch.exists():
        shutil.rmtree(scratch)
    assets = scratch / "assets"
    output = scratch / "build"
    base = f"openmitrastar-linux510-f223-{args.device_id}-PRIVATE-NO-FLASH"

    def cleanup() -> None:
        if scratch.exists():
            shutil.rmtree(scratch)

    atexit.register(cleanup)
    assets.mkdir(parents=True, exist_ok=True)
    build_kernel(assets, source_config, args.distro)
    shutil.copy2(source_rootfs, assets / "rootfs-product-xz-128k.squashfs")
    with engine_context(assets, output, base):
        if compose.main():
            raise SystemExit("F223 image composition failed")

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    output_rootfs = output / f"{base}.rootfs.squashfs"
    output_kernel = output / f"{base}.kernel.lzma"
    output_vmlinux = output / f"{base}.vmlinux"
    output_config = output / f"{base}.config"
    output_dtb = output / f"{base}.dtb"
    if sha256(output_rootfs) != sha256(source_rootfs):
        raise SystemExit("F223 rootfs differs from F222")
    if sha256(output_kernel) == sha256(source_kernel):
        raise SystemExit("F223 kernel did not change")
    if sha256(output_config) != sha256(source_config):
        raise SystemExit("F223 kernel config differs from F222")
    if sha256(output_dtb) != sha256(source_dtb):
        raise SystemExit("F223 DTB differs from F222")
    binary_contract = verify_binary_contract(output_vmlinux, args.distro)

    candidate = output / manifest["artifacts"]["webformat"]["file"]
    candidate_data = candidate.read_bytes()
    full_slot = candidate_data + b"\xff" * (0x7A0000 - len(candidate_data))
    if len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F223 candidate overlaps lyoko_store")
    if not all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE]):
        raise SystemExit("F223 initializes lyoko_store")

    added_payload_bytes = 128 * 2048
    added_descriptor_bytes = 128 * 16
    added_metadata_bytes = 128 * 12
    manifest.update({
        "schema": "openmitrastar.f223-emac-rxring256-from-f222/v1",
        "classification": "PRIVATE_DEVICE_BOUND_FIRMWARE_DO_NOT_DISTRIBUTE",
        "candidate_eligible": True,
        "release_eligible": False,
        "flash_supported": True,
        "device_identity": source_manifest["device_identity"],
        "web_identity": source_manifest["web_identity"],
        "web_security": source_manifest["web_security"],
        "source": {
            "firmware": "F222 installed persistent baseline",
            "manifest_sha256": sha256(source_manifest_path),
            "rootfs_sha256": sha256(source_rootfs),
            "kernel_lzma_sha256": sha256(source_kernel),
        },
        "hypothesis": {
            "claim": "A 256-entry RX ring absorbs short EMAC bursts that currently trigger intermittent NO_RX_DESC pressure before NAPI-128 can recycle descriptors.",
            "evidence": "F219 three-run physical campaign: NO_RX_DESC samples 925/609/0 and RX restarts 3/2/0 while MCS15 remained negotiated.",
        },
        "change_scope": {
            "single_variable": "qtn-topaz-emac RX ring 128 -> 256 descriptors",
            "napi_weight": "unchanged at 128",
            "rx_buffer_size": "unchanged at 2048 bytes",
            "tx_ring": "unchanged at 64 descriptors",
            "restart_policy": "unchanged",
            "rootfs": "byte-identical to installed F222",
            "kernel_config": "byte-identical to installed F222",
            "dtb": "byte-identical to installed F222",
            "radios_tqe_bridge_security_packages": "byte-identical to installed F222",
            "estimated_added_memory": {
                "payload_bytes": added_payload_bytes,
                "descriptor_bytes": added_descriptor_bytes,
                "buffer_metadata_bytes": added_metadata_bytes,
                "subtotal_before_skb_allocator_overhead": added_payload_bytes + added_descriptor_bytes + added_metadata_bytes,
            },
        },
        "binary_contract": binary_contract,
        "physical_validation": {
            "status": "NOT_RUN",
            "improvement_claimed": False,
            "required": "three matched 32 MiB 2.4 GHz down/up runs plus dual-radio sanity; compare throughput, latency, NO_RX_DESC, NAPI exhaustion and RX restarts against F222/F219 baseline",
        },
        "storage": {
            **source_manifest["storage"],
            "store_erased_ff": True,
            "candidate_ends_before_store": True,
        },
        "spi_probe": source_manifest["spi_probe"],
        "safety": {
            "write_target_if_promoted": "mtd4/linux_live only after explicit authorization",
            "rollback": "installed F222 artifact plus preserved boot path",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "mtd6": "logical rootfs view; never a physical write target",
            "offline_builder_hardware_actions": "none",
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
    public_key = (identity_dir / identity["public_key_file"]).read_text(encoding="ascii").strip()
    (final_out / "known_hosts.f223").write_text(f"192.168.1.90 {public_key}\n", encoding="ascii", newline="\n")
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
        "single_variable": manifest["change_scope"]["single_variable"],
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }, indent=2))
    cleanup()
    atexit.unregister(cleanup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
