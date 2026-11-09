#!/usr/bin/env python3
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_qtn_w3_qdrv_firmware_stage.py"
REMOTE = ROOT / "tools/qtn_w3_qdrv_firmware_stage_remote.sh"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QDRV_FIRMWARE_STAGE_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QDRV_FIRMWARE_STAGE_GATE.approved.env"
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-qdrv-staged-20260819"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def gate(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines()
                if line and "=" in line)


class QdrvFirmwareStageTests(unittest.TestCase):
    def test_gate_pair_and_safety(self):
        closed = CLOSED.read_text()
        approved = APPROVED.read_text()
        transformed = closed.replace(
            "W3_QDRV_FIRMWARE_STAGE_APPROVED=0",
            "W3_QDRV_FIRMWARE_STAGE_APPROVED=1",
        ).replace(
            "QDRV_FIRMWARE_STAGE_NOT_APPROVED",
            "QDRV_FIRMWARE_STAGE_ONE_SHOT_APPROVED",
        )
        self.assertEqual(transformed, approved)
        values = gate(CLOSED)
        for key in ("W3_RF_ENABLE", "W3_FLASH_ENABLE", "W3_WIFI_ENABLE",
                    "W3_QDRV_CLEARSRAM_ENABLE", "W3_QDRV_START_ENABLE"):
            self.assertEqual(values[key], "0")
        self.assertEqual(values["W3_RAM_ONLY"], "1")
        self.assertEqual(values["W3_SWITCH_HANDOFF_STATUS"], "committed")
        self.assertEqual(values["W3_QDRV_SHA256"],
                         "338b09fcbcff933f716783a955b2d1dcec546a16675c02529570b205810c8791")

    def test_exact_local_inputs(self):
        values = gate(CLOSED)
        expected = {
            "W3_MUCFW_SHA256": "rootfs/lib/firmware/qtn_driver.qtn_ruby.0.bin",
            "W3_AUCFW_SHA256": "rootfs/lib/firmware/auc_driver.nomu.0.bin",
            "W3_DSPFW_SHA256": "rootfs/lib/firmware/rdsp_driver.0.bin",
            "W3_REGDB_SHA256": "rootfs/etc/qtn_regulatory_db.bin",
        }
        for key, relative in expected.items():
            path = ARTIFACT / relative
            self.assertTrue(path.is_file())
            self.assertEqual(sha(path), values[key])
        self.assertEqual(values["W3_REGDB_AVAILABLE"], "1")

    def test_remote_has_only_four_control_commands(self):
        text = REMOTE.read_text()
        commands = re.findall(r'^control_set "([^"]+)" [1-4]$', text, re.MULTILINE)
        self.assertEqual(commands, [
            "set mucfw qtn_driver.qtn_ruby.0.bin",
            "set fw_no_mu 1",
            "set aucfw auc_driver.nomu.0.bin",
            "set dspfw rdsp_driver.0.bin",
        ])
        self.assertNotIn("ram_insmod", text)
        self.assertNotRegex(text, re.compile(r"\b(?:insmod|rmmod|reboot|iwconfig|iwpriv|ifconfig)\b"))
        self.assertNotIn("/dev/mtd", text)
        self.assertNotIn("flash_erase", text)
        self.assertNotRegex("\n".join(commands), re.compile(r"\b(?:clearsram|start)\b"))

    def test_remote_requires_provenance_and_ok_after_every_write(self):
        text = REMOTE.read_text()
        self.assertIn("W3_SWITCH_HANDOFF_STATUS", text)
        self.assertIn("grep -q '^qdrv ' /proc/modules", text)
        self.assertIn('verify_file "$root/provenance/qdrv.ko"', text)
        self.assertIn("/bin/busybox sha256sum", text)
        self.assertIn('reply=$(cat "$control"', text)
        self.assertIn('test "$reply" = ok', text)
        self.assertIn("W3_REGDB_AVAILABLE", text)
        self.assertIn('/lib/firmware/qtn_driver.qtn_ruby.0.bin', text)
        self.assertIn('/etc/qtn_regulatory_db.bin', text)
        self.assertIn("qdrv-firmware-stage/status", text)
        self.assertIn("printf 'staged\\n'", text)
        self.assertIn("W3_QDRV_FIRMWARE_STAGE_EXPERIMENT_PASS=1", text)

    def test_syntax_and_dry_run(self):
        py = subprocess.run([sys.executable, "-m", "py_compile", str(RUNNER)], cwd=ROOT)
        self.assertEqual(py.returncode, 0)
        sh = subprocess.run([
            "wsl.exe", "sh", "-n",
            "/workspace/user-home/Desktop/MitraStar/tools/qtn_w3_qdrv_firmware_stage_remote.sh",
        ], cwd=ROOT)
        self.assertEqual(sh.returncode, 0)
        dry = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT,
                             capture_output=True, text=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("W3_QDRV_FIRMWARE_STAGE_DRY_RUN_PASS=1", dry.stdout)
        self.assertIn("'ram_only': True", dry.stdout)
        self.assertIn("'rf': False", dry.stdout)
        self.assertIn("'flash': False", dry.stdout)


if __name__ == "__main__":
    unittest.main()
