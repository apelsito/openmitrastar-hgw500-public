#!/usr/bin/env python3
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from contextlib import redirect_stdout
import hashlib
import io
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zlib


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_q1_mtd4_flash_one_shot.py"
BACKEND = ROOT / "tools/q1_mtd4_bootbase_flash.ps1"
SPEC = importlib.util.spec_from_file_location("q1_mtd4_flash", RUNNER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Q1Mtd4FlashOneShotTests(unittest.TestCase):
    def test_default_is_dry_run_and_never_flashes(self) -> None:
        proc = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMQ1_MTD4_FLASH_ONE_SHOT_DRY_RUN_PASS=1", proc.stdout)
        self.assertIn("flash=0", proc.stdout)

    def test_constants_pin_only_physical_mtd4_and_mtd3_rollback(self) -> None:
        self.assertEqual(0x007E0000, MODULE.TARGET_OFFSET)
        self.assertEqual(0x007A0000, MODULE.TARGET_BYTES)
        self.assertEqual(0x00040000, MODULE.ROLLBACK_OFFSET)
        self.assertEqual(0x007A0000, MODULE.ROLLBACK_BYTES)
        self.assertEqual("f1a40a5a87bf4262f8c0a3a39e6041d0f32d06794cf0302b470bfe98a50134b1",
                         MODULE.ROLLBACK_SHA256)
        self.assertEqual("ef928a82ffe27f9a8b982d8a361dc490b13c3639267cc941ba9571ecd1cb88c8",
                         MODULE.ROLLBACK_LOG_SHA256)
        self.assertEqual("bd473ef7f7238a5f9488e4739308615355c7e86526c5c867e16d3a232908c306",
                         MODULE.EXPECTED_SHA256)

    def test_full_slot_model_is_candidate_plus_erased_ff(self) -> None:
        candidate = b"Q1" * 100
        full = MODULE.full_slot_bytes(candidate)
        self.assertEqual(MODULE.TARGET_BYTES, len(full))
        self.assertEqual(candidate, full[:len(candidate)])
        self.assertEqual(b"\xff" * 128, full[-128:])
        self.assertEqual(zlib.crc32(full) & 0xFFFFFFFF, zlib.crc32(full) & 0xFFFFFFFF)

    def test_freshness_is_fail_closed(self) -> None:
        now = datetime.now(timezone.utc)
        age = MODULE.require_fresh((now - timedelta(minutes=10)).isoformat(), "test", 30, now)
        self.assertGreaterEqual(age, 9.9)
        with self.assertRaises(ValueError):
            MODULE.require_fresh((now - timedelta(minutes=31)).isoformat(), "test", 30, now)
        with self.assertRaises(ValueError):
            MODULE.require_fresh("not-a-time", "test", 30, now)

    def test_execute_requires_exact_ack_before_backend(self) -> None:
        proc = subprocess.run([sys.executable, str(RUNNER), "--execute", "--ack", "wrong"],
                              cwd=ROOT, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.PIPE, check=False)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn(MODULE.ACK, proc.stderr + proc.stdout)

    def test_execute_never_reaches_backend_when_local_gate_fails(self) -> None:
        argv = ["runner", "--execute", "--ack", MODULE.ACK, "--timeout", "600"]
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(MODULE, "validate_local_inputs", side_effect=ValueError("gate closed")), \
             mock.patch.object(MODULE, "execute_backend") as backend:
            with self.assertRaises(ValueError):
                MODULE.main()
            backend.assert_not_called()

    def test_execute_reaches_backend_only_after_local_and_strict_readiness_pass(self) -> None:
        argv = ["runner", "--execute", "--ack", MODULE.ACK, "--timeout", "600"]
        fake_preflight = {"candidate_sha256": MODULE.EXPECTED_SHA256}
        fake_result = {"result": {"status": "PASS"}, "result_path": "evidence/result.json"}
        with mock.patch.object(sys, "argv", argv), \
             mock.patch.object(MODULE, "validate_local_inputs", return_value=fake_preflight) as local, \
             mock.patch.object(MODULE, "run_readiness", return_value={"candidate_eligible": True}) as ready, \
             mock.patch.object(MODULE, "execute_backend", return_value=fake_result) as backend:
            with redirect_stdout(io.StringIO()):
                self.assertEqual(0, MODULE.main())
            local.assert_called_once()
            ready.assert_called_once()
            backend.assert_called_once()

    def test_backend_has_exact_order_and_no_environment_persistence(self) -> None:
        text = BACKEND.read_text(encoding="utf-8")
        pre_safety = text.index("fresh rollback read")
        pre_live = text.index("fresh current-live read")
        erase = text.index("'mtd4 erase'")
        write = text.index("'mtd4 candidate write'")
        readback = text.index("'mtd4 full readback'")
        remote_sha = text.index("OMQ1_REMOTE_SHA256_READBACK_PASS=1")
        self.assertLess(pre_safety, pre_live)
        self.assertLess(pre_live, erase)
        self.assertLess(erase, write)
        self.assertLess(write, readback)
        self.assertLess(readback, remote_sha)
        self.assertNotIn("saveenv", text.lower())
        self.assertNotIn("setenv bootselect", text.lower())
        self.assertIn("prewrite boot selector", text)
        self.assertIn("postwrite boot selector", text)
        self.assertIn("bootselect=0", text)
        self.assertNotRegex(text, r"spi_flash (?:erase|write) 0x00040000")
        self.assertNotRegex(text, r"spi_flash (?:erase|write) 0x00020000")
        self.assertNotRegex(text, r"spi_flash (?:erase|write) 0x00030000")
        self.assertRegex(text, r"spi_flash erase 0x\{0:x8\} 0x\{1:x8\}")
        self.assertIn("ExpectedFullSlotSha256", text)
        self.assertIn("ExpectedCandidateCrc32", text)
        self.assertIn("sha256sum /dev/mtdblock3", text)
        self.assertIn("sha256sum /dev/mtdblock4", text)

    def test_backend_powershell_parses(self) -> None:
        command = (
            f"[void][scriptblock]::Create((Get-Content -Raw '{BACKEND}')); "
            "Write-Output OMQ1_POWERSHELL_PARSE_PASS"
        )
        proc = subprocess.run(["pwsh.exe", "-NoProfile", "-Command", command], cwd=ROOT,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMQ1_POWERSHELL_PARSE_PASS", proc.stdout)

    def test_current_unit_v2_requires_exact_documented_divergence_and_rollback(self) -> None:
        contract = json.loads(MODULE.CONTRACT.read_text(encoding="utf-8"))
        baseline = json.loads(
            (ROOT / contract["cached_f2"]["baseline"]["path"]).read_text(encoding="utf-8")
        )
        from openmitrastar_flash_backup_preflight import validate_current_read_attestation

        ok, detail = validate_current_read_attestation(
            MODULE.CURRENT_READ, baseline, "linux_live",
            contract["current_unit_recovery_contract"],
        )
        self.assertTrue(ok, detail)
        with tempfile.TemporaryDirectory() as raw:
            tampered = json.loads(MODULE.CURRENT_READ.read_text(encoding="utf-8"))
            tampered["environment"]["primary"]["bootselect"] = "1"
            path = Path(raw) / "tampered.json"
            path.write_text(json.dumps(tampered), encoding="utf-8")
            ok, detail = validate_current_read_attestation(
                path, baseline, "linux_live",
                contract["current_unit_recovery_contract"],
            )
            self.assertFalse(ok)
            self.assertIn("environment divergence", detail)


if __name__ == "__main__":
    unittest.main()
