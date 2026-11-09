#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/package_router_lyoko_overlay.py"
OVERLAY = ROOT / "work/mission-state/router-lyoko-v0"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def refresh_manifest_entry(overlay: Path, rel: str) -> None:
    manifest_path = overlay / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    path = overlay / Path(*rel.split("/"))
    payload = path.read_bytes()
    manifest["files"][rel] = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [f"{meta['sha256']}  {entry}" for entry, meta in manifest["files"].items()]
    (overlay / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


class RouterLyokoOverlayPackageTests(unittest.TestCase):
    def test_dry_run_reports_no_flash_package(self):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--dry-run"],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertEqual(
            report["classification"],
            "READ-ONLY-LAB-OVERLAY-PACKAGE-NO-FLASH",
        )
        self.assertTrue(report["dry_run"])
        self.assertFalse(report["guards"]["flash_candidate"])

    def test_package_is_reproducible_and_contains_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            one = Path(td) / "one.tar.gz"
            two = Path(td) / "two.tar.gz"
            one_manifest = Path(td) / "one.json"
            two_manifest = Path(td) / "two.json"
            for archive, manifest in ((one, one_manifest), (two, two_manifest)):
                proc = subprocess.run(
                    [
                        sys.executable,
                        str(SCRIPT),
                        "--output",
                        str(archive),
                        "--package-manifest",
                        str(manifest),
                    ],
                    cwd=ROOT,
                    text=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    check=False,
                )
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                report = json.loads(proc.stdout)
                self.assertEqual(report["archive"]["sha256"], sha256(archive))
                self.assertEqual(report["archive"]["bytes"], archive.stat().st_size)

            self.assertEqual(sha256(one), sha256(two))
            manifest = json.loads(one_manifest.read_text(encoding="utf-8"))
            self.assertEqual(manifest["archive"]["sha256"], sha256(one))
            with tarfile.open(one, "r:gz") as archive:
                names = archive.getnames()
            self.assertIn("router-lyoko-v0/manifest.json", names)
            self.assertIn("router-lyoko-v0/SHA256SUMS", names)
            self.assertIn("router-lyoko-v0/rootfs/var/www/api/lyoko", names)
            self.assertIn("router-lyoko-v0/rootfs/var/www/api/lyoko-control", names)
            self.assertIn("router-lyoko-v0/rootfs/var/www/lyoko-data/mission-truth.json", names)
            self.assertFalse(any(name.startswith("/") or "/../" in name for name in names))
            with tarfile.open(one, "r:gz") as archive:
                lyoko = archive.getmember("router-lyoko-v0/rootfs/var/www/api/lyoko")
                lyoko_control = archive.getmember("router-lyoko-v0/rootfs/var/www/api/lyoko-control")
            self.assertEqual(lyoko.mode & 0o777, 0o755)
            self.assertEqual(lyoko_control.mode & 0o777, 0o755)

    def test_archive_covers_manifest_files(self):
        with tempfile.TemporaryDirectory() as td:
            archive_path = Path(td) / "overlay.tar.gz"
            manifest_path = Path(td) / "package-manifest.json"
            subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--output",
                    str(archive_path),
                    "--package-manifest",
                    str(manifest_path),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=True,
            )
            overlay_manifest = json.loads((OVERLAY / "manifest.json").read_text(encoding="utf-8"))
            with tarfile.open(archive_path, "r:gz") as archive:
                names = set(archive.getnames())
            for rel in overlay_manifest["files"]:
                self.assertIn(f"router-lyoko-v0/{rel}", names)

    def test_package_refuses_self_consistent_but_stale_static_truth(self):
        with tempfile.TemporaryDirectory() as td:
            stale_overlay = Path(td) / "router-lyoko-v0"
            shutil.copytree(OVERLAY, stale_overlay)
            rel = "rootfs/var/www/lyoko-data/mission-truth.json"
            (stale_overlay / Path(*rel.split("/"))).write_text(
                '{"schema":"router-lyoko.truth/v1","stale":true}\n',
                encoding="utf-8",
            )
            refresh_manifest_entry(stale_overlay, rel)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--overlay",
                    str(stale_overlay),
                    "--output",
                    str(Path(td) / "stale.tar.gz"),
                    "--package-manifest",
                    str(Path(td) / "stale-package.json"),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("static Lyoko truth is stale", proc.stderr)

    def test_package_refuses_secret_material_in_web_overlay(self):
        with tempfile.TemporaryDirectory() as td:
            secret_overlay = Path(td) / "router-lyoko-v0"
            shutil.copytree(OVERLAY, secret_overlay)
            rel = "rootfs/var/www/lyoko.js"
            target = secret_overlay / Path(*rel.split("/"))
            target.write_text(
                target.read_text(encoding="utf-8")
                + "\nwindow.__lyoko_test = { wpa_psk: 'router-lab-secret-1234' };\n",
                encoding="utf-8",
            )
            refresh_manifest_entry(secret_overlay, rel)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--overlay",
                    str(secret_overlay),
                    "--output",
                    str(Path(td) / "secret.tar.gz"),
                    "--package-manifest",
                    str(Path(td) / "secret-package.json"),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Lyoko web overlay contains secret material", proc.stderr)
            self.assertNotIn("router-lab-secret-1234", proc.stderr)

    def test_package_refuses_missing_objective_surface(self):
        with tempfile.TemporaryDirectory() as td:
            incomplete_overlay = Path(td) / "router-lyoko-v0"
            shutil.copytree(OVERLAY, incomplete_overlay)
            rel = "rootfs/var/www/lyoko.html"
            target = incomplete_overlay / Path(*rel.split("/"))
            target.write_text(
                target.read_text(encoding="utf-8").replace('id="runtime-clients"', 'id="runtime-clients-missing"', 1),
                encoding="utf-8",
            )
            refresh_manifest_entry(incomplete_overlay, rel)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--overlay",
                    str(incomplete_overlay),
                    "--output",
                    str(Path(td) / "incomplete.tar.gz"),
                    "--package-manifest",
                    str(Path(td) / "incomplete-package.json"),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("objective coverage guard failed", proc.stderr)
            self.assertIn("missing_html_surface", proc.stderr)

    def test_package_refuses_unsafe_telemetry_contract(self):
        with tempfile.TemporaryDirectory() as td:
            unsafe_overlay = Path(td) / "router-lyoko-v0"
            shutil.copytree(OVERLAY, unsafe_overlay)
            rel = "telemetry-contract.json"
            target = unsafe_overlay / rel
            payload = json.loads(target.read_text(encoding="utf-8"))
            payload["safety"]["flash_write"] = True
            target.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            refresh_manifest_entry(unsafe_overlay, rel)
            proc = subprocess.run(
                [
                    sys.executable,
                    str(SCRIPT),
                    "--overlay",
                    str(unsafe_overlay),
                    "--output",
                    str(Path(td) / "unsafe-telemetry.tar.gz"),
                    "--package-manifest",
                    str(Path(td) / "unsafe-telemetry-package.json"),
                ],
                cwd=ROOT,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("telemetry contract guard failed", proc.stderr)
            self.assertIn("safety flag must be false: flash_write", proc.stderr)


if __name__ == "__main__":
    unittest.main()
