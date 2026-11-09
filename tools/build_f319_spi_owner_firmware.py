#!/usr/bin/env python3
"""Package the F319 claim-only SPI owner probe over exact installed F314."""

from __future__ import annotations

import argparse
import atexit
import hashlib
import json
from pathlib import Path
import shutil

import build_f170_lyoko_foundation_runtime_fix as engine
import compose_f164_squashfs_product as compose_engine
from build_f196_device_personalized import verify_embedded_key
from init_lyoko_device_host_key import DEFAULT_ROOT, DEFAULT_TOOL, DEVICE_RE, inspect_key, restrict_acl


ROOT = Path(__file__).resolve().parents[1]
MODULE_OUT = ROOT / "outputs/kernel-port/f319-spi-owner-probe-20260905"
EXPECTED_F314_SHA256 = "a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11"
ROOTFS_WINDOW = 0x460000
STORE_SLOT_OFFSET = 0x5E0000
STORE_SIZE = 0x1C0000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_file(source: Path, destination: Path, mode: int) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    destination.chmod(mode)


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

    module_manifest = json.loads((MODULE_OUT / "manifest.json").read_text(encoding="ascii"))
    if module_manifest.get("status") != "PASS" or module_manifest.get("physical_validation") != "NOT_RUN":
        raise SystemExit("F319 claim-only module is not an offline PASS artifact")
    module = MODULE_OUT / module_manifest["artifact"]["file"]
    if sha256(module) != module_manifest["artifact"]["sha256"]:
        raise SystemExit("F319 module hash mismatch")

    identity_dir = args.identity_root.resolve() / args.device_id
    identity = json.loads((identity_dir / "identity.json").read_text(encoding="utf-8"))
    key = identity_dir / "dropbear_ed25519_host_key"
    public_key = (identity_dir / identity["public_key_file"]).read_text(encoding="ascii").strip()
    if inspect_key(args.distro, args.dropbearkey, key) != identity["fingerprint"]:
        raise SystemExit("device identity mismatch")

    private_root = args.private_output_root.resolve()
    firmware_root = private_root / args.device_id / "firmware"
    source = firmware_root / "f314-device-bound"
    source_base = f"openmitrastar-linux510-f314-{args.device_id}-PRIVATE-NO-FLASH"
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="ascii"))
    if source_manifest["artifacts"]["webformat"]["sha256"] != EXPECTED_F314_SHA256:
        raise SystemExit("F319 source is not the exact installed F314 candidate")

    final_out = firmware_root / "f319-device-bound"
    if final_out.exists() and not args.replace_existing:
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")
    if final_out.exists():
        if final_out.name != "f319-device-bound" or final_out.parent != firmware_root:
            raise SystemExit(f"unsafe replacement target: {final_out}")
        shutil.rmtree(final_out)

    scratch = ROOT / ".codex_tmp" / f"f319-device-{args.device_id}"
    if scratch.exists():
        shutil.rmtree(scratch)

    def cleanup() -> None:
        if scratch.exists():
            shutil.rmtree(scratch)

    atexit.register(cleanup)
    source_build = scratch / "source-build"
    foundation = scratch / "foundation"
    overlay = foundation / "overlay"
    assets = scratch / "assets"
    output = scratch / "build"
    shutil.copytree(source, source_build)

    module_target = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-spi-owner-probe.ko"
    feature_target = "etc/openmitrastar/features/spi-owner-probe-v1"
    copy_file(module, overlay / module_target, 0o644)
    feature = overlay / feature_target
    feature.parent.mkdir(parents=True, exist_ok=True)
    feature.write_text(
        "OPENMITRASTAR_SPI_OWNER_MODE=claim-only\n"
        "OPENMITRASTAR_SPI_OWNER_AUTOLOAD=0\n"
        "OPENMITRASTAR_SPI_OWNER_MMIO_READS=0\n"
        "OPENMITRASTAR_SPI_OWNER_MMIO_WRITES=0\n"
        "OPENMITRASTAR_SPI_OWNER_PROVIDER_READY=0\n",
        encoding="ascii",
        newline="\n",
    )
    feature.chmod(0o644)

    base = f"openmitrastar-linux510-f319-{args.device_id}-PRIVATE-NO-FLASH"
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS", "OUT", "BASE",
        "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA", "REMOVE_PATHS", "DISTRO",
    )
    old = {name: getattr(engine, name) for name in names}
    old_rootfs_window = compose_engine.ROOTFS_WINDOW
    try:
        engine.SOURCE_BUILD = source_build
        engine.SOURCE_BASE = source_base
        engine.FOUNDATION = foundation
        engine.OVERLAY = overlay
        engine.ASSETS = assets
        engine.OUT = output
        engine.BASE = base
        engine.PRODUCT_VERSION = "lyoko-foundation-6.8.3-f319-spi-owner-claim-device"
        engine.ASSETS_SCHEMA = "openmitrastar.f319-spi-owner-claim-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f319-spi-owner-claim-rootfs-diff/v1"
        engine.REMOVE_PATHS = ()
        engine.DISTRO = args.distro
        compose_engine.ROOTFS_WINDOW = ROOTFS_WINDOW
        rc = engine.main()
    finally:
        compose_engine.ROOTFS_WINDOW = old_rootfs_window
        for name, value in old.items():
            setattr(engine, name, value)
    if rc:
        raise SystemExit(rc)

    manifest_path = output / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    rootfs = output / f"{base}.rootfs.squashfs"
    verify_embedded_key(rootfs, identity["fingerprint"], args.distro, args.dropbearkey, scratch)
    for suffix in (".uncompressed.uImage", ".kernel.raw.bin", ".kernel.lzma", ".config", ".dtb", ".vmlinux"):
        if sha256(source / f"{source_base}{suffix}") != sha256(output / f"{base}{suffix}"):
            raise SystemExit(f"F319 unexpectedly changed kernel artifact: {suffix}")

    candidate = output / manifest["artifacts"]["webformat"]["file"]
    candidate_data = candidate.read_bytes()
    full_slot = candidate_data + b"\xff" * (0x7A0000 - len(candidate_data))
    store_erased = all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F319 overlaps or initializes lyoko_store")

    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    required = {"etc/openmitrastar/release", module_target, feature_target}
    if not required.issubset(changed):
        raise SystemExit(f"F319 missing expected rootfs paths: {sorted(required - changed)}")

    manifest.update({
        "schema": "openmitrastar.f319-spi-owner-claim-candidate/v1",
        "classification": "PRIVATE_DEVICE_BOUND_MTD4_SPI_OWNER_DIAGNOSTIC_CANDIDATE",
        "candidate_eligible": True,
        "release_eligible": False,
        "flash_supported": True,
        "device_identity": source_manifest["device_identity"],
        "web_identity": source_manifest["web_identity"],
        "web_security": source_manifest["web_security"],
        "source": {
            "firmware": "exact installed F314",
            "base_candidate_sha256": EXPECTED_F314_SHA256,
            "module_manifest_sha256": sha256(MODULE_OUT / "manifest.json"),
        },
        "spi_owner_probe": {
            **module_manifest["contract"],
            "module": "/" + module_target,
            "module_sha256": module_manifest["artifact"]["sha256"],
            "hardware_status": "NOT_LOADED",
        },
        "change_scope": {
            "kernel_dtb_radio": "byte-identical to installed F314",
            "rootfs_additions": [module_target, feature_target],
            "autoload": False,
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "versioned mtd4 boot, UART capture, claim/map readback, zero MMIO access counters, unload, dual-radio regression",
        },
        "storage": {
            **source_manifest["storage"],
            "store_erased_ff": store_erased,
            "candidate_ends_before_store": len(candidate_data) <= STORE_SLOT_OFFSET,
            "persistent_writes_enabled": False,
        },
        "safety": {
            "normal_write_target": "mtd4/linux_live only after explicit authorization",
            "protected_partitions": "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged",
            "mtd6": "logical rootfs view; never a physical write target",
            "hardware_actions": "none",
        },
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )

    final_out.parent.mkdir(parents=True, exist_ok=True)
    restrict_acl(final_out.parent, directory=True)
    shutil.copytree(output, final_out)
    (final_out / "known_hosts.f319").write_text(f"192.168.1.90 {public_key}\n", encoding="ascii", newline="\n")
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
        "candidate_eligible": True,
        "hardware_actions": {"router": False, "uart": False, "flash": False, "mtd": False},
    }, indent=2))
    cleanup()
    atexit.unregister(cleanup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
