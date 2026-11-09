"""Linux-native offline F323 integration; no hardware or radio operation."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import f323_browser_compat_contract as contract
import lyoko_web_rootfs_worker as web
from package_f323_browser_compat import validate_package


def put(root: Path, relative: str, content: bytes, mode: int) -> dict:
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()) or target.is_symlink():
        raise ValueError("unsafe F323 target: " + relative)
    for parent in target.parents:
        if parent == root.parent:
            break
        if parent.is_symlink():
            raise ValueError("symlink parent of F323 target")
    if not target.is_file():
        raise ValueError("F323 transformation target is not a regular existing file")
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(content)
    try:
        temporary.chmod(mode)
        os.chown(temporary, 0, 0)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": relative, "bytes": len(content), "sha256": contract.digest(content), "mode": f"{mode:04o}"}


def run(args) -> None:
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("F323 integration requires the Linux build environment")
    contract.pinned(args.source.read_bytes(), contract.SOURCE_ROOTFS, "F321 rootfs")
    if web.sha256(args.manifest) != args.manifest_sha256:
        raise ValueError("F323 UI package manifest drift")
    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    expected = validate_package(args.overlay, manifest)
    ui_paths = set(expected)
    if args.image.exists() or args.result.exists():
        raise ValueError("refusing to overwrite F323 worker outputs")
    with tempfile.TemporaryDirectory(prefix="f323-browser-rootfs-", dir="/tmp") as directory:
        scratch = Path(directory)
        root, packed, verified = scratch / "rootfs", scratch / "packed.squashfs", scratch / "verified"
        subprocess.run(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(root), str(args.source)], check=True, stdout=subprocess.DEVNULL)
        before = web.inventory(root)
        if before[contract.API_PATH]["mode"] != 0o755 or before[contract.RELEASE_PATH]["mode"] != 0o644:
            raise ValueError("unexpected F321 API/release metadata")
        api = contract.api_bytes((root / contract.API_PATH).read_bytes())
        release = contract.release_bytes((root / contract.RELEASE_PATH).read_bytes(), args.build_id)
        web.apply_overlay(root, args.overlay, expected)
        expected = {**expected,
            contract.API_PATH: put(root, contract.API_PATH, api, 0o755),
            contract.RELEASE_PATH: put(root, contract.RELEASE_PATH, release, 0o644)}
        contract.verify_delta(before, web.inventory(root), expected, ui_paths)
        web.check_legacy_asset_metadata(root)
        subprocess.run(["mksquashfs", str(root), str(packed), "-noappend", "-all-root", "-comp", "xz", "-b", "131072",
                        "-no-xattrs", "-no-exports", "-all-time", str(args.epoch), "-mkfs-time", str(args.epoch),
                        "-processors", "1", "-no-progress"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(verified), str(packed)], check=True, stdout=subprocess.DEVNULL)
        after = web.inventory(verified)
        checks = contract.verify_delta(before, after, expected, ui_paths)
        web.check_legacy_asset_metadata(verified)
        shutil.copyfile(packed, args.image)
        args.result.write_text(json.dumps({"before": before, "after": after, "checks": checks,
            "expected_changes": expected, "ui_paths": sorted(ui_paths)}, sort_keys=True) + "\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "overlay", "manifest", "image", "result"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--epoch", required=True, type=int)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
