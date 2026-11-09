#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
LOOP = ROOT / "tools" / "openmitrastar_realtek_loop.py"
POWERSHELL = ROOT / "tools" / "run_realtek_ram_probe.ps1"
BUILD = ROOT / "tools" / "build_realtek_8192ee_incremental.sh"
BUNDLE = (
    ROOT
    / "outputs"
    / "kernel-port"
    / "realtek-loop"
    / "current-RAM-ONLY-NO-FLASH"
)


def load_loop_module():
    spec = importlib.util.spec_from_file_location("openmitrastar_realtek_loop", LOOP)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RealtekLoopOfflineTests(unittest.TestCase):
    def test_bundle_integrity_and_classification(self) -> None:
        module = load_loop_module()
        manifest = module.load_and_validate_bundle(BUNDLE)
        self.assertEqual(manifest["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(manifest["candidate_eligible"])
        self.assertFalse(manifest["safety"]["flash_supported"])
        self.assertFalse(manifest["safety"]["persistent_writes_supported"])
        self.assertEqual(
            manifest["regulatory_database"],
            {
                "path": "firmware/regulatory.db",
                "sha256": "e9051546c38849b54e6b6a90ca32151c9e29f23edb7698f2c4a437fc353b3393",
                "install_before_module": "cfg80211.ko",
                "force_reg_after_load": False,
            },
        )

    def test_default_is_dry_run(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(LOOP)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("REALTEK_LOOP_DRY_RUN_BUNDLE_VALID=1", completed.stdout)
        self.assertIn("REALTEK_LOOP_DRY_RUN_PASS=1", completed.stdout)

    def test_ram_execution_without_ack_fails_closed(self) -> None:
        completed = subprocess.run(
            [sys.executable, str(LOOP), "--execute-ram"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 2)
        self.assertIn("requires exact --ack-ram-only", completed.stderr)

    def test_powershell_default_is_dry_run(self) -> None:
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(POWERSHELL),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("REALTEK_RAM_PROBE_DRY_RUN=1", completed.stdout)

    def test_offline_builder_has_no_network_fetch_command(self) -> None:
        code = "\n".join(
            line for line in BUILD.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertIsNone(
            re.search(r"\b(?:curl|wget|Invoke-WebRequest|requests)\b|https?://", code)
        )

    def test_ram_helper_has_no_persistent_write_primitive(self) -> None:
        code = "\n".join(
            line for line in POWERSHELL.read_text(encoding="utf-8").splitlines()
            if not line.lstrip().startswith("#")
        )
        self.assertIsNone(
            re.search(
                r"\bsaveenv\b|\bflash_erase\b|\bnand\s+write\b|"
                r"/dev/mtd|\bmtd_debug\b|\bfw_setenv\b",
                code,
                re.IGNORECASE,
            )
        )
        manifest = json.loads((BUNDLE / "manifest.json").read_text())
        self.assertFalse(manifest["safety"]["flash_supported"])

    def test_regdb_is_installed_before_cfg80211_without_forced_reg_change(self) -> None:
        code = POWERSHELL.read_text(encoding="utf-8")
        install = code.index(') "install-regdb-before-cfg80211"')
        module_loop = code.index("foreach ($module in $manifest.load_order)")
        self.assertLess(install, module_loop)
        self.assertIn("OMRTL_REGDB_ORDER_PASS=cfg80211-absent", code)
        self.assertIn("OMRTL_REGDB_INSTALLED_BEFORE_CFG80211=1", code)
        self.assertNotRegex(code, r"\biw\s+reg\s+set\b")
        manifest = json.loads((BUNDLE / "manifest.json").read_text())
        regdb = BUNDLE / "firmware" / "regulatory.db"
        self.assertTrue(regdb.is_file())
        self.assertEqual(
            manifest["regulatory_database"]["sha256"],
            __import__("hashlib").sha256(regdb.read_bytes()).hexdigest(),
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
