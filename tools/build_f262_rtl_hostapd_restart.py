#!/usr/bin/env python3
"""Build F262 from F261 with verified hostapd restart for RTL control."""
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
FOUNDATION_SOURCE = ROOT / "versions/lyoko-foundation-4.9.5-f262/overlay"
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

    device_dir = args.identity_root.resolve() / args.device_id
    identity = json.loads((device_dir / "identity.json").read_text(encoding="utf-8"))
    key = device_dir / "dropbear_ed25519_host_key"
    public_key = (device_dir / identity["public_key_file"]).read_text(encoding="ascii").strip()
    if inspect_key(args.distro, args.dropbearkey, key) != identity["fingerprint"]:
        raise SystemExit("device identity mismatch")

    private_root = args.private_output_root.resolve()
    source = private_root / args.device_id / "firmware/f261-device-bound"
    source_base = f"openmitrastar-linux510-f261-{args.device_id}-PRIVATE-NO-FLASH"
    source_manifest = json.loads((source / "manifest.json").read_text(encoding="ascii"))
    final_out = private_root / args.device_id / "firmware/f262-device-bound"
    if final_out.exists() and not args.replace_existing:
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")
    if final_out.exists():
        if final_out.name != "f262-device-bound" or final_out.parent != private_root / args.device_id / "firmware":
            raise SystemExit(f"unsafe replacement target: {final_out}")
        shutil.rmtree(final_out)

    scratch = ROOT / ".codex_tmp" / f"f262-device-{args.device_id}"
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

    copies = (
        ("etc/lyoko/frontend.env", "etc/lyoko/frontend.env", 0o644),
        ("usr/sbin/om-radioctl", "usr/sbin/om-radioctl", 0o755),
        ("usr/sbin/om-rtlctl", "usr/sbin/om-rtlctl", 0o755),
    )
    for source_name, target_name, mode in copies:
        copy_file(FOUNDATION_SOURCE / source_name, overlay / target_name, mode)

    base = f"openmitrastar-linux510-f262-{args.device_id}-PRIVATE-NO-FLASH"
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS", "OUT", "BASE",
        "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA", "REMOVE_PATHS",
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
        engine.PRODUCT_VERSION = "lyoko-foundation-4.9.5-f262-device"
        engine.ASSETS_SCHEMA = "openmitrastar.f262-device-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f262-device-rootfs-diff/v1"
        engine.REMOVE_PATHS = ()
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
    candidate = output / manifest["artifacts"]["webformat"]["file"]
    candidate_data = candidate.read_bytes()
    full_slot = candidate_data + b"\xff" * (0x7A0000 - len(candidate_data))
    store_erased = all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F262 candidate overlaps or initializes lyoko_store")

    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    expected = {"etc/openmitrastar/release"} | {target for _, target, _ in copies}
    if changed != expected:
        raise SystemExit(f"F262 changed unexpected rootfs paths: {sorted(changed)}")
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        if sha256(source / f"{source_base}{suffix}") != sha256(output / f"{base}{suffix}"):
            raise SystemExit(f"F262 unexpectedly changed {suffix}")

    manifest.update({
        "schema": "openmitrastar.f262-rtl-hostapd-restart/v1",
        "classification": "PRIVATE_DEVICE_BOUND_HARDWARE_TEST_CANDIDATE",
        "candidate_eligible": True,
        "release_eligible": False,
        "flash_supported": True,
        "device_identity": source_manifest["device_identity"],
        "web_identity": source_manifest["web_identity"],
        "web_security": source_manifest["web_security"],
        "source": {
            "firmware": "F261",
            "reason": "restart hostapd so Realtek channel and bandwidth changes reach the physical radio",
        },
        "native_qtn_control": source_manifest["native_qtn_control"],
        "native_rtl_control": {**source_manifest["native_rtl_control"], "backend": "nl80211-hostapd-restart"},
        "config_apply": source_manifest["config_apply"],
        "transaction_hardening": source_manifest["transaction_hardening"],
        "dfs_observability": source_manifest["dfs_observability"],
        "network_observability": source_manifest["network_observability"],
        "hardware_provenance": {
            **source_manifest["hardware_provenance"],
        },
        "package_catalog": source_manifest["package_catalog"],
        "package_runtime_fix": source_manifest["package_runtime_fix"],
        "hardware_inventory": source_manifest["hardware_inventory"],
        "change_scope": {
            "rootfs_paths": sorted(changed),
            "kernel_config_dtb": "byte-identical to F261/F260/F259/F258/F247/F223",
            "qdrv_wlan_firmware": "byte-identical to F261/F260/F259/F258/F247/F222",
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "dual-radio stage/apply/rollback physical gate and package regression",
        },
        "storage": {
            **source_manifest["storage"],
            "store_erased_ff": store_erased,
            "candidate_ends_before_store": len(candidate_data) <= STORE_SLOT_OFFSET,
        },
        "spi_probe": source_manifest["spi_probe"],
    })
    manifest["layout"]["mtd_mapping"] = source_manifest["layout"]["mtd_mapping"]
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text("".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii")

    final_out.parent.mkdir(parents=True, exist_ok=True)
    restrict_acl(final_out.parent, directory=True)
    shutil.copytree(output, final_out)
    (final_out / "known_hosts.f262").write_text(f"192.168.1.90 {public_key}\n", encoding="ascii", newline="\n")
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
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }, indent=2))
    cleanup()
    atexit.unregister(cleanup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
