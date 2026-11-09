#!/usr/bin/env python3
"""Compose private F244 from the F223 kernel and F243 rootfs."""
from __future__ import annotations

import argparse
import atexit
import contextlib
import hashlib
import json
from pathlib import Path
import shutil

import compose_f164_squashfs_product as compose
from build_f196_device_personalized import verify_embedded_key
from init_lyoko_device_host_key import DEFAULT_ROOT, DEFAULT_TOOL, DEVICE_RE, inspect_key, restrict_acl


ROOT = Path(__file__).resolve().parents[1]
ROOTFS_WINDOW = 0x460000
STORE_SLOT_OFFSET = 0x5E0000
STORE_SIZE = 0x1C0000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextlib.contextmanager
def compose_context(assets: Path, output: Path, base: str):
    names = ("ASSETS", "OUT", "BASE", "ROOTFS_WINDOW")
    old = {name: getattr(compose, name) for name in names}
    try:
        compose.ASSETS = assets
        compose.OUT = output
        compose.BASE = base
        compose.ROOTFS_WINDOW = ROOTFS_WINDOW
        yield
    finally:
        for name, value in old.items():
            setattr(compose, name, value)


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

    private_root = args.private_output_root.resolve()
    firmware_root = private_root / args.device_id / "firmware"
    f223 = firmware_root / "f223-device-bound"
    f243 = firmware_root / "f243-device-bound"
    f223_base = f"openmitrastar-linux510-f223-{args.device_id}-PRIVATE-NO-FLASH"
    f243_base = f"openmitrastar-linux510-f243-{args.device_id}-PRIVATE-NO-FLASH"
    f223_manifest = json.loads((f223 / "manifest.json").read_text(encoding="ascii"))
    f243_manifest = json.loads((f243 / "manifest.json").read_text(encoding="ascii"))

    device_dir = args.identity_root.resolve() / args.device_id
    identity = json.loads((device_dir / "identity.json").read_text(encoding="utf-8"))
    key = device_dir / "dropbear_ed25519_host_key"
    public_key = (device_dir / identity["public_key_file"]).read_text(encoding="ascii").strip()
    if inspect_key(args.distro, args.dropbearkey, key) != identity["fingerprint"]:
        raise SystemExit("device identity mismatch")

    final_out = firmware_root / "f244-device-bound"
    if final_out.exists() and not args.replace_existing:
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")
    if final_out.exists():
        if final_out.name != "f244-device-bound" or final_out.parent != firmware_root:
            raise SystemExit(f"unsafe replacement target: {final_out}")
        shutil.rmtree(final_out)
    scratch = ROOT / ".codex_tmp" / f"f244-device-{args.device_id}"
    if scratch.exists():
        shutil.rmtree(scratch)

    def cleanup() -> None:
        if scratch.exists():
            shutil.rmtree(scratch)

    atexit.register(cleanup)
    assets = scratch / "assets"
    output = scratch / "build"
    assets.mkdir(parents=True, exist_ok=True)
    copies = {
        f223 / f"{f223_base}.uncompressed.uImage": assets / "kernel-squashfs.uncompressed.uImage",
        f223 / f"{f223_base}.kernel.raw.bin": assets / "kernel-squashfs.raw.bin",
        f223 / f"{f223_base}.kernel.lzma": assets / "kernel-squashfs.lzma",
        f223 / f"{f223_base}.config": assets / "kernel-squashfs.config",
        f223 / f"{f223_base}.dtb": assets / "topaz_mitrastar_squashfs.dtb",
        f223 / f"{f223_base}.vmlinux": assets / "kernel-squashfs.vmlinux",
        f243 / f"{f243_base}.rootfs.squashfs": assets / "rootfs-product-xz-128k.squashfs",
    }
    for source, target in copies.items():
        if not source.is_file():
            raise SystemExit(f"missing F244 input: {source}")
        shutil.copy2(source, target)

    base = f"openmitrastar-linux510-f244-{args.device_id}-PRIVATE-NO-FLASH"
    with compose_context(assets, output, base):
        if compose.main():
            raise SystemExit("F244 image composition failed")

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    rootfs = output / f"{base}.rootfs.squashfs"
    verify_embedded_key(rootfs, identity["fingerprint"], args.distro, args.dropbearkey, scratch)
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        if sha256(output / f"{base}{suffix}") != sha256(f223 / f"{f223_base}{suffix}"):
            raise SystemExit(f"F244 kernel-side artifact differs from F223: {suffix}")
    if sha256(rootfs) != sha256(f243 / f"{f243_base}.rootfs.squashfs"):
        raise SystemExit("F244 rootfs differs from F243")

    candidate = output / manifest["artifacts"]["webformat"]["file"]
    candidate_data = candidate.read_bytes()
    full_slot = candidate_data + b"\xff" * (0x7A0000 - len(candidate_data))
    store_erased = all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F244 candidate overlaps or initializes lyoko_store")

    manifest.update({
        "schema": "openmitrastar.f244-integrated-rxring-hardware-provenance/v1",
        "classification": "PRIVATE_DEVICE_BOUND_INTEGRATION_HOLD_DO_NOT_FLASH",
        "candidate_eligible": False,
        "release_eligible": False,
        "flash_supported": False,
        "device_identity": f243_manifest["device_identity"],
        "web_identity": f243_manifest["web_identity"],
        "web_security": f243_manifest["web_security"],
        "source": {
            "kernel": "F223 EMAC RX ring 256",
            "rootfs": "F243 Foundation 4.8 hardware provenance",
            "f223_kernel_sha256": f223_manifest["artifacts"]["kernel_lzma"]["sha256"],
            "f243_rootfs_sha256": f243_manifest["artifacts"]["rootfs_squashfs"]["sha256"],
        },
        "integration": {
            "kernel_contract": f223_manifest["binary_contract"],
            "native_qtn_control": f243_manifest["native_qtn_control"],
            "native_rtl_control": f243_manifest["native_rtl_control"],
            "config_apply": f243_manifest["config_apply"],
            "transaction_hardening": f243_manifest["transaction_hardening"],
            "dfs_observability": f243_manifest["dfs_observability"],
            "network_observability": f243_manifest["network_observability"],
            "hardware_provenance": f243_manifest["hardware_provenance"],
            "transaction_review": f243_manifest.get("transaction_review", {}),
            "package_web": f243_manifest.get("package_web", {}),
            "hardware_inventory": f243_manifest["hardware_inventory"],
            "additional_changes": [],
        },
        "promotion_blockers": [
            "F223 three-run physical 2.4 GHz campaign has not passed",
            "F237 hardened controls plus F239/F241/F243 observability have not run on hardware",
        ],
        "physical_validation": {
            "status": "NOT_RUN",
            "improvement_claimed": False,
            "required": "pass F223 physical campaign, then run integrated boot, radio contract, package API, hardware UI and dual-radio gates",
        },
        "storage": {
            **f243_manifest["storage"],
            "store_erased_ff": store_erased,
            "candidate_ends_before_store": len(candidate_data) <= STORE_SLOT_OFFSET,
        },
        "spi_probe": f243_manifest["spi_probe"],
        "safety": {
            "normal_write_target": "mtd4/linux_live only",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "mtd6": "logical rootfs view; never a physical write target",
            "hardware_actions": "none",
        },
    })
    manifest["layout"]["mtd_mapping"] = f243_manifest["layout"]["mtd_mapping"]
    manifest["contracts"]["hardware_boot"] = "NOT_RUN"
    manifest["contracts"]["flash"] = False
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")

    final_out.parent.mkdir(parents=True, exist_ok=True)
    restrict_acl(final_out.parent, directory=True)
    shutil.copytree(output, final_out)
    (final_out / "known_hosts.f244").write_text(f"192.168.1.90 {public_key}\n", encoding="ascii", newline="\n")
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
        "candidate_eligible": False,
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }, indent=2))
    cleanup()
    atexit.unregister(cleanup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
