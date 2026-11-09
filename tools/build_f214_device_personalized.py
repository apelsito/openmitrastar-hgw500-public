#!/usr/bin/env python3
"""Build private F214 from F213 with device SSH and web-login identity."""
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
TEMPLATE = ROOT / "versions/lyoko-foundation-3.0-f213"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f213-movistar-f1-ui-from-f209/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f213-movistar-f1-ui-from-f209-LZMA-OFFLINE-NO-FLASH"
PRIVATE_KEY_REL = "usr/share/openmitrastar/device-identity/dropbear_ed25519_host_key"
WEB_HASH_REL = "usr/share/openmitrastar/device-identity/web_password.sha256"
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
    parser.add_argument("--verify-existing", action="store_true")
    args = parser.parse_args()
    if not DEVICE_RE.fullmatch(args.device_id):
        raise SystemExit("invalid --device-id")

    identity_dir = args.identity_root.resolve() / args.device_id
    key = identity_dir / "dropbear_ed25519_host_key"
    if not key.is_file():
        raise SystemExit("device identity is missing; run init_lyoko_device_host_key.py first")
    fingerprint = inspect_key(args.distro, args.dropbearkey, key)
    private_root = args.private_output_root.resolve()
    try:
        private_root.relative_to(ROOT.resolve())
    except ValueError:
        pass
    else:
        raise SystemExit("private firmware output must be outside the workspace")
    web_hash = identity_dir / "web_password.sha256"
    if not web_hash.is_file():
        raise SystemExit("device web credential hash is missing")
    web_hash_value = web_hash.read_text(encoding="ascii").strip()
    if len(web_hash_value) != 64 or any(char not in "0123456789abcdef" for char in web_hash_value):
        raise SystemExit("device web credential hash is invalid")
    final_out = private_root / args.device_id / "firmware/f214-device-bound"
    if final_out.exists() and not args.verify_existing:
        raise SystemExit(f"refusing to overwrite private firmware: {final_out}")
    if args.verify_existing and not final_out.is_dir():
        raise SystemExit(f"private firmware to verify is missing: {final_out}")

    scratch = ROOT / ".codex_tmp" / f"f214-device-{args.device_id}"
    if scratch.exists():
        if scratch.resolve().parent != (ROOT / ".codex_tmp").resolve():
            raise SystemExit("unsafe scratch path")
        shutil.rmtree(scratch)

    def cleanup_scratch() -> None:
        if scratch.exists():
            shutil.rmtree(scratch)

    atexit.register(cleanup_scratch)
    foundation = scratch / "foundation"
    overlay = foundation / "overlay"
    assets = scratch / "assets"
    output = scratch / "build"
    shutil.copytree(TEMPLATE / "overlay", overlay)
    private_target = overlay / PRIVATE_KEY_REL
    private_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(key, private_target)
    web_target = overlay / WEB_HASH_REL
    web_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(web_hash, web_target)

    base = f"openmitrastar-linux510-f214-{args.device_id}-PRIVATE-NO-FLASH"
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS", "OUT", "BASE",
        "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA", "REMOVE_PATHS",
    )
    old = {name: getattr(engine, name) for name in names}
    old_rootfs_window = compose_engine.ROOTFS_WINDOW
    try:
        engine.SOURCE_BUILD = SOURCE_BUILD
        engine.SOURCE_BASE = SOURCE_BASE
        engine.FOUNDATION = foundation
        engine.OVERLAY = overlay
        engine.ASSETS = assets
        engine.OUT = output
        engine.BASE = base
        engine.PRODUCT_VERSION = "lyoko-foundation-3.0-f214-device"
        engine.ASSETS_SCHEMA = "openmitrastar.f214-device-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f214-device-rootfs-diff/v1"
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
    source_manifest = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    rootfs = output / f"{base}.rootfs.squashfs"
    verify_embedded_key(rootfs, fingerprint, args.distro, args.dropbearkey, scratch)
    candidate = output / manifest["artifacts"]["webformat"]["file"]
    candidate_data = candidate.read_bytes()
    full_slot = candidate_data + b"\xff" * (0x7A0000 - len(candidate_data))
    store_erased = all(value == 0xFF for value in full_slot[STORE_SLOT_OFFSET:STORE_SLOT_OFFSET + STORE_SIZE])
    if not store_erased or len(candidate_data) > STORE_SLOT_OFFSET:
        raise SystemExit("F208 candidate overlaps or initializes lyoko_store")
    manifest.update({
        "schema": "openmitrastar.f214-device-personalized/v1",
        "classification": "PRIVATE_DEVICE_BOUND_FIRMWARE_DO_NOT_DISTRIBUTE",
        "candidate_eligible": True,
        "release_eligible": False,
        "flash_supported": True,
        "device_identity": {
            "device_id": args.device_id,
            "algorithm": "ed25519",
            "fingerprint": fingerprint,
            "storage": "read-only mtd4 firmware image",
            "private_key_in_workspace": False,
        },
        "web_identity": {
            "credential": "device-label-password",
            "storage": "read-only mtd4 firmware image as SHA-256 only",
            "plaintext_in_firmware": False,
            "hash_in_workspace": False,
            "session_scope": "full Lyoko console",
            "rate_limit": "per-client bounded lockout",
        },
        "source": {"firmware": "F213", "template": "lyoko-foundation-3.0-f213"},
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "device-password login, lockout, SSH fingerprint, storage split, package signature and dual-radio gates",
        },
        "distribution": "PRIVATE_LOCAL_DEVICE_ONLY",
        "storage": {
            **source_manifest["storage"],
            "store_erased_ff": store_erased,
            "candidate_ends_before_store": len(candidate_data) <= STORE_SLOT_OFFSET,
        },
        "spi_probe": source_manifest["spi_probe"],
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

    if args.verify_existing:
        existing_manifest = json.loads((final_out / "manifest.json").read_text(encoding="ascii"))
        existing_candidate = final_out / existing_manifest["artifacts"]["webformat"]["file"]
        rebuilt_candidate = output / manifest["artifacts"]["webformat"]["file"]
        existing_sha = sha256(existing_candidate)
        rebuilt_sha = sha256(rebuilt_candidate)
        if existing_sha != rebuilt_sha or rebuilt_sha != manifest["artifacts"]["webformat"]["sha256"]:
            raise SystemExit("F214 reproducibility mismatch")
        if existing_manifest["device_identity"]["fingerprint"] != fingerprint:
            raise SystemExit("existing F214 fingerprint mismatch")
        result = {
            "status": "PASS_REPRODUCIBLE",
            "device_id": args.device_id,
            "fingerprint": fingerprint,
            "existing_sha256": existing_sha,
            "rebuilt_sha256": rebuilt_sha,
            "hardware_actions": {"router": False, "uart": False, "flash": False},
        }
        cleanup_scratch()
        atexit.unregister(cleanup_scratch)
        print(json.dumps(result, indent=2))
        return 0

    final_out.parent.mkdir(parents=True, exist_ok=True)
    restrict_acl(final_out.parent, directory=True)
    shutil.copytree(output, final_out)
    restrict_acl(final_out, directory=True)
    for path in final_out.iterdir():
        if path.is_file():
            restrict_acl(path, directory=False)
    result = {
        "status": "PASS",
        "device_id": args.device_id,
        "fingerprint": fingerprint,
        "output": str(final_out),
        "candidate": str(final_out / manifest["artifacts"]["webformat"]["file"]),
        "bytes": manifest["artifacts"]["webformat"]["bytes"],
        "sha256": manifest["artifacts"]["webformat"]["sha256"],
        "hardware_actions": {"router": False, "uart": False, "flash": False},
    }
    cleanup_scratch()
    atexit.unregister(cleanup_scratch)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
