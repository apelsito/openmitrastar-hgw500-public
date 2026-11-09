#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OVERLAY = ROOT / "work/mission-state/router-lyoko-v0"
INTEGRATOR = ROOT / "tools/integrate_router_lyoko_overlay.py"

EXPECTED_WEB_FILES = (
    "api/lyoko",
    "api/lyoko-control",
    "lyoko.html",
    "lyoko.css",
    "lyoko.js",
)

FORBIDDEN = (
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


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def refresh_manifest_entry(overlay: Path, rel: str) -> None:
    manifest_path = overlay / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    path = overlay / Path(*rel.split("/"))
    payload = path.read_bytes()
    manifest["files"][rel] = {"bytes": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    lines = [f"{meta['sha256']}  {entry}" for entry, meta in manifest["files"].items()]
    (overlay / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_integrator(rootfs: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(INTEGRATOR),
            "--rootfs",
            str(rootfs),
            *extra,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoIntegratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((OVERLAY / "manifest.json").read_text(encoding="utf-8"))

    def assert_web_root_has_overlay(self, web_root: Path):
        for rel in EXPECTED_WEB_FILES:
            dst = web_root / rel
            src = OVERLAY / "rootfs" / "var" / "www" / rel
            self.assertTrue(dst.is_file(), rel)
            self.assertEqual(sha256_file(dst), sha256_file(src), rel)
        if os.name != "nt":
            for rel in ("api/lyoko", "api/lyoko-control"):
                dst = web_root / rel
                self.assertTrue(dst.stat().st_mode & 0o111, rel)

    def assert_report_marks_cgi_executable(self, report: dict):
        by_name = {
            Path(item["destination"]).as_posix().split("/")[-2:][0] + "/" + Path(item["destination"]).name: item
            for item in report["files"]
            if Path(item["destination"]).name in {"lyoko", "lyoko-control"}
        }
        self.assertEqual(by_name["api/lyoko"]["intended_mode"], "0755")
        self.assertEqual(by_name["api/lyoko-control"]["intended_mode"], "0755")

    def test_integrates_into_var_www_rootfs(self):
        with tempfile.TemporaryDirectory() as td:
            rootfs = Path(td)
            (rootfs / "var/www").mkdir(parents=True)
            proc = run_integrator(rootfs)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertTrue(report["ok"])
            self.assertEqual(report["web_roots"], [str((rootfs / "var/www").resolve())])
            self.assert_report_marks_cgi_executable(report)
            self.assert_web_root_has_overlay(rootfs / "var/www")

    def test_integrates_into_www_rootfs(self):
        with tempfile.TemporaryDirectory() as td:
            rootfs = Path(td)
            (rootfs / "www").mkdir(parents=True)
            proc = run_integrator(rootfs)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertTrue(report["ok"])
            self.assertEqual(report["web_roots"], [str((rootfs / "www").resolve())])
            self.assert_report_marks_cgi_executable(report)
            self.assert_web_root_has_overlay(rootfs / "www")

    def test_integrates_into_both_web_roots_when_present(self):
        with tempfile.TemporaryDirectory() as td:
            rootfs = Path(td)
            (rootfs / "var/www").mkdir(parents=True)
            (rootfs / "www").mkdir(parents=True)
            proc = run_integrator(rootfs)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            report = json.loads(proc.stdout)
            self.assertEqual(len(report["web_roots"]), 2)
            self.assert_report_marks_cgi_executable(report)
            self.assert_web_root_has_overlay(rootfs / "var/www")
            self.assert_web_root_has_overlay(rootfs / "www")

    def test_create_var_www_for_fresh_ram_staging_rootfs(self):
        with tempfile.TemporaryDirectory() as td:
            rootfs = Path(td)
            proc = run_integrator(rootfs, "--create-var-www")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assert_report_marks_cgi_executable(json.loads(proc.stdout))
            self.assert_web_root_has_overlay(rootfs / "var/www")

    def test_dry_run_does_not_copy(self):
        with tempfile.TemporaryDirectory() as td:
            rootfs = Path(td)
            (rootfs / "var/www").mkdir(parents=True)
            proc = run_integrator(rootfs, "--dry-run")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertFalse((rootfs / "var/www/lyoko.html").exists())
            report = json.loads(proc.stdout)
            self.assertTrue(all(item["status"] == "would-copy" for item in report["files"]))

    def test_refuses_different_existing_file_without_force(self):
        with tempfile.TemporaryDirectory() as td:
            rootfs = Path(td)
            (rootfs / "var/www").mkdir(parents=True)
            (rootfs / "var/www/lyoko.html").write_text("not lyoko\n", encoding="utf-8")
            proc = run_integrator(rootfs)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("destination differs", proc.stderr)

    def test_force_replaces_different_existing_file(self):
        with tempfile.TemporaryDirectory() as td:
            rootfs = Path(td)
            (rootfs / "var/www").mkdir(parents=True)
            (rootfs / "var/www/lyoko.html").write_text("not lyoko\n", encoding="utf-8")
            proc = run_integrator(rootfs, "--force")
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assert_report_marks_cgi_executable(json.loads(proc.stdout))
            self.assert_web_root_has_overlay(rootfs / "var/www")

    def test_already_present_control_api_gets_executable_mode_fixed(self):
        with tempfile.TemporaryDirectory() as td:
            rootfs = Path(td)
            api_dir = rootfs / "var/www/api"
            api_dir.mkdir(parents=True)
            src = OVERLAY / "rootfs/var/www/api/lyoko-control"
            dst = api_dir / "lyoko-control"
            dst.write_bytes(src.read_bytes())
            dst.chmod(0o644)
            proc = run_integrator(rootfs)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assert_report_marks_cgi_executable(json.loads(proc.stdout))
            self.assertEqual(sha256_file(dst), sha256_file(src))
            if os.name != "nt":
                self.assertTrue(dst.stat().st_mode & 0o111)

    def test_copied_overlay_has_no_forbidden_control_surface(self):
        with tempfile.TemporaryDirectory() as td:
            rootfs = Path(td)
            (rootfs / "var/www").mkdir(parents=True)
            proc = run_integrator(rootfs)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = "\n".join(
                p.read_text(encoding="utf-8", errors="ignore")
                for p in (rootfs / "var/www").rglob("*")
                if p.is_file()
            )
            for token in FORBIDDEN:
                self.assertNotIn(token, text, token)

    def test_refuses_self_consistent_but_stale_static_truth(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            stale_overlay = temp / "router-lyoko-v0"
            rootfs = temp / "rootfs"
            shutil.copytree(OVERLAY, stale_overlay)
            (rootfs / "var/www").mkdir(parents=True)
            rel = "rootfs/var/www/lyoko-data/mission-truth.json"
            (stale_overlay / Path(*rel.split("/"))).write_text(
                '{"schema":"router-lyoko.truth/v1","stale":true}\n',
                encoding="utf-8",
            )
            refresh_manifest_entry(stale_overlay, rel)
            proc = run_integrator(rootfs, "--overlay", str(stale_overlay))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("static Lyoko truth is stale", proc.stderr)
            self.assertFalse((rootfs / "var/www/lyoko.html").exists())

    def test_refuses_secret_material_before_copy(self):
        with tempfile.TemporaryDirectory() as td:
            temp = Path(td)
            secret_overlay = temp / "router-lyoko-v0"
            rootfs = temp / "rootfs"
            shutil.copytree(OVERLAY, secret_overlay)
            (rootfs / "var/www").mkdir(parents=True)
            rel = "rootfs/var/www/lyoko.js"
            target = secret_overlay / Path(*rel.split("/"))
            target.write_text(
                target.read_text(encoding="utf-8")
                + "\nwindow.__lyoko_test = { password: 'router-lab-secret-1234' };\n",
                encoding="utf-8",
            )
            refresh_manifest_entry(secret_overlay, rel)
            proc = run_integrator(rootfs, "--overlay", str(secret_overlay))
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("Lyoko web overlay contains secret material", proc.stderr)
            self.assertNotIn("router-lab-secret-1234", proc.stderr)
            self.assertFalse((rootfs / "var/www/lyoko.html").exists())


if __name__ == "__main__":
    unittest.main()
