#!/usr/bin/env python3
"""Build private F221 from F220 with the BusyBox multicall dispatcher."""
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
PKGBOX_DIR = ROOT / "outputs/packages/lyoko-pkgbox"
PKGBOX = PKGBOX_DIR / "lyoko-pkgbox"
PKGBOX_MANIFEST = PKGBOX_DIR / "manifest.json"
ROOTFS_WINDOW = 0x460000
STORE_SLOT_OFFSET = 0x5E0000
STORE_SIZE = 0x1C0000


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


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

    pkgbox_manifest = json.loads(PKGBOX_MANIFEST.read_text(encoding="ascii"))
    if "wc" not in pkgbox_manifest.get("required_applets", []):
        raise SystemExit("pkgbox manifest lacks wc")
    if sha256(PKGBOX) != pkgbox_manifest.get("sha256"):
        raise SystemExit("pkgbox hash mismatch")

    device_dir = args.identity_root.resolve() / args.device_id
    identity = json.loads((device_dir / "identity.json").read_text(encoding="utf-8"))
    key = device_dir / "dropbear_ed25519_host_key"
    public_key = (device_dir / identity["public_key_file"]).read_text(encoding="ascii").strip()
    fingerprint = inspect_key(args.distro, args.dropbearkey, key)
    if fingerprint != identity["fingerprint"]:
        raise SystemExit("device identity mismatch")

    private_root = args.private_output_root.resolve()
    private_source = private_root / args.device_id / "firmware/f220-device-bound"
    source_base = f"openmitrastar-linux510-f220-{args.device_id}-PRIVATE-NO-FLASH"
    source_manifest = json.loads((private_source / "manifest.json").read_text(encoding="ascii"))
    final_out = private_root / args.device_id / "firmware/f221-device-bound"
    if final_out.exists():
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")

    scratch = ROOT / ".codex_tmp" / f"f221-device-{args.device_id}"
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
    shutil.copytree(private_source, source_build)
    target_pkgbox = overlay / "usr/libexec/lyoko/pkgbox"
    target_pkgbox.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PKGBOX, target_pkgbox)

    base = f"openmitrastar-linux510-f221-{args.device_id}-PRIVATE-NO-FLASH"
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
        engine.PRODUCT_VERSION = "lyoko-foundation-3.6-f221-device"
        engine.ASSETS_SCHEMA = "openmitrastar.f221-device-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f221-device-rootfs-diff/v1"
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
    verify_embedded_key(rootfs, fingerprint, args.distro, args.dropbearkey, scratch)
    candidate = output / manifest["artifacts"]["webformat"]["file"]
    candidate_data = candidate.read_bytes()
    full_slot = candidate_data + b"\xff" * (0x7A0000 - len(candidate_data))
    store_erased = all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F221 candidate overlaps or initializes lyoko_store")

    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    required = {"etc/openmitrastar/release", "usr/libexec/lyoko/pkgbox"}
    if changed != required:
        raise SystemExit(f"F221 changed unexpected rootfs paths: {sorted(changed)}")

    manifest.update({
        "schema": "openmitrastar.f221-pkgbox-multicall/v1",
        "classification": "PRIVATE_DEVICE_BOUND_FIRMWARE_DO_NOT_DISTRIBUTE",
        "candidate_eligible": True,
        "release_eligible": False,
        "flash_supported": True,
        "device_identity": source_manifest["device_identity"],
        "web_identity": source_manifest["web_identity"],
        "web_security": source_manifest["web_security"],
        "source": {"firmware": "F220", "reason": "enable BusyBox multicall dispatch for pkgbox applet invocation"},
        "package_runtime_fix": {
            "pkgbox_sha256": pkgbox_manifest["sha256"],
            "pkgbox_bytes": pkgbox_manifest["bytes"],
            "added_applet": "wc",
            "multicall_dispatcher": True,
            "network_fetch": False,
            "persistent_install": False,
        },
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "F219 platform gate plus signed volatile package lifecycle",
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
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )

    final_out.parent.mkdir(parents=True, exist_ok=True)
    restrict_acl(final_out.parent, directory=True)
    shutil.copytree(output, final_out)
    (final_out / "known_hosts.f221").write_text(f"192.168.1.90 {public_key}\n", encoding="ascii", newline="\n")
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
        "pkgbox_sha256": pkgbox_manifest["sha256"],
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }, indent=2))
    cleanup()
    atexit.unregister(cleanup)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
