#!/usr/bin/env python3
"""Build private F215 from F214 with the crashing SPI probe disabled at boot."""
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

    device_dir = args.identity_root.resolve() / args.device_id
    key = device_dir / "dropbear_ed25519_host_key"
    if not key.is_file():
        raise SystemExit("device identity is missing")
    fingerprint = inspect_key(args.distro, args.dropbearkey, key)

    private_source_build = args.private_output_root.resolve() / args.device_id / "firmware/f214-device-bound"
    source_base = f"openmitrastar-linux510-f214-{args.device_id}-PRIVATE-NO-FLASH"
    source_manifest_path = private_source_build / "manifest.json"
    if not source_manifest_path.is_file():
        raise SystemExit("F214 private source is missing")
    source_manifest = json.loads(source_manifest_path.read_text(encoding="ascii"))
    if source_manifest.get("device_identity", {}).get("fingerprint") != fingerprint:
        raise SystemExit("F214 device identity mismatch")

    final_out = args.private_output_root.resolve() / args.device_id / "firmware/f215-device-bound"
    if final_out.exists():
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")

    scratch = ROOT / ".codex_tmp" / f"f215-device-{args.device_id}"
    if scratch.exists():
        shutil.rmtree(scratch)

    def cleanup_scratch() -> None:
        if scratch.exists():
            shutil.rmtree(scratch)

    atexit.register(cleanup_scratch)
    foundation = scratch / "foundation"
    overlay = foundation / "overlay"
    assets = scratch / "assets"
    output = scratch / "build"
    source_build = scratch / "source-build"
    shutil.copytree(private_source_build, source_build)
    init = overlay / "etc/init.d/S31-spi-probe"
    init.parent.mkdir(parents=True, exist_ok=True)
    init.write_text(
        "#!/bin/sh\n"
        "mkdir -p /run/openmitrastar\n"
        "cat > /run/openmitrastar/spi-probe.state <<'EOF'\n"
        "status=disabled\n"
        "reason=f214-machine-check\n"
        "write_capable=N\n"
        "EOF\n"
        "echo 'OMSPIPROBE_DISABLED reason=f214-machine-check'\n"
        "exit 0\n",
        encoding="ascii",
    )

    base = f"openmitrastar-linux510-f215-{args.device_id}-PRIVATE-NO-FLASH"
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
        engine.PRODUCT_VERSION = "lyoko-foundation-3.1-f215-device"
        engine.ASSETS_SCHEMA = "openmitrastar.f215-device-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f215-device-rootfs-diff/v1"
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
        raise SystemExit("F215 candidate overlaps or initializes lyoko_store")

    manifest.update({
        "schema": "openmitrastar.f215-spi-probe-disabled/v1",
        "classification": "PRIVATE_DEVICE_BOUND_FIRMWARE_DO_NOT_DISTRIBUTE",
        "candidate_eligible": True,
        "release_eligible": False,
        "flash_supported": True,
        "device_identity": source_manifest["device_identity"],
        "web_identity": source_manifest["web_identity"],
        "source": {"firmware": "F214", "reason": "disable boot-time SPI probe after physical Machine Check"},
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "persistent boot, web/API, package signature and dual-radio gates",
        },
        "storage": {
            **source_manifest["storage"],
            "store_erased_ff": store_erased,
            "candidate_ends_before_store": len(candidate_data) <= STORE_SLOT_OFFSET,
        },
        "spi_probe": {
            **source_manifest["spi_probe"],
            "boot_state": "disabled",
            "disabled_reason": "F214 physical Machine Check during insmod",
            "write": False,
            "mtd_registration": False,
        },
    })
    manifest["layout"]["mtd_mapping"] = source_manifest["layout"]["mtd_mapping"]
    manifest["safety"].update({
        "lyoko_store": "read-only and unformatted",
        "module_registers_mtd": False,
        "module_has_write_path": False,
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in output.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (output / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )

    final_out.parent.mkdir(parents=True, exist_ok=True)
    restrict_acl(final_out.parent, directory=True)
    shutil.copytree(output, final_out)
    restrict_acl(final_out, directory=True)
    for path in final_out.iterdir():
        if path.is_file():
            restrict_acl(path, directory=False)
    print(json.dumps({
        "status": "PASS",
        "device_id": args.device_id,
        "output": str(final_out),
        "candidate": str(final_out / manifest["artifacts"]["webformat"]["file"]),
        "bytes": manifest["artifacts"]["webformat"]["bytes"],
        "sha256": manifest["artifacts"]["webformat"]["sha256"],
        "single_change": "disable S31-spi-probe boot load",
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }, indent=2))
    cleanup_scratch()
    atexit.unregister(cleanup_scratch)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
