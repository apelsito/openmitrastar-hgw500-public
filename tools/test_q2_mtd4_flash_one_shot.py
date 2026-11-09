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
RUNNER = ROOT / "tools/run_q2_mtd4_flash_one_shot.py"
BACKEND = ROOT / "tools/q2_mtd4_bootbase_flash.ps1"
OMSPIRO_SOURCE = ROOT / "work/linux510-radio-port/omspiro/omspiro.c"
SPEC = importlib.util.spec_from_file_location("q2_mtd4_flash", RUNNER)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Q2Mtd4FlashOneShotTests(unittest.TestCase):
    def test_default_is_dry_run_and_never_flashes(self) -> None:
        proc = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT, text=True,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMQ2_MTD4_FLASH_ONE_SHOT_DRY_RUN_PASS=1", proc.stdout)
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
        self.assertEqual("cbe904ab7a807838fa12077fab924c79ce3c112a5ef40727cbaf9ec98f638cf1",
                         MODULE.EXPECTED_SHA256)
        self.assertEqual(4_157_772, MODULE.EXPECTED_BYTES)

    def test_full_slot_model_is_candidate_plus_erased_ff(self) -> None:
        candidate = b"Q2" * 100
        full = MODULE.full_slot_bytes(candidate)
        self.assertEqual(MODULE.TARGET_BYTES, len(full))
        self.assertEqual(candidate, full[:len(candidate)])
        self.assertEqual(b"\xff" * 128, full[-128:])
        self.assertEqual(zlib.crc32(full) & 0xFFFFFFFF, zlib.crc32(full) & 0xFFFFFFFF)

    def test_exact_q2_candidate_has_pinned_prefix_and_full_slot_hashes(self) -> None:
        candidate = MODULE.CANDIDATE.read_bytes()
        full = MODULE.full_slot_bytes(candidate)
        self.assertEqual(MODULE.EXPECTED_SHA256, hashlib.sha256(candidate).hexdigest())
        self.assertEqual("79c566c9", f"{zlib.crc32(candidate) & 0xFFFFFFFF:08x}")
        self.assertEqual("29e696799639d19e37fec7e142f67228127a26a5aaa014dd06c3c9d6381b8221",
                         hashlib.sha256(full).hexdigest())
        self.assertEqual("d533dfd0", f"{zlib.crc32(full) & 0xFFFFFFFF:08x}")

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
            ready.assert_called_once_with(strict=True)
            backend.assert_called_once()

    def test_backend_has_exact_order_and_no_environment_persistence(self) -> None:
        text = BACKEND.read_text(encoding="utf-8")
        pre_safety = text.index("fresh rollback read")
        pre_live = text.index("fresh current-live read")
        erase = text.index("'mtd4 erase'")
        write = text.index("'mtd4 candidate write'")
        readback = text.index("'mtd4 full readback'")
        remote_sha = text.index("OMQ2_REMOTE_SHA256_READBACK_PASS=1")
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
        self.assertIn("$CrcResultAddress = [Convert]::ToUInt32('84000000', 16)", text)
        self.assertIn("$LoadAddress = [Convert]::ToUInt32('83000000', 16)", text)
        self.assertIn("$ReadbackAddress = [Convert]::ToUInt32('86000000', 16)", text)
        self.assertIn("crc32 0x{0:x8} 0x{1:x8} 0x{2:x8}; md.l 0x{2:x8} 1", text)
        self.assertIn("CRC32 RAM readback missing", text)
        self.assertIn('"(?im)^${address}:\\s*([0-9a-f]{8})\\b"', text)
        self.assertIn("/dev/omspiro", text)
        self.assertNotIn("/dev/mtd", text)
        self.assertNotIn("/proc/mtd", text)

    def test_backend_has_exactly_one_erase_and_one_write_both_bound_to_mtd4(self) -> None:
        text = BACKEND.read_text(encoding="utf-8")
        command_lines = [line.strip() for line in text.splitlines() if "spi_flash erase" in line or "spi_flash write" in line]
        self.assertEqual(2, len(command_lines), command_lines)
        self.assertEqual(1, sum("spi_flash erase" in line for line in command_lines))
        self.assertEqual(1, sum("spi_flash write" in line for line in command_lines))
        for line in command_lines:
            self.assertIn("$TargetOffset", line)
            self.assertNotIn("$RollbackOffset", line)
        self.assertIn("OMQ2_PROTECTED_PARTITIONS_UNCHANGED_PASS=1", text)
        self.assertNotIn("of=/dev/omspiro", text)
        self.assertNotRegex(text, r"(?:flash_erase|mtd_debug)")

    def test_omspiro_module_and_read_only_contract_are_exactly_pinned(self) -> None:
        observed = hashlib.sha256(MODULE.OMSPIRO_MODULE.read_bytes()).hexdigest()
        self.assertEqual("7e00484816f37496f263e22e1bb286d8383681f1af4ad5629cd49ca97d659201",
                         observed)
        self.assertEqual(4_856, MODULE.OMSPIRO_MODULE.stat().st_size)
        contract = MODULE.validate_omspiro_contract()
        self.assertEqual("0400", contract["device_mode"])
        self.assertEqual("/dev/omspiro", contract["device"])
        self.assertTrue(contract["read_only"])
        self.assertFalse(contract["flash_actions"])
        source = OMSPIRO_SOURCE.read_text(encoding="utf-8")
        fops = source.split("static const struct file_operations omspiro_fops = {", 1)[1].split("};", 1)[0]
        self.assertIn(".read = omspiro_read", fops)
        self.assertIn(".llseek = omspiro_llseek", fops)
        for forbidden in (".write", ".unlocked_ioctl", ".compat_ioctl", ".mmap"):
            self.assertNotIn(forbidden, fops)
        for forbidden in ("copy_from_user", "memcpy_toio", "writel(", "writeb(", "writew("):
            self.assertNotIn(forbidden, source)

    def test_omspiro_postboot_readback_uses_exact_physical_offsets(self) -> None:
        text = BACKEND.read_text(encoding="utf-8")
        regions = {
            "Mtd0": (0, 2, 0x000000, 0x020000),
            "Mtd1": (2, 1, 0x020000, 0x010000),
            "Mtd2": (3, 1, 0x030000, 0x010000),
            "Mtd3": (4, 122, 0x040000, 0x7A0000),
            "Mtd4": (126, 122, 0x7E0000, 0x7A0000),
            "Mtd5": (248, 8, 0xF80000, 0x080000),
        }
        for name, (skip, count, offset, size) in regions.items():
            self.assertEqual(offset, skip * 65536)
            self.assertEqual(size, count * 65536)
            self.assertIn(f"$Omspiro{name}Skip64K = {skip}", text)
            self.assertIn(f"$Omspiro{name}Count64K = {count}", text)
            self.assertIn(
                f"dd if=/dev/omspiro bs=65536 skip=$Omspiro{name}Skip64K count=$Omspiro{name}Count64K",
                text,
            )
        self.assertIn("$OmspiroMtd4Skip4K = 2016", text)
        self.assertEqual(0x7E0000, 2016 * 4096)
        self.assertIn("dd if=/dev/omspiro bs=4096 skip=$OmspiroMtd4Skip4K", text)
        self.assertIn("$prefixTailBlock = $OmspiroMtd4Skip4K + $blocks", text)

    def test_omspiro_is_uploaded_verified_unloaded_and_cleaned_without_mtd_fallback(self) -> None:
        text = BACKEND.read_text(encoding="utf-8")
        self.assertIn("ramssh_upload.py", text)
        self.assertIn("7e00484816f37496f263e22e1bb286d8383681f1af4ad5629cd49ca97d659201", text)
        self.assertIn("ls -l /dev/omspiro | grep -q '^cr--------'", text)
        self.assertIn("OMSPIRO ready phys=0x90000000 size=0x01000000", text)
        self.assertIn("rmmod omspiro", text)
        self.assertIn("test ! -e /dev/omspiro", text)
        self.assertIn("OMQ2_OMSPIRO_CLEANUP_PASS=1", text)
        self.assertNotIn("/dev/mtd", text)
        self.assertNotIn("/proc/mtd", text)

    def test_q2_gate_never_consumes_q1_candidate_attestations(self) -> None:
        runner_text = RUNNER.read_text(encoding="utf-8").lower()
        contract = json.loads(MODULE.CONTRACT.read_text(encoding="utf-8"))
        inputs = contract["required_candidate_inputs"]
        self.assertEqual("work/mission-state/q2-mtd4-flash-candidate", inputs["directory"])
        self.assertEqual(MODULE.CURRENT_READ.name, inputs["current_read_attestation"])
        self.assertEqual(MODULE.RAM_EQUIVALENCE.name, inputs["ram_equivalence"])
        self.assertNotIn("f2-q1-full-flash-candidate", runner_text)
        self.assertNotIn("f2-q1-full-flash-candidate", json.dumps(contract).lower())
        self.assertTrue(str(MODULE.CURRENT_READ).startswith(str(MODULE.CANDIDATE_DIR)))
        self.assertTrue(str(MODULE.RAM_EQUIVALENCE).startswith(str(MODULE.CANDIDATE_DIR)))

    def test_readiness_accepts_only_the_present_exact_q2_equivalence(self) -> None:
        report = MODULE.run_readiness(strict=False)
        failed = [gate for gate in report["gates"] if gate.get("blocking") and not gate.get("passed")]
        self.assertEqual([], failed)
        self.assertTrue(report["candidate_eligible"])
        gate = next(gate for gate in report["gates"] if gate["id"] == "same-candidate-ram-equivalence")
        self.assertTrue(gate["passed"])
        required = str(MODULE.RAM_EQUIVALENCE).replace("\\", "/").lower()
        self.assertIn("q2-mtd4-flash-candidate/ram-equivalence.json", required)
        self.assertNotIn("q1", required)

    def test_superseded_55ab_attestation_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            stale = Path(raw) / "ram-equivalence.json"
            stale.write_text(json.dumps({
                "schema": "openmitrastar.ram-equivalence/v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "PASS",
                "candidate_sha256": "55ab135a388e5e156ae4166209148607104bc731aca9d7da6afe48a0470494b1",
                "flash_actions": False,
                "secret_values_recorded": False,
                "checks": {},
                "evidence": [],
            }), encoding="utf-8")
            with mock.patch.object(MODULE, "RAM_EQUIVALENCE", stale):
                with self.assertRaisesRegex(ValueError, "RAM equivalence does not PASS the exact candidate"):
                    MODULE.validate_local_inputs(10_000_000)

    def test_active_gate_contains_no_superseded_55ab_pins(self) -> None:
        old_pin = "55ab135a388e5e156ae4166209148607104bc731aca9d7da6afe48a0470494b1"
        active = (
            RUNNER,
            BACKEND,
            MODULE.CONTRACT,
            MODULE.MANIFEST,
        )
        for path in active:
            self.assertNotIn(old_pin, path.read_text(encoding="utf-8").lower(), str(path))
        self.assertEqual("cbe904ab7a807838fa12077fab924c79ce3c112a5ef40727cbaf9ec98f638cf1",
                         MODULE.EXPECTED_SHA256)

    def test_backend_powershell_parses(self) -> None:
        command = (
            "$ErrorActionPreference='Stop'; "
            f"[void][scriptblock]::Create((Get-Content -Raw '{BACKEND}')); "
            "Write-Output OMQ2_POWERSHELL_PARSE_PASS"
        )
        proc = subprocess.run(["pwsh.exe", "-NoProfile", "-Command", command], cwd=ROOT,
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMQ2_POWERSHELL_PARSE_PASS", proc.stdout)

    def test_backend_dry_run_evaluates_runtime_types_before_hardware(self) -> None:
        with tempfile.TemporaryDirectory() as raw:
            transcript = Path(raw) / "backend-dry-run.log"
            dummy_sha = "a" * 64
            proc = subprocess.run([
                "pwsh.exe", "-NoProfile", "-File", str(BACKEND),
                "-Candidate", str(MODULE.CANDIDATE),
                "-ExpectedSha256", MODULE.EXPECTED_SHA256,
                "-ExpectedBytes", str(MODULE.EXPECTED_BYTES),
                "-Transcript", str(transcript),
                "-RollbackSha256", MODULE.ROLLBACK_SHA256,
                "-ProtectedMtd0Sha256", dummy_sha,
                "-ProtectedMtd1Sha256", dummy_sha,
                "-ProtectedMtd2Sha256", dummy_sha,
                "-ProtectedMtd5Sha256", dummy_sha,
                "-RollbackCrc32", "00000000",
                "-CurrentLiveCrc32", "00000000",
                "-ExpectedCandidateCrc32", "00000000",
                "-ExpectedFullSlotSha256", dummy_sha,
                "-ExpectedFullSlotCrc32", "00000000",
                "-OmspiroModule", str(MODULE.OMSPIRO_MODULE),
                "-ExpectedOmspiroSha256", MODULE.OMSPIRO_SHA256,
                "-ExpectedOmspiroBytes", str(MODULE.OMSPIRO_BYTES),
                "-ExpectedOmspiroKernelRelease", MODULE.OMSPIRO_KERNEL_RELEASE,
                "-ExpectedOmspiroDeviceMode", MODULE.OMSPIRO_DEVICE_MODE,
            ], cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            self.assertIn("OMQ2_BOOTBASE_FLASH_DRY_RUN_PASS=1", proc.stdout)

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
