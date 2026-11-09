#!/usr/bin/env python3
"""Two native, temporary rootfs builds: classic UI plus qualified TLS delta.

No webformat, deployable firmware, router access, UART or flash operation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path, PurePosixPath
import stat
import subprocess
import tempfile

from build_minihttpd_wolfssl_trial import HOST_REPORT_SHA, QUALIFIED_SOURCE_SHA, LEGACY_BINARY_SHA
from lyoko_https_profile import BINARY_PATH, CONFIG_PATH, digest, modernize_config
from lyoko_web_rootfs_worker import (
    sha256, inventory, validate_overlay, apply_overlay, apply_identity_transform,
    check_legacy_asset_metadata, validate_delta,
)
from verify_lyoko_https_profile import ARC_BINARY_SHA


def replace_payload(root: Path, relative: str, data: bytes, mode: int) -> dict:
    if {BINARY_PATH: 0o755, CONFIG_PATH: 0o644}.get(relative) != mode:
        raise ValueError("TLS payload target or mode is outside the two-file delta")
    current = root
    for component in PurePosixPath(relative).parts:
        current /= component
        if current.is_symlink(): raise ValueError("TLS payload path crosses a symlink")
    info = current.lstat()
    if not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != mode or info.st_uid or info.st_gid:
        raise ValueError("TLS payload baseline metadata differs")
    with tempfile.NamedTemporaryFile(dir=current.parent, delete=False) as stream:
        temporary = Path(stream.name); stream.write(data)
    try:
        temporary.chmod(mode); os.chown(temporary, 0, 0); temporary.replace(current)
    finally:
        temporary.unlink(missing_ok=True)
    return {"path": relative, "mode": f"{mode:04o}", "bytes": len(data), "sha256": digest(data)}


def command(argv):
    subprocess.run(argv, check=True, stdout=subprocess.DEVNULL, timeout=180)


def linux_worker(args):
    from verify_lyoko_web_next_f314_rootfs import BASES, ROOTFS_WINDOW_BYTES, SOURCE_DATE_EPOCH
    if os.name != "posix" or os.geteuid() != 0: raise ValueError("native Linux root required")
    if sha256(args.rootfs) != BASES[args.base]["sha256"]: raise ValueError("base rootfs changed")
    if args.report.exists(): raise ValueError("refusing to overwrite rootfs evidence")
    if sha256(args.host_report) != HOST_REPORT_SHA: raise ValueError("host qualification changed")
    host = json.loads(args.host_report.read_text())
    manifest_path = args.package / "manifest.json"
    if sha256(manifest_path) != host["package_manifest_sha256"]: raise ValueError("UI package changed")
    manifest = json.loads(manifest_path.read_text())
    expected_ui = validate_overlay(args.package / "overlay", manifest)
    tls_binary = (args.arc_trial / "mini_httpd-wolfssl").read_bytes()
    if digest(tls_binary) != ARC_BINARY_SHA: raise ValueError("qualified ARC binary changed")
    arc = json.loads((args.arc_trial / "manifest.json").read_text())
    if (arc["adapted_source_sha256"] != QUALIFIED_SOURCE_SHA or arc["binary_sha256"] != ARC_BINARY_SHA
            or arc["host_qualification_sha256"] != HOST_REPORT_SHA):
        raise ValueError("ARC qualification chain changed")
    config_report_path = args.config_trial / "manifest.json"
    config_report = json.loads(config_report_path.read_text())
    tls_config = (args.config_trial / "minihttpd-https.conf").read_bytes()
    if (config_report["status"] != "PASS" or config_report["base"] != args.base
            or config_report["arc_binary_sha256"] != ARC_BINARY_SHA
            or config_report["rootfs_sha256"] != BASES[args.base]["sha256"]
            or config_report["fixed_config_sha256"] != digest(tls_config)
            or config_report["package_manifest_sha256"] != host["package_manifest_sha256"]
            or config_report["host_qualification_sha256"] != HOST_REPORT_SHA):
        raise ValueError("HTTPS config qualification differs")
    if any(len(config_report["tests"].get(name, [])) != 22
           or any(row["status"] != "PASS" for row in config_report["tests"][name])
           for name in ("TLS1.2", "TLS1.3")):
        raise ValueError("HTTPS configuration test set incomplete")
    builds = []
    first_after = None
    with tempfile.TemporaryDirectory(prefix="lyoko-ui-tls-rootfs-", dir="/tmp") as directory:
        scratch = Path(directory)
        for name in ("a", "b"):
            root, packed, unpacked = scratch / (name + "-root"), scratch / (name + ".squashfs"), scratch / (name + "-verified")
            command(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(root), str(args.rootfs)])
            before = inventory(root)
            if before[BINARY_PATH]["sha256"] != LEGACY_BINARY_SHA: raise ValueError("old TLS binary differs")
            if modernize_config((root / CONFIG_PATH).read_bytes()) != tls_config: raise ValueError("config delta changed")
            apply_overlay(root, args.package / "overlay", expected_ui)
            transformed, audits = apply_identity_transform(root, manifest)
            expected = {**expected_ui, **transformed}
            expected[BINARY_PATH] = replace_payload(root, BINARY_PATH, tls_binary, 0o755)
            expected[CONFIG_PATH] = replace_payload(root, CONFIG_PATH, tls_config, 0o644)
            check_legacy_asset_metadata(root)
            validate_delta(before, inventory(root), expected)
            command(["mksquashfs", str(root), str(packed), "-noappend", "-all-root", "-comp", "xz", "-b", "131072",
                     "-no-xattrs", "-no-exports", "-all-time", str(SOURCE_DATE_EPOCH), "-mkfs-time", str(SOURCE_DATE_EPOCH),
                     "-processors", "1", "-no-progress"])
            command(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(unpacked), str(packed)])
            after = inventory(unpacked)
            checks = validate_delta(before, after, expected)
            if first_after is not None and first_after != after: raise ValueError("repeated rootfs inventory differs")
            first_after = after
            builds.append({"name": name, "bytes": packed.stat().st_size, "sha256": sha256(packed)})
        if builds[0]["sha256"] != builds[1]["sha256"]: raise ValueError("UI/TLS rootfs not reproducible")
        if builds[0]["bytes"] > ROOTFS_WINDOW_BYTES: raise ValueError("UI/TLS rootfs exceeds slot budget")
        protected = list(BASES[args.base]["protected"])
        protected += sorted(path for path in before if path.startswith(("etc/init.d/", "lib/modules/", "lib/firmware/")))
        protected = sorted(set(protected) - set(transformed))
        if any(before.get(path) != after.get(path) for path in protected): raise ValueError("protected runtime changed")
        report = {
            "schema": "lyoko.ui-tls-native-rootfs/v1", "status": "PASS", "base": args.base,
            "base_rootfs_sha256": BASES[args.base]["sha256"], "ui_manifest_sha256": sha256(manifest_path),
            "tls_arc_binary_sha256": ARC_BINARY_SHA, "tls_config_sha256": digest(tls_config),
            "config_qualification_sha256": sha256(config_report_path), "host_qualification_sha256": HOST_REPORT_SHA,
            "builds": builds, "reproducible": True, "metadata_checks": checks,
            "protected_runtime_files": protected, "transforms": audits,
            "rootfs_window_bytes": ROOTFS_WINDOW_BYTES, "rootfs_headroom_bytes": ROOTFS_WINDOW_BYTES - builds[0]["bytes"],
            "validation_scope": "all native extracted entries: bytes, uid/gid, modes, directories, symlinks and hardlinks",
            "hardware_actions": False, "deployable_firmware_generated": False, "temporary_rootfs_retained": False,
            "release_eligible": False, "flash_supported": False,
            "not_proven": ["ARC TLS runtime", "device memory/CPU/entropy", "physical platform and dual-radio regression"],
        }
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps({"status": "PASS", "base": args.base, "bytes": builds[0]["bytes"],
                      "headroom": report["rootfs_headroom_bytes"], "sha256": builds[0]["sha256"],
                      "changed_files": checks["changed_files"], "report": str(args.report)}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", choices=("f314", "f317"), default="f314")
    parser.add_argument("--report", type=Path); parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--linux-worker", action="store_true", help=argparse.SUPPRESS)
    for name in ("rootfs", "package", "host-report", "arc-trial", "config-trial"):
        parser.add_argument("--" + name, type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.linux_worker: linux_worker(args)
    else:
        import shlex
        from verify_lyoko_web_next_f314_rootfs import ROOT, BASES
        from package_lyoko_web_next import default_package_dir
        from build_f306_unified_product_from_f305 import run_wsl, wsl_path
        report = (args.report or ROOT / f"outputs/userland/ui-tls-rootfs-{args.base}.json").resolve()
        command = ["python3", wsl_path(Path(__file__).resolve()), "--linux-worker", "--base", args.base,
                   "--report", wsl_path(report), "--rootfs", wsl_path(BASES[args.base]["rootfs"]),
                   "--package", wsl_path(default_package_dir()),
                   "--host-report", wsl_path(ROOT / "outputs/userland/wolfssl-https-host-qualification/manifest.json"),
                   "--arc-trial", wsl_path(ROOT / "outputs/userland/minihttpd-wolfssl-5.9.2-arc700-cgi-tls-trial"),
                   "--config-trial", wsl_path(ROOT / f"outputs/userland/https-config-{args.base}-qualification")]
        print(run_wsl(shlex.join(command), args.distro, timeout=600))


if __name__ == "__main__": main()
