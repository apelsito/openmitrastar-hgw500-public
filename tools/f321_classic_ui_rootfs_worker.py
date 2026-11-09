"""Linux-only F321 UI integration with a bounded release-identity update."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

import lyoko_web_rootfs_worker as web


SOURCE_ROOTFS_HASHES = {
    "f314": "ee2c7a63ee738382ba8eaf813cfd725e64e52ce0686bfbf83129a78dcf323cce",
    "f319": "71bb527783b02f8952b09d7f423eb3248d679c03f7d2975accdb1b7d09649e9d",
}
SOURCE_RELEASE_HASHES = {
    "f314": "a9396f40e2374d88d5d5f3a9eb09f163c396c316f9e9212350155bf4309a5fb3",
    "f319": "dbed2e8bc0d8ea81926d136fbfb07e333bb5cdc3d9661abd4ab01752ace826b0",
}
RELEASE_PATH = "etc/openmitrastar/release"


def product_version(base: str) -> str:
    if base not in SOURCE_ROOTFS_HASHES:
        raise ValueError("unknown F321 lineage")
    return f"lyoko-foundation-6.8.5-f321-classic-ui-{base}-device"


def release_bytes(source: bytes, build_id: str, ui_version: str, base: str) -> bytes:
    if base not in SOURCE_RELEASE_HASHES or hashlib.sha256(source).hexdigest() != SOURCE_RELEASE_HASHES[base]:
        raise ValueError("release source is not the pinned " + base.upper() + " identity")
    if not re.fullmatch(r"[0-9a-f]{16}", build_id) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", ui_version):
        raise ValueError("invalid F321 release identity")
    replacements = {
        "OPENMITRASTAR_PRODUCT_VERSION": product_version(base),
        "OPENMITRASTAR_UI_VERSION": ui_version,
        "OPENMITRASTAR_BUILD_ID": build_id,
    }
    result = []
    seen = set()
    for line in source.decode("ascii").splitlines():
        key = line.split("=", 1)[0]
        if key in replacements:
            if key in seen:
                raise ValueError("duplicate release field")
            seen.add(key)
            line = key + "=" + replacements[key]
        result.append(line)
    if seen != set(replacements):
        raise ValueError("missing pinned release field")
    return ("\n".join(result) + "\n").encode("ascii")


def run(args) -> None:
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("F321 rootfs integration requires the Linux build environment")
    if web.sha256(args.source) != SOURCE_ROOTFS_HASHES[args.base] or web.sha256(args.manifest) != args.manifest_sha256:
        raise ValueError("immutable base rootfs or frontend manifest changed")
    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    expected = web.validate_overlay(args.overlay, manifest)
    if manifest.get("schema") != "openmitrastar.lyoko-web-next-overlay/v3":
        raise ValueError("F321 requires the reviewed classic TSX v3 overlay")
    if args.image.exists() or args.result.exists():
        raise ValueError("refusing to overwrite F321 worker outputs")
    bundle = json.loads((args.overlay / "etc/lyoko/web-next.json").read_text(encoding="ascii"))
    with tempfile.TemporaryDirectory(prefix="f321-ui-rootfs-", dir="/tmp") as directory:
        scratch = Path(directory)
        root, packed, verified = scratch / "rootfs", scratch / "packed.squashfs", scratch / "verified"
        subprocess.run(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(root), str(args.source)], check=True, stdout=subprocess.DEVNULL)
        before = web.inventory(root)
        if before.get("etc/lyoko/frontend.env", {}).get("sha256") != web.BASE_FRONTEND_HASH:
            raise ValueError("base frontend identity does not match the pinned package")
        web.apply_overlay(root, args.overlay, expected)
        transformed, audits = web.apply_identity_transform(root, manifest)
        expected = {**expected, **transformed}
        release = root / RELEASE_PATH
        if release.is_symlink() or before[RELEASE_PATH]["mode"] != 0o644:
            raise ValueError("unexpected base release entry")
        content = release_bytes(release.read_bytes(), args.firmware_build_id, bundle["ui_version"], args.base)
        release.write_bytes(content)
        expected[RELEASE_PATH] = {"path": RELEASE_PATH, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest(), "mode": "0644"}
        web.check_legacy_asset_metadata(root)
        web.validate_delta(before, web.inventory(root), expected)
        subprocess.run(["mksquashfs", str(root), str(packed), "-noappend", "-all-root", "-comp", "xz", "-b", "131072",
                        "-no-xattrs", "-no-exports", "-all-time", str(args.epoch), "-mkfs-time", str(args.epoch),
                        "-processors", "1", "-no-progress"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(verified), str(packed)], check=True, stdout=subprocess.DEVNULL)
        after = web.inventory(verified)
        checks = web.validate_delta(before, after, expected)
        web.check_legacy_asset_metadata(verified)
        shutil.copyfile(packed, args.image)
        args.result.write_text(json.dumps({"before": before, "after": after, "checks": checks, "transforms": audits,
                                          "release_identity": expected[RELEASE_PATH]}, sort_keys=True) + "\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", required=True, choices=tuple(SOURCE_ROOTFS_HASHES))
    parser.add_argument("--firmware-build-id", required=True)
    for name in ("source", "overlay", "manifest", "image", "result"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--epoch", required=True, type=int)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
