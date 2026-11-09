#!/usr/bin/env python3
"""Build F177 with volatile signed-IPK management on top of F176."""
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
FOUNDATION = ROOT / "versions/lyoko-foundation-1.3-f177"
SOURCE_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f176-lyoko-package-ui-from-f174/build"
SOURCE_BASE = "openmitrastar-linux510-q3-persistent-f176-lyoko-package-ui-from-f174-LZMA-OFFLINE-NO-FLASH"
FEED = ROOT / "outputs/packages/lyoko-v1.1"
PKGBOX = ROOT / "outputs/packages/lyoko-pkgbox/lyoko-pkgbox"
ASSETS = ROOT / "outputs/kernel-port/f177-lyoko-package-manager-20260901"
OVERLAY = ASSETS / "combined-overlay"
OUT = ROOT / "work/mission-state/q3-persistent-composite-f177-lyoko-package-manager-from-f176/build"
BASE = "openmitrastar-linux510-q3-persistent-f177-lyoko-package-manager-from-f176-LZMA-OFFLINE-NO-FLASH"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare_overlay() -> dict[str, object]:
    feed_manifest = json.loads((FEED / "manifest.json").read_text(encoding="ascii"))
    if feed_manifest.get("trust") != "production":
        raise SystemExit("F177 requires a production-signed feed")
    if not PKGBOX.is_file():
        raise SystemExit("missing Lyoko pkgbox")
    packages_file = FEED / "repository/Packages"
    signature = FEED / "repository/Packages.sig.json"
    public_key = FEED / "repository/lyoko-feed-ed25519.pub"
    package_dir = FEED / "packages"
    lyoko_ipk.verify_index(packages_file, signature, public_key, package_dir)

    if OVERLAY.exists():
        shutil.rmtree(OVERLAY)
    shutil.copytree(FOUNDATION / "overlay", OVERLAY)
    pkgbox_target = OVERLAY / "usr/libexec/lyoko/pkgbox"
    pkgbox_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(PKGBOX, pkgbox_target)

    feed_target = OVERLAY / "usr/share/lyoko/feed"
    archive_target = feed_target / "archives"
    archive_target.mkdir(parents=True, exist_ok=True)
    for source in (packages_file, signature):
        shutil.copy2(source, feed_target / source.name)
    for package in sorted(package_dir.glob("*.ipk")):
        shutil.copy2(package, archive_target / package.name)
    key_target = OVERLAY / "etc/lyoko/keys/feed-ed25519.pub"
    key_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(public_key, key_target)

    indexed = {row["Package"]: row for row in integration.read_index(packages_file)}
    installed = indexed["lyoko-sysinfo"]
    installed_manifest = {
        "schema": "lyoko.installed-packages/v1",
        "packages": [{
            "package": installed["Package"],
            "version": installed["Version"],
            "architecture": installed["Architecture"],
            "sha256": installed["SHA256sum"],
        }],
        "files": ["/usr/bin/lyoko-sysinfo"],
        "source_index_sha256": sha256(packages_file),
        "signature_verified": True,
        "runtime_install": False,
    }
    installed_path = OVERLAY / "usr/share/lyoko/packages/installed.json"
    installed_path.parent.mkdir(parents=True, exist_ok=True)
    installed_path.write_text(json.dumps(installed_manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")
    signature_data = json.loads(signature.read_text(encoding="ascii"))
    return {
        "feed_manifest_sha256": sha256(FEED / "manifest.json"),
        "index_sha256": sha256(packages_file),
        "key_id": signature_data["key_id"],
        "pkgbox": {"bytes": PKGBOX.stat().st_size, "sha256": sha256(PKGBOX)},
        "bundled_packages": feed_manifest["packages"],
        "immutable_installed": ["lyoko-sysinfo"],
        "volatile_install_available": True,
        "network_fetch": False,
        "persistent_install": False,
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
        engine.FOUNDATION = FOUNDATION
        engine.OVERLAY = OVERLAY
        engine.ASSETS = ASSETS
        engine.OUT = OUT
        engine.BASE = BASE
        engine.PRODUCT_VERSION = "lyoko-foundation-1.3-f177"
        engine.ASSETS_SCHEMA = "openmitrastar.f177-lyoko-package-manager-assets/v1"
        engine.DIFF_SCHEMA = "openmitrastar.f177-lyoko-package-manager-rootfs-diff/v1"
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def main() -> int:
    package_manager = prepare_overlay()
    with variant_context():
        rc = engine.main()
    if rc:
        return rc
    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    manifest.update({
        "schema": "openmitrastar.f177-lyoko-package-manager/v1",
        "classification": "F177_LYOKO_VOLATILE_PACKAGE_MANAGER_OFFLINE_CANDIDATE",
        "candidate_eligible": True,
        "flash_supported": True,
        "source": {
            "firmware": "F176 offline package-UI candidate; F170 currently installed",
            "rootfs": str((SOURCE_BUILD / f"{SOURCE_BASE}.rootfs.squashfs").relative_to(ROOT)),
        },
        "change_scope": {
            "manager": "lyoko-pkg list/status/verify/install/remove/list-installed/exec",
            "install_root": "volatile /run by default; external path only when explicitly selected",
            "feed": "two production-signed bundled IPKs",
            "network_fetch": "disabled",
            "persistent_install": "disabled",
            "kernel_dtb_radios": "byte-identical to F176/F174/F173/F171/F170/F167",
        },
        "package_manager": package_manager,
        "source_kernel_lzma_sha256": source["artifacts"]["kernel_lzma"]["sha256"],
        "physical_validation": {
            "status": "NOT_RUN",
            "required": "list, verify, volatile install, exec and remove lyoko-netdiag on physical ARC700",
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
