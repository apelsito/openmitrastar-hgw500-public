#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools/verify_router_lyoko_served_files.py"
WEB_ROOT = ROOT / "work/mission-state/router-lyoko-v0/rootfs/var/www"
MANIFEST = ROOT / "work/mission-state/router-lyoko-v0/manifest.json"


def run_verifier(base_dir: Path, manifest: Path = MANIFEST) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            str(VERIFIER),
            "--manifest",
            str(manifest),
            "--base-dir",
            str(base_dir),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


class RouterLyokoServedFilesVerifierTests(unittest.TestCase):
    def test_accepts_current_local_web_root_against_manifest(self) -> None:
        proc = run_verifier(WEB_ROOT)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertEqual(report["classification"], "READONLY-SERVED-WEB-FILES-VERIFY-NO-CONTROL")
        self.assertGreaterEqual(report["files_checked"], 3)
        ids = {check["id"] for check in report["checks"]}
        self.assertIn("served./lyoko.html.sha256", ids)
        self.assertIn("served./lyoko.css.sha256", ids)
        self.assertIn("served./lyoko.js.sha256", ids)
        self.assertIn("served./lyoko-data/index.json.sha256", ids)
        self.assertIn("served./lyoko-data/safe-mode.json.tx11_command_boot_evidence_json", ids)
        self.assertIn("served./lyoko.js.fetches_safe_mode_contract", ids)

    def test_rejects_corrupt_served_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "www"
            shutil.copytree(WEB_ROOT, clone)
            (clone / "lyoko.js").write_text("/* stale xana drift */\n", encoding="utf-8")

            proc = run_verifier(clone)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            failing = {check["id"] for check in report["checks"] if not check["ok"]}
            self.assertIn("served./lyoko.js.sha256", failing)

    def test_rejects_missing_served_file(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            clone = Path(td) / "www"
            shutil.copytree(WEB_ROOT, clone)
            (clone / "lyoko.html").unlink()

            proc = run_verifier(clone)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            failing = {check["id"] for check in report["checks"] if not check["ok"]}
            self.assertIn("served./lyoko.html.present", failing)

    def test_rejects_served_safe_mode_without_recovery_result_even_if_manifest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            clone = root / "www"
            shutil.copytree(WEB_ROOT, clone)
            safe_mode = json.loads((clone / "lyoko-data" / "safe-mode.json").read_text(encoding="utf-8"))
            for step in safe_mode["operator_sequence"]:
                if step["id"] == "tx11-2g-client-gate-plan":
                    step.pop("requires_tx11_boot_evidence_json", None)
                    step.pop("tx11_boot_evidence_json", None)
                    step["display_command"] = "powershell -NoProfile -ExecutionPolicy Bypass -File .\\tools\\run_w2_2g_tx11_gate.ps1"
            safe_mode_path = clone / "lyoko-data" / "safe-mode.json"
            safe_mode_path.write_text(json.dumps(safe_mode, indent=2), encoding="utf-8")

            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            rel = "rootfs/var/www/lyoko-data/safe-mode.json"
            data = safe_mode_path.read_bytes()
            manifest["files"][rel] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            proc = run_verifier(clone, manifest_path)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            failing = {check["id"] for check in report["checks"] if not check["ok"]}
            self.assertIn("served./lyoko-data/safe-mode.json.tx11_requires_boot_evidence_json", failing)
            self.assertIn("served./lyoko-data/safe-mode.json.tx11_command_boot_evidence_json", failing)

    def test_rejects_served_js_that_does_not_fetch_safe_mode_even_if_manifest_matches(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            clone = root / "www"
            shutil.copytree(WEB_ROOT, clone)
            js_path = clone / "lyoko.js"
            js_path.write_text(
                "function renderLabConsole(){return 'Tx11BootEvidenceJson w2-tx11-green-boot-controls-boot-evidence-latest.json';}\n",
                encoding="utf-8",
            )

            manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
            rel = "rootfs/var/www/lyoko.js"
            data = js_path.read_bytes()
            manifest["files"][rel] = {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            manifest_path = root / "manifest.json"
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            proc = run_verifier(clone, manifest_path)
            self.assertNotEqual(proc.returncode, 0)
            report = json.loads(proc.stdout)
            failing = {check["id"] for check in report["checks"] if not check["ok"]}
            self.assertIn("served./lyoko.js.fetches_safe_mode_contract", failing)

    def test_source_is_read_only_and_has_no_hardware_mutation_commands(self) -> None:
        source = VERIFIER.read_text(encoding="utf-8")
        self.assertIn("urllib.request.Request", source)
        self.assertIn("method=\"GET\"", source)
        self.assertIn("READONLY-SERVED-WEB-FILES-VERIFY-NO-CONTROL", source)
        for forbidden in (
            "ramssh_exec.py",
            "flash_erase",
            "mtd_debug",
            "fw_setenv",
            "saveenv",
            "reboot -f",
            "COM3",
            "mode COM",
            "bootm",
            "ATGO",
        ):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main()
