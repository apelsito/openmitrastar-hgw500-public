"""Single-process Linux rootfs repack for the pinned F322 shadow experiment."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

import f322_shadow_contract as contract
import lyoko_web_rootfs_worker as web


HELPERS = ("usr/sbin/om-dfs-status", "usr/sbin/om-radarctl")


def put(root: Path, relative: str, content: bytes, mode: int) -> dict:
    target = root / relative
    if not target.resolve().is_relative_to(root.resolve()) or any(path.is_symlink() for path in [target, *target.parents] if path != root.parent):
        raise ValueError("unsafe F322 target: " + relative)
    target.parent.mkdir(parents=True, exist_ok=True)
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
        raise ValueError("F322 repack requires the Linux build environment")
    contract.pinned(args.source.read_bytes(), contract.SOURCE_ROOTFS, "exact F321 rootfs")
    donor = args.donor_start.read_bytes()
    contract.pinned(donor, contract.DONOR_START, "F315 bootstrap")
    qdrv = (args.module_dir / "qdrv-f315-external-radar.ko").read_bytes()
    provider = (args.module_dir / "qtn_radar_shadow_f315.ko").read_bytes()
    contract.pinned(qdrv, contract.QDRV_SHA256, "F315 qdrv")
    contract.pinned(provider, contract.PROVIDER_SHA256, "F315 provider")
    actual_helpers = {p.relative_to(args.overlay).as_posix() for p in args.overlay.rglob("*") if p.is_file() or p.is_symlink()}
    if actual_helpers != set(HELPERS):
        raise ValueError("F322 helper overlay must not contain radio controls or UI")
    inputs = json.loads(args.helper_hashes)
    helpers = {}
    for path in HELPERS:
        item = args.overlay / path
        if item.is_symlink():
            raise ValueError("symlink in F322 helper overlay")
        helpers[path] = item.read_bytes()
        contract.pinned(helpers[path], inputs[path], "F322 " + path)
    if args.image.exists() or args.result.exists():
        raise ValueError("refusing to overwrite F322 worker outputs")
    with tempfile.TemporaryDirectory(prefix="f322-shadow-rootfs-", dir="/tmp") as directory:
        scratch = Path(directory)
        root, packed, verified = scratch / "rootfs", scratch / "packed.squashfs", scratch / "verified"
        subprocess.run(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(root), str(args.source)], check=True, stdout=subprocess.DEVNULL)
        before = web.inventory(root)
        changes = {
            contract.API_PATH: (contract.api_bytes((root / contract.API_PATH).read_bytes()), 0o755),
            contract.START_PATH: (contract.start_bytes((root / contract.START_PATH).read_bytes(), donor), 0o755),
            contract.RELEASE_PATH: (contract.release_bytes((root / contract.RELEASE_PATH).read_bytes(), args.build_id), 0o644),
            contract.ARTIFACTS_PATH: (contract.artifacts_bytes((root / contract.ARTIFACTS_PATH).read_bytes()), 0o644),
            contract.DRIVER_CONTRACT_PATH: (contract.driver_contract_bytes((root / contract.DRIVER_CONTRACT_PATH).read_bytes()), 0o644),
            contract.QDRV_PATH: (qdrv, 0o644), contract.PROVIDER_PATH: (provider, 0o644),
            **{path: (content, 0o755) for path, content in helpers.items()},
        }
        expected = {path: put(root, path, content, mode) for path, (content, mode) in changes.items()}
        web.validate_delta(before, web.inventory(root), expected)
        web.check_legacy_asset_metadata(root)
        subprocess.run(["mksquashfs", str(root), str(packed), "-noappend", "-all-root", "-comp", "xz", "-b", "131072",
                        "-no-xattrs", "-no-exports", "-all-time", str(args.epoch), "-mkfs-time", str(args.epoch),
                        "-processors", "1", "-no-progress"], check=True, stdout=subprocess.DEVNULL)
        subprocess.run(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(verified), str(packed)], check=True, stdout=subprocess.DEVNULL)
        after = web.inventory(verified)
        checks = web.validate_delta(before, after, expected)
        web.check_legacy_asset_metadata(verified)
        for path in ["etc/lyoko/frontend.env", "etc/lyoko/web-next.json", "etc/lyoko/web-next.env", "usr/sbin/om-qtnctl", "www/dashboard.cgi"]:
            if before[path] != after[path]:
                raise ValueError("F322 modified a protected F321 entry: " + path)
        shutil.copyfile(packed, args.image)
        args.result.write_text(json.dumps({"before": before, "after": after, "checks": checks, "expected_changes": expected}, sort_keys=True) + "\n", encoding="ascii")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "overlay", "donor-start", "module-dir", "image", "result"):
        parser.add_argument("--" + name, required=True, type=Path)
    parser.add_argument("--helper-hashes", required=True)
    parser.add_argument("--build-id", required=True)
    parser.add_argument("--epoch", required=True, type=int)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
