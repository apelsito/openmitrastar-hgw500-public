#!/usr/bin/env python3
"""Verify a UI delta against pinned rootfs images, including native metadata."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shlex
import tempfile

import build_f306_unified_product_from_f305 as f306
from lyoko_web_rootfs_worker import validate_overlay
from package_lyoko_web_next import default_package_dir


ROOT = Path(__file__).resolve().parents[1]
DEVICE_ROOT = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary"
ROOTFS_WINDOW_BYTES = 0x460000
SOURCE_DATE_EPOCH = 1788566400
COMMON_PROTECTED = (
    "usr/libexec/openmitrastar/om-oem-cgi",
    "usr/libexec/openmitrastar/om-api-v1",
    "www/dashboard.cgi",
    "www/index.cgi",
    "www/login.html",
    "www/login.css",
    "usr/sbin/om-radioctl",
    "usr/sbin/om-qtnctl",
)
BASES = {
    "f314": {
        "rootfs": DEVICE_ROOT / "firmware/f314-device-bound/openmitrastar-linux510-f314-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.rootfs.squashfs",
        "sha256": "ee2c7a63ee738382ba8eaf813cfd725e64e52ce0686bfbf83129a78dcf323cce",
        "protected": COMMON_PROTECTED,
    },
    "f317": {
        "rootfs": DEVICE_ROOT / "firmware/f317-device-bound/openmitrastar-linux510-f317-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.rootfs.squashfs",
        "sha256": "7adb94770d6633782d9aa6eb13b0b3e298b30c84f046d2442a239f7e8fb1ec32",
        "protected": COMMON_PROTECTED + (
            "etc/init.d/S89-radiod",
            "etc/lyoko/radiod/hgw500bna-qcv2.profile",
            "usr/bin/hgw500-radiod-adapter",
            "usr/bin/lyoko-radiod",
            "usr/sbin/om-radiod-status",
            "usr/sbin/om-radiod-supervisor",
            "usr/share/lyoko/boards/hgw500bna-qcv2.json",
            "usr/share/lyoko/boards/schema.json",
        ),
    },
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build_once(source: Path, source_hash: str, overlay: Path, manifest: Path,
               manifest_hash: str, target: Path, result: Path, distro: str) -> dict:
    worker = ROOT / "tools/lyoko_web_rootfs_worker.py"
    argv = ["python3", f306.wsl_path(worker), "--source", f306.wsl_path(source),
            "--source-sha256", source_hash, "--overlay", f306.wsl_path(overlay),
            "--manifest", f306.wsl_path(manifest), "--manifest-sha256", manifest_hash,
            "--image", f306.wsl_path(target), "--result", f306.wsl_path(result),
            "--epoch", str(SOURCE_DATE_EPOCH)]
    f306.run_wsl(shlex.join(argv), distro)
    return json.loads(result.read_text(encoding="ascii"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", choices=tuple(BASES), default="f314")
    parser.add_argument("--package", type=Path)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    args = parser.parse_args()

    package = (args.package or default_package_dir()).resolve()
    base = BASES[args.base]
    source_rootfs = Path(base["rootfs"])
    expected_rootfs_sha256 = str(base["sha256"])
    overlay = package / "overlay"
    manifest_path = package / "manifest.json"
    report_path = (args.report or package / f"rootfs-integration-native-{args.base}.json").resolve()
    if report_path.exists():
        raise SystemExit(f"refusing to overwrite report: {report_path}")
    if sha256(source_rootfs) != expected_rootfs_sha256:
        raise SystemExit(f"exact {args.base.upper()} rootfs hash mismatch")
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    expected_changes = set(validate_overlay(overlay, manifest))
    expected_changes.update(spec["path"] for spec in manifest.get("transforms", []))
    manifest_hash = sha256(manifest_path)

    with tempfile.TemporaryDirectory(prefix="lyoko-next-f314-rootfs-") as directory:
        scratch = Path(directory)
        builds = []
        baseline_result = None
        for name in ("a", "b"):
            target = scratch / f"lyoko-next-{name}.squashfs"
            worker_result = build_once(source_rootfs, expected_rootfs_sha256, overlay,
                                       manifest_path, manifest_hash, target,
                                       scratch / f"inventory-{name}.json", args.distro)
            builds.append({"name": name, "bytes": target.stat().st_size, "sha256": sha256(target)})
            if name == "a":
                baseline_result = worker_result
            elif worker_result != baseline_result:
                raise SystemExit("packed metadata differs between independent builds")

        if builds[0]["sha256"] != builds[1]["sha256"] or builds[0]["bytes"] != builds[1]["bytes"]:
            raise SystemExit("Lyoko Next SquashFS is not reproducible")
        if int(builds[0]["bytes"]) > ROOTFS_WINDOW_BYTES:
            raise SystemExit("Lyoko Next SquashFS exceeds the F314 rootfs window")
        assert baseline_result is not None
        base_inventory = baseline_result["before"]
        final_inventory = baseline_result["after"]
        changed = baseline_result["checks"]["changed_files"]
        if not set(changed).issubset(expected_changes):
            raise SystemExit(f"unexpected rootfs delta: {sorted(set(changed) - expected_changes)}")

        protected = {}
        transformed_paths = {item["path"] for item in baseline_result.get("transforms", [])}
        for relative in base["protected"]:
            before = base_inventory.get(relative)
            after = final_inventory.get(relative)
            if relative in transformed_paths:
                continue  # Validated by the exact transform's before/after SHA-256.
            if before is None or before != after:
                raise SystemExit(f"protected runtime file changed: {relative}")
            protected[relative] = before

        report = {
            "schema": "openmitrastar.lyoko-web-next-rootfs-integration/v2",
            "status": "PASS",
            "source": {"firmware": args.base.upper(), "rootfs_sha256": expected_rootfs_sha256},
            "package": str(package),
            "release_eligible": False,
            "overlay_manifest_sha256": manifest_hash,
            "builds": builds,
            "reproducible": True,
            "rootfs_window_bytes": ROOTFS_WINDOW_BYTES,
            "rootfs_headroom_bytes": ROOTFS_WINDOW_BYTES - int(builds[0]["bytes"]),
            "changed_files": changed,
            "metadata_checks": baseline_result["checks"],
            "inventory_scope": "all entries after native Linux extraction of the produced SquashFS; modes, uid/gid, links and content",
            "protected_files": protected,
            "transformed_files": baseline_result.get("transforms", []),
            "authentication_contract": {
                "dashboard": "/dashboard.cgi",
                "internal_html": "/usr/share/openmitrastar/web/dashboard.html",
                "public_dashboard_html": False,
                "session": "OMSESSION",
                "verification": "CGI inherited; API changes restricted to pinned frontend identity transform; execution checked separately",
            },
            "ui_feature_parity": "NOT_VERIFIED",
            "hardware_actions": {"router": False, "ssh": False, "uart": False, "flash": False, "mtd": False},
            "firmware_generated": False,
        }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = report_path.with_suffix(report_path.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="ascii")
    temporary.replace(report_path)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
