#!/usr/bin/env python3
import hashlib
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_qtn_w3_qdrv_config_stage.py"
REMOTE = ROOT / "tools/qtn_w3_qdrv_config_stage_remote.sh"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QDRV_CONFIG_STAGE_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QDRV_CONFIG_STAGE_GATE.approved.env"
PRIVATE = ROOT / "work/secrets-backup/20260725-161724-text/mnt__jffs2__wifi_mac_addrs"
QDRV_CONTROL = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_control.c"
POWER = ROOT / "work/hgw500-rootfs-live/squashfs-root/etc/power_tables"


def digest(path: Path, algorithm: str = "sha256") -> str:
    return hashlib.new(algorithm, path.read_bytes()).hexdigest()


def gate(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text().splitlines()
                if line and "=" in line)


class QdrvConfigStageTests(unittest.TestCase):
    def test_gate_pair_and_closed_surfaces(self):
        closed = CLOSED.read_text()
        approved = APPROVED.read_text()
        transformed = closed.replace(
            "W3_QDRV_CONFIG_STAGE_APPROVED=0", "W3_QDRV_CONFIG_STAGE_APPROVED=1"
        ).replace(
            "QDRV_CONFIG_STAGE_NOT_APPROVED", "QDRV_CONFIG_STAGE_ONE_SHOT_APPROVED"
        )
        self.assertEqual(transformed, approved)
        values = gate(CLOSED)
        for key in ("W3_RF_ENABLE", "W3_FLASH_ENABLE", "W3_WIFI_ENABLE",
                    "W3_VAP_ENABLE", "W3_QDRV_CLEARSRAM_ENABLE",
                    "W3_QDRV_START_ENABLE"):
            self.assertEqual(values[key], "0")
        self.assertEqual(values["W3_FIRMWARE_STAGE_STATUS"], "staged")
        self.assertEqual(values["W3_WATCHDOG_REQUIRED"], "1")

    def test_private_mac_is_valid_but_never_embedded(self):
        secret = PRIVATE.read_text(encoding="ascii").splitlines()[0].strip()
        self.assertRegex(secret, r"^(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
        combined = RUNNER.read_text() + REMOTE.read_text() + CLOSED.read_text() + APPROVED.read_text()
        if secret in combined:
            self.fail("private MAC was embedded in a runner or gate")
        self.assertIn('(PRIVATE_MAC_SOURCE, f"{remote_root}/private/mac0addr", "0600")',
                      RUNNER.read_text())
        self.assertIn("private_mac=redacted", REMOTE.read_text())

    def test_power_table_hashes_and_destination(self):
        values = gate(CLOSED)
        table = POWER / "tx_power_QSR1000_es.txt"
        conf = POWER / "power_table.conf"
        self.assertEqual(digest(table), values["W3_POWER_TABLE_SHA256"])
        self.assertEqual(digest(table, "md5"), values["W3_POWER_TABLE_MD5"])
        self.assertEqual(digest(conf), values["W3_POWER_CONF_SHA256"])
        self.assertEqual(digest(conf, "md5"), values["W3_POWER_CONF_MD5"])
        self.assertEqual(conf.read_text(), "power_selection=2\n")
        remote = REMOTE.read_text()
        self.assertIn("power_dir=/etc/power_tables", remote)
        self.assertGreaterEqual(remote.count('verify_file "$power_dir/'), 2)
        self.assertIn("target_sha256=verified md5_source=host-pinned-same-bytes", remote)
        self.assertNotIn("md5_file()", remote)
        self.assertNotRegex(remote, re.compile(r"\btr\b"))

    def test_lock_syntax_matches_real_parser(self):
        parser = QDRV_CONTROL.read_text()
        value_read = parser.index("value = argv[2];")
        lock_branch = parser.index('strcmp(name, "lock_checksum_list")')
        self.assertLess(value_read, lock_branch)
        self.assertIn('control_set "set lock_checksum_list 1" 3', REMOTE.read_text())

    def test_remote_executes_only_three_redacted_control_commands(self):
        text = REMOTE.read_text()
        calls = re.findall(r'^control_set "([^"]+)" [1-3]$', text, re.MULTILINE)
        self.assertEqual(calls, [
            "set mac0addr $private_mac",
            "set power_table_checksum $power_dir/tx_power_QSR1000_es.txt $(value W3_POWER_TABLE_MD5)",
            "set lock_checksum_list 1",
        ])
        self.assertNotRegex("\n".join(calls), re.compile(r"\b(?:clearsram|start)\b"))
        self.assertNotRegex(text, re.compile(r"\b(?:insmod|rmmod|reboot|iwconfig|iwpriv|ifconfig)\b"))
        self.assertNotIn("/dev/mtd", text)
        self.assertIn("command_index=$2", text)
        self.assertNotIn("command=$command", text)

    def test_prerequisites_and_ok_readback(self):
        text = REMOTE.read_text()
        self.assertIn("qdrv-firmware-stage/status", text)
        self.assertIn("W3_SWITCH_HANDOFF_STATUS", text)
        self.assertIn("grep -q '^qdrv ' /proc/modules", text)
        self.assertIn("OMWDT stage=armed", text)
        self.assertIn("OMWDT stage=pet first=1", text)
        self.assertIn('test "$(cat "$control" 2>/dev/null)" = ok', text)
        self.assertIn('test "$reply" = ok', text)
        self.assertIn("rootfs_not_ram", text)

    def test_syntax_and_dry_run_without_secret_output(self):
        py = subprocess.run([sys.executable, "-m", "py_compile", str(RUNNER)], cwd=ROOT)
        self.assertEqual(py.returncode, 0)
        sh = subprocess.run([
            "wsl.exe", "sh", "-n",
            "/workspace/user-home/Desktop/MitraStar/tools/qtn_w3_qdrv_config_stage_remote.sh",
        ], cwd=ROOT)
        self.assertEqual(sh.returncode, 0)
        dry = subprocess.run([sys.executable, str(RUNNER)], cwd=ROOT,
                             capture_output=True, text=True)
        self.assertEqual(dry.returncode, 0, dry.stderr)
        output = dry.stdout + dry.stderr
        secret = PRIVATE.read_text(encoding="ascii").splitlines()[0].strip()
        if secret in output:
            self.fail("private MAC leaked in dry-run output")
        self.assertIn("W3_QDRV_CONFIG_STAGE_DRY_RUN_PASS=1", output)
        self.assertIn("validated-redacted", output)


if __name__ == "__main__":
    unittest.main()
