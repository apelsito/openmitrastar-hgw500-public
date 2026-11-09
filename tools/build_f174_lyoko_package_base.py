#!/usr/bin/env python3
"""Build F174 by integrating verified Lyoko IPKs into the F173 SquashFS."""
from __future__ import annotations

import contextlib
import hashlib
import json
from pathlib import Path
import shutil

import build_f170_lyoko_foundation_runtime_fix as engine
import integrate_lyoko_packages as integration
import lyoko_ipk


ROOT = Path(__file__).resolve().parents[1]
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f173-lyoko-hardware-inventory-from-f171/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f173-lyoko-hardware-inventory-from-f171-LZMA-OFFLINE-NO-FLASH"
FEED = ROOT / "versions/lyoko-feed-1.0-f174"
ASSETS = ROOT / "outputs/kernel-port/f174-lyoko-package-base-20260901"
PACKAGE_OVERLAY = ASSETS / "package-overlay"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f174-lyoko-package-base-from-f173/build"
BASE = "openmitrastar-linux510-q3-persistent-f174-lyoko-package-base-from-f173-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_package_overlay() -> dict[str, object]:
    feed_manifest = json.loads((FEED / "manifest.json").read_text(encoding="ascii"))
    if feed_manifest.get("trust") != "production":
        raise SystemExit("F174 requires a production-signed feed")
    packages_file = FEED / "repository/Packages"
    signature = FEED / "repository/Packages.sig.json"
    public_key = FEED / "repository/lyoko-feed-ed25519.pub"
    package_dir = FEED / "packages"
    lyoko_ipk.verify_index(packages_file, signature, public_key, package_dir)

    if PACKAGE_OVERLAY.exists():
        shutil.rmtree(PACKAGE_OVERLAY)
    PACKAGE_OVERLAY.mkdir(parents=True)
    indexed = {row["Package"]: row for row in integration.read_index(packages_file)}
    selected = indexed["lyoko-sysinfo"]
    installed_files = lyoko_ipk.install_tree(package_dir / selected["Filename"], PACKAGE_OVERLAY)

    installed_manifest = {
        "schema": "lyoko.installed-packages/v1",
        "packages": [{
            "package": selected["Package"],
            "version": selected["Version"],
            "architecture": selected["Architecture"],
            "sha256": selected["SHA256sum"],
        }],
        "files": sorted(installed_files),
        "source_index_sha256": sha256(packages_file),
        "signature_verified": True,
        "runtime_install": False,
    }
    installed_path = PACKAGE_OVERLAY / "usr/share/lyoko/packages/installed.json"
    installed_path.parent.mkdir(parents=True, exist_ok=True)
    installed_path.write_text(
        json.dumps(installed_manifest, indent=2, sort_keys=True) + "\n",
        encoding="ascii",
    )

    key_target = PACKAGE_OVERLAY / "etc/lyoko/keys/feed-ed25519.pub"
    key_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(public_key, key_target)
    feed_target = PACKAGE_OVERLAY / "usr/share/lyoko/feed"
    feed_target.mkdir(parents=True, exist_ok=True)
    for source in (packages_file, signature):
        shutil.copy2(source, feed_target / source.name)
    abi = PACKAGE_OVERLAY / "etc/lyoko/package-abi"
    abi.write_text(
        "\n".join((
            f"architecture={lyoko_ipk.ARCH}",
            f"kernel_abi={lyoko_ipk.KERNEL_ABI}",
            "libc_abi=uclibc",
            f"platform={lyoko_ipk.PLATFORM}",
            "runtime_install=disabled",
            "",
        )),
        encoding="ascii",
    )
    return {
        "feed_manifest_sha256": sha256(FEED / "manifest.json"),
        "index_sha256": sha256(packages_file),
        "signature_sha256": sha256(signature),
        "public_key_sha256": sha256(public_key),
        "packages": [{
            "name": selected["Package"],
            "version": selected["Version"],
            "architecture": selected["Architecture"],
            "sha256": selected["SHA256sum"],
            "files": installed_files,
        }],
        "installed_manifest_sha256": sha256(installed_path),
    }


@contextlib.contextmanager
def variant_context():
    names = (
        "SOURCE_BUILD", "SOURCE_BASE", "FOUNDATION", "OVERLAY", "ASSETS",
        "OUT", "BASE", "PRODUCT_VERSION", "ASSETS_SCHEMA", "DIFF_SCHEMA",
    )
    old = {name: getattr(engine, name) for name in names}
    try:
        engine.SOURCE_BUILD = SOURCE_BUILD
        engine.SOURCE_BASE = SOURCE_BASE
        engine.FOUNDATION = PACKAGE_OVERLAY
        engine.OVERLAY = PACKAGE_OVERLAY
        engine.ASSETS = ASSETS
        engine.OUT = OUT
        engine.BASE = BASE
        engine.PRODUCT_VERSION = "lyoko-foundation-1.1-f174"
        engine.ASSETS_SCHEMA = "openmitrastar.f174-lyoko-package-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f174-lyoko-package-rootfs-diff/v1"
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    package_state = prepare_package_overlay()
    with variant_context():
        rc = engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source_manifest = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f174-lyoko-package-base/v1",
        "classification": "F174_LYOKO_SIGNED_PACKAGE_BASE_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {
            "firmware": "F173 offline Foundation candidate; F170 currently installed",
            "rootfs": str((SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs").relative_to(ROOT)),
        },
        "change_scope": {
            "package_format": "standard deterministic IPK",
            "feed": "Ed25519 signature and package SHA-256 verified before integration",
            "installed": "lyoko-sysinfo 1.0.0-1",
            "runtime_install": "disabled",
            "kernel_dtb_radios": "byte-identical to F173/F171/F170/F167",
        },
        "package_state": package_state,
        "source_kernel_lzma_sha256": source_manifest["artifacts"]["kernel_lzma"]["sha256"],
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "F171 base gate, F173 hardware API and /usr/bin/lyoko-sysinfo execution",
        },
    })
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    sums = sorted(path for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS")
    (OUT / "SHA256SUMS").write_text(
        "".join(f"{sha256(path)}  {path.name}\n" for path in sums), encoding="ascii"
    )
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
