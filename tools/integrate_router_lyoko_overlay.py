#!/usr/bin/env python3

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import stat
import sys
from pathlib import Path

import sync_router_lyoko_static_data as sync_static
import verify_router_lyoko_no_secrets as no_secrets


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERLAY = ROOT / "work" / "mission-state" / "router-lyoko-v0"


FORBIDDEN_ROOTFS_TOKENS = (
    "saveenv",
    "fw_setenv",
    "mtd_write ",
    "flashcp",
    "/dev/mtd",
    "dd if=",
    "dd of=",
    "insmod ",
    "rmmod ",
    "modprobe ",
    "reboot",
    "halt",
    "poweroff",
    "ifconfig br0 ",
    "ip addr add",
    "ip link set",
    "call_qcsapi ",
    "qweconfig set",
    "hostapd_cli ",
)

EXECUTABLE_CGI_NAMES = {"lyoko", "lyoko-control"}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rel_from_manifest(rel: str) -> Path:
    posix = Path(*rel.split("/"))
    if posix.is_absolute() or ".." in posix.parts:
        raise ValueError(f"unsafe manifest path: {rel}")
    return posix


def load_manifest(overlay: Path) -> dict:
    manifest_path = overlay / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"missing manifest: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("classification") != "READ-ONLY-LAB-OVERLAY-NO-FLASH":
        raise RuntimeError(
            "overlay classification is not READ-ONLY-LAB-OVERLAY-NO-FLASH"
        )
    if manifest.get("guards", {}).get("flash_candidate") is not False:
        raise RuntimeError("overlay is not explicitly marked flash_candidate=false")
    return manifest


def verify_overlay_sources(overlay: Path, manifest: dict) -> list[Path]:
    files: list[Path] = []
    for rel, meta in manifest["files"].items():
        src = overlay / rel_from_manifest(rel)
        if not src.is_file():
            raise FileNotFoundError(f"missing overlay file: {rel}")
        data_len = src.stat().st_size
        data_sha = sha256_file(src)
        if data_len != meta["bytes"]:
            raise RuntimeError(f"size mismatch for {rel}: {data_len} != {meta['bytes']}")
        if data_sha != meta["sha256"]:
            raise RuntimeError(f"sha256 mismatch for {rel}: {data_sha} != {meta['sha256']}")
        files.append(src)
    return files


def verify_static_truth_sync(overlay: Path) -> None:
    generated = sync_static.generate_static_data()
    mismatches = sync_static.find_static_drift(
        generated,
        data_dir=overlay / "rootfs" / "var" / "www" / "lyoko-data",
        manifest_path=overlay / "manifest.json",
        sha256sums_path=overlay / "SHA256SUMS",
    )
    if mismatches:
        raise RuntimeError(
            "static Lyoko truth is stale; run tools/sync_router_lyoko_static_data.py "
            f"before integration: {json.dumps(mismatches, ensure_ascii=False)}"
        )


def detect_web_roots(rootfs: Path, create_var_www: bool) -> list[Path]:
    candidates = [rootfs / "var" / "www", rootfs / "www"]
    roots = [p for p in candidates if p.is_dir()]
    if roots:
        return roots
    if not create_var_www:
        raise RuntimeError(
            f"no web root found under {rootfs}; expected /var/www or /www "
            "(pass --create-var-www for a fresh RAM rootfs staging tree)"
        )
    created = rootfs / "var" / "www"
    created.mkdir(parents=True, exist_ok=True)
    return [created]


def destination_for_source(src: Path, overlay: Path, web_root: Path) -> Path:
    rel = src.relative_to(overlay / "rootfs" / "var" / "www")
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe overlay web path: {rel}")
    return web_root / rel


def scan_forbidden_tokens(paths: list[Path]) -> None:
    for path in paths:
        text = path.read_text(encoding="utf-8", errors="ignore")
        for token in FORBIDDEN_ROOTFS_TOKENS:
            if token in text:
                raise RuntimeError(f"forbidden control token {token!r} found in {path}")


def verify_no_secrets(paths: list[Path], overlay: Path) -> None:
    no_secrets.assert_no_secrets(
        paths,
        base=overlay / "rootfs" / "var" / "www",
    )


def copy_one(src: Path, dst: Path, force: bool, dry_run: bool) -> str:
    if dst.exists():
        if dst.is_symlink():
            raise RuntimeError(f"refusing to overwrite symlink: {dst}")
        if not dst.is_file():
            raise RuntimeError(f"refusing to overwrite non-file path: {dst}")
        if sha256_file(src) == sha256_file(dst):
            if not dry_run and dst.name in EXECUTABLE_CGI_NAMES:
                mode = dst.stat().st_mode
                dst.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            return "already-present"
        if not force:
            raise RuntimeError(f"destination differs; use --force to replace: {dst}")
    if dry_run:
        return "would-copy"
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)
    if dst.name in EXECUTABLE_CGI_NAMES:
        mode = dst.stat().st_mode
        dst.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    if sha256_file(src) != sha256_file(dst):
        raise RuntimeError(f"post-copy sha256 mismatch: {dst}")
    return "copied"


def integrate(
    overlay: Path,
    rootfs: Path,
    create_var_www: bool,
    force: bool,
    dry_run: bool,
) -> dict:
    overlay = overlay.resolve()
    rootfs = rootfs.resolve()
    if not rootfs.exists() or not rootfs.is_dir():
        raise RuntimeError(f"rootfs directory does not exist: {rootfs}")

    manifest = load_manifest(overlay)
    sources = verify_overlay_sources(overlay, manifest)
    verify_static_truth_sync(overlay)
    web_sources = [
        p for p in sources if p.is_relative_to(overlay / "rootfs" / "var" / "www")
    ]
    scan_forbidden_tokens(web_sources)
    verify_no_secrets(web_sources, overlay)

    web_roots = detect_web_roots(rootfs, create_var_www)
    actions = []
    for web_root in web_roots:
        for src in web_sources:
            dst = destination_for_source(src, overlay, web_root)
            status = copy_one(src, dst, force=force, dry_run=dry_run)
            actions.append(
                {
                    "status": status,
                    "source": str(src),
                    "destination": str(dst),
                    "sha256": sha256_file(src),
                    "intended_mode": "0755" if src.name in EXECUTABLE_CGI_NAMES else "preserve",
                }
            )

    return {
        "ok": True,
        "classification": manifest["classification"],
        "dry_run": dry_run,
        "rootfs": str(rootfs),
        "web_roots": [str(p) for p in web_roots],
        "files": actions,
        "notes": [
            "RAM-test rootfs integration only.",
            "No image rebuild, flash write, bootenv write, module mutation, or network reconfiguration performed.",
        ],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Integrate Router-Lyoko read-only web overlay into a RAM-test rootfs."
    )
    parser.add_argument(
        "--rootfs",
        required=True,
        type=Path,
        help="Destination rootfs staging directory. Must already exist.",
    )
    parser.add_argument(
        "--overlay",
        default=DEFAULT_OVERLAY,
        type=Path,
        help=f"Router-Lyoko overlay directory (default: {DEFAULT_OVERLAY})",
    )
    parser.add_argument(
        "--create-var-www",
        action="store_true",
        help="Create /var/www if the destination rootfs has no /var/www or /www.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace existing destination files when their hashes differ.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Verify and report actions without copying files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        report = integrate(
            overlay=args.overlay,
            rootfs=args.rootfs,
            create_var_www=args.create_var_www,
            force=args.force,
            dry_run=args.dry_run,
        )
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, indent=2), file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
