#!/usr/bin/env python3
"""Linux-native, offline SquashFS integration and metadata verification."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import subprocess
import tempfile
from lyoko_frontend_identity import API_PATH, BASE_FRONTEND_HASH, check_transform_spec, transform_bytes


FIXED_PATHS = {"etc/lyoko/web-next.env", "usr/share/openmitrastar/web/dashboard.html"}
IDENTITY_PATHS = {"etc/lyoko/frontend.env", "etc/lyoko/web-next.json"}
BRAND_PATHS = {"www/assets/movistar-logo.svg", "www/assets/telefonica-logo.svg", "www/assets/movistar-m.png"}
ASSET_PATH = re.compile(r"www/assets/lyoko-next/[A-Za-z0-9_-]+-[A-Za-z0-9_-]+\.(js|css)\Z")


def sha256(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def inventory(root: Path) -> dict:
    """Do not follow symlinks; include directory modes, owners and hardlinks."""
    result = {}
    hardlinks = {}
    for item in [root, *sorted(root.rglob("*"))]:
        relative = item.relative_to(root).as_posix()
        info = item.lstat()
        row = {"mode": stat.S_IMODE(info.st_mode), "uid": info.st_uid, "gid": info.st_gid}
        if stat.S_ISLNK(info.st_mode):
            row.update(type="symlink", target=os.readlink(item))
        elif stat.S_ISREG(info.st_mode):
            row.update(type="file", bytes=info.st_size, sha256=sha256(item))
            if info.st_nlink > 1:
                row["hardlink_group"] = hardlinks.setdefault((info.st_dev, info.st_ino), relative)
        elif stat.S_ISDIR(info.st_mode):
            row["type"] = "dir"
        else:
            row.update(type="special", kind=stat.S_IFMT(info.st_mode), rdev=info.st_rdev)
        result[relative] = row
    return result


def validate_overlay(overlay: Path, manifest: dict) -> dict:
    expected = {}
    for row in manifest["files"]:
        relative = row["path"]
        path = PurePosixPath(relative)
        if path.is_absolute() or ".." in path.parts or "\\" in relative or str(path) != relative:
            raise ValueError(f"unsafe overlay path: {relative}")
        if relative in expected or (relative not in FIXED_PATHS | BRAND_PATHS | IDENTITY_PATHS and not ASSET_PATH.fullmatch(relative)):
            raise ValueError(f"unexpected or duplicate overlay path: {relative}")
        if row["mode"] != "0644":
            raise ValueError(f"unexpected overlay mode: {relative}")
        item = overlay / relative
        if any(parent.is_symlink() for parent in [item, *item.parents] if parent != overlay.parent):
            raise ValueError(f"overlay symlink is forbidden: {relative}")
        if not item.is_file() or item.stat().st_size != row["bytes"] or sha256(item) != row["sha256"]:
            raise ValueError(f"overlay hash/size mismatch: {relative}")
        expected[relative] = row
    assets = [path for path in expected if path not in FIXED_PATHS | BRAND_PATHS | IDENTITY_PATHS]
    if not FIXED_PATHS.issubset(expected) or not 2 <= len(assets) <= 32 or {Path(path).suffix for path in assets} != {".js", ".css"}:
        raise ValueError("overlay must contain internal HTML, metadata and bounded hashed JS/CSS assets")
    if manifest.get("schema") in {"openmitrastar.lyoko-web-next-overlay/v2", "openmitrastar.lyoko-web-next-overlay/v3"} and not BRAND_PATHS.issubset(expected):
        raise ValueError("classic overlay is missing original branding")
    actual = {item.relative_to(overlay).as_posix() for item in overlay.rglob("*") if item.is_file() or item.is_symlink()}
    if actual != set(expected):
        raise ValueError(f"unmanifested overlay entries: {sorted(actual ^ set(expected))}")
    transforms = manifest.get("transforms", [])
    if len(transforms) > 1: raise ValueError("too many transforms")
    for spec in transforms: check_transform_spec(spec)
    if manifest.get("schema") == "openmitrastar.lyoko-web-next-overlay/v3":
        if len(transforms) != 1 or not IDENTITY_PATHS.issubset(expected): raise ValueError("missing identity integration")
        bundle = json.loads((overlay / "etc/lyoko/web-next.json").read_text(encoding="ascii"))
        identity = dict(line.split("=", 1) for line in (overlay / "etc/lyoko/frontend.env").read_text(encoding="ascii").splitlines() if "=" in line)
        if bundle.get("build_id") != manifest["build_id"] or identity.get("LYOKO_UI_BUILD_ID") != manifest["build_id"]:
            raise ValueError("frontend build identity mismatch")
        if identity.get("LYOKO_UI_VERSION") != bundle.get("ui_version"):
            raise ValueError("frontend version mismatch")
        active = {path for path in expected if path.startswith(("www/", "usr/share/"))}
        rows = {row["path"]: row for row in bundle["assets"]}
        if set(rows) != active or len(rows) != len(bundle["assets"]): raise ValueError("active bundle catalogue mismatch")
        for path, row in rows.items():
            if any(row[key] != expected[path][key] for key in ("bytes", "sha256")): raise ValueError("active bundle hash mismatch")
            url = "/dashboard.cgi" if path.startswith("usr/") else "/" + path.removeprefix("www/")
            if row.get("url") != url: raise ValueError("active bundle URL mismatch")
        if bundle["asset_bytes"] != sum(row["bytes"] for row in rows.values()): raise ValueError("active bundle byte count mismatch")
        if identity.get("LYOKO_UI_DASHBOARD_HTML_SHA256") != expected["usr/share/openmitrastar/web/dashboard.html"]["sha256"]:
            raise ValueError("dashboard identity hash mismatch")
    return expected


def validate_delta(before: dict, after: dict, expected: dict) -> dict:
    parents = {str(parent) for path in expected for parent in PurePosixPath(path).parents}
    new_dirs = parents - before.keys()
    changed = {path for path in before.keys() | after.keys() if before.get(path) != after.get(path)}
    desired = {}
    for relative, row in expected.items():
        required = {"type": "file", "bytes": row["bytes"], "sha256": row["sha256"], "mode": int(row["mode"], 8), "uid": 0, "gid": 0}
        # Keep existing hardlink topology for byte-identical files.
        old = before.get(relative, {})
        if all(old.get(key) == value for key, value in required.items()): required = old
        desired[relative] = required
        if relative in BRAND_PATHS and relative in before and before[relative] != required:
            raise ValueError(f"original brand asset would change: {relative}")
    changed_files = {path for path in expected if before.get(path) != desired[path]}
    allowed = changed_files | new_dirs
    if changed != allowed:
        raise ValueError(f"unexpected rootfs changes: {sorted(changed ^ allowed)}")
    for relative, required in desired.items():
        if after.get(relative) != required:
            raise ValueError(f"packaged file metadata/content mismatch: {relative}")
    for relative in new_dirs:
        if after.get(relative) != {"type": "dir", "mode": 0o755, "uid": 0, "gid": 0}:
            raise ValueError(f"new directory metadata mismatch: {relative}")
    return {"changed_files": sorted(changed_files), "preserved_overlay_files": sorted(expected.keys() - changed_files), "new_directories": sorted(new_dirs),
            "existing_directories_preserved": sum(row["type"] == "dir" for row in before.values()),
            "unchanged_entries": len(before.keys() - changed_files)}


def apply_overlay(root: Path, overlay: Path, expected: dict) -> None:
    for relative in sorted(expected):
        target = root / relative
        current = root
        for component in PurePosixPath(relative).parts[:-1]:
            current = current / component
            if current.is_symlink() or (current.exists() and not current.is_dir()):
                raise ValueError(f"unsafe target parent: {relative}")
            if not current.exists():
                current.mkdir(mode=0o755)
                current.chmod(0o755)
        if target.is_symlink() or (target.exists() and not target.is_file()):
            raise ValueError(f"unsafe target entry: {relative}")
        if target.is_file():
            metadata = target.stat()
            if (stat.S_IMODE(metadata.st_mode) == 0o644 and metadata.st_uid == 0 and metadata.st_gid == 0
                    and metadata.st_size == expected[relative]["bytes"] and sha256(target) == expected[relative]["sha256"]):
                continue
        # Replace this file only; never chmod or copy metadata onto existing parents.
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name)
            with (overlay / relative).open("rb") as source:
                shutil.copyfileobj(source, stream)
        try:
            temporary.chmod(0o644)
            os.chown(temporary, 0, 0)
            temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)


def apply_identity_transform(root: Path, manifest: dict) -> tuple[dict, list]:
    expected = {}
    audits = []
    for spec in manifest.get("transforms", []):
        target = root / API_PATH
        if target.is_symlink() or not target.resolve().is_relative_to(root.resolve()): raise ValueError("unsafe API target")
        after, audit = transform_bytes(target.read_bytes(), spec)
        with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as stream:
            temporary = Path(stream.name); stream.write(after)
        try:
            temporary.chmod(0o755); os.chown(temporary, 0, 0); temporary.replace(target)
        finally:
            temporary.unlink(missing_ok=True)
        expected[API_PATH] = {"path": API_PATH, "mode": "0755", "bytes": len(after), "sha256": audit["after_sha256"]}
        audits.append(audit)
    return expected, audits


def check_legacy_asset_metadata(root: Path):
    identity = dict(line.split("=", 1) for line in (root / "etc/lyoko/frontend.env").read_text().splitlines() if "=" in line)
    names = {"DASHBOARD_HTML": "usr/share/openmitrastar/web/dashboard.html", "APP_JS": "www/app.js", "APP_CSS": "www/app.css",
             "CAPABILITIES_CSS": "www/capabilities.css", "LAYOUT_FIXES_CSS": "www/layout-fixes.css", "F313_CSS": "www/f313-console.css",
             "LOGIN_HTML": "www/login.html", "LOGIN_CSS": "www/login.css"}
    total = 0
    for key, relative in names.items():
        item = root / relative
        if identity.get("LYOKO_UI_" + key + "_SHA256") != sha256(item): raise ValueError(f"legacy asset metadata mismatch: {relative}")
        total += item.stat().st_size
    if int(identity["LYOKO_UI_ASSET_BYTES"]) != total: raise ValueError("legacy asset byte count mismatch")


def run(args) -> None:
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("run inside the Linux build environment as root")
    if sha256(args.source) != args.source_sha256 or sha256(args.manifest) != args.manifest_sha256:
        raise ValueError("pinned source or overlay manifest changed")
    manifest = json.loads(args.manifest.read_text(encoding="ascii"))
    expected = validate_overlay(args.overlay, manifest)
    if args.image.exists() or args.result.exists():
        raise ValueError("refusing to overwrite worker outputs")
    with tempfile.TemporaryDirectory(prefix="openmitrastar-web-rootfs-", dir="/tmp") as directory:
        scratch = Path(directory)
        root = scratch / "rootfs"
        packed = scratch / "packed.squashfs"
        verified = scratch / "verified"
        subprocess.run(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(root), str(args.source)], check=True, stdout=subprocess.DEVNULL)
        before = inventory(root)
        if manifest.get("transforms") and before.get("etc/lyoko/frontend.env", {}).get("sha256") != BASE_FRONTEND_HASH:
            raise ValueError("base frontend identity differs from the approved source")
        apply_overlay(root, args.overlay, expected)
        transformed, audits = apply_identity_transform(root, manifest)
        expected = {**expected, **transformed}
        if audits: check_legacy_asset_metadata(root)
        validate_delta(before, inventory(root), expected)
        subprocess.run(["mksquashfs", str(root), str(packed), "-noappend", "-all-root", "-comp", "xz", "-b", "131072",
                        "-no-xattrs", "-no-exports", "-all-time", str(args.epoch), "-mkfs-time", str(args.epoch),
                        "-processors", "1", "-no-progress"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(verified), str(packed)], check=True, stdout=subprocess.DEVNULL)
        after = inventory(verified)
        checks = validate_delta(before, after, expected)
        shutil.copyfile(packed, args.image)
        args.result.write_text(json.dumps({"before": before, "after": after, "checks": checks, "transforms": audits}, sort_keys=True) + "\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "overlay", "manifest", "image", "result"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--source-sha256", required=True)
    parser.add_argument("--manifest-sha256", required=True)
    parser.add_argument("--epoch", required=True, type=int)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
