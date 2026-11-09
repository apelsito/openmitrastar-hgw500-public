#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]


class OpenMitraStarToolSecurityTests(unittest.TestCase):
    def test_reboot_runner_rejects_uboot_command_injection_before_uart(self) -> None:
        proc = subprocess.run(
            [
                "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File",
                str(ROOT / "tools/reboot_boot_ramssh.ps1"),
                "-ClientIp", "192.168.1.90; saveenv",
            ],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=30,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("canonical IPv4 literal", proc.stdout + proc.stderr)
        self.assertNotIn("RAMSSH_CYCLE_START", proc.stdout)

    def test_handoff_timestamp_traversal_is_rejected(self) -> None:
        proc = subprocess.run(
            [
                sys.executable, str(ROOT / "tools/create_openmitrastar_tx5_handoff.py"),
                "--workspace", str(ROOT), "--timestamp", "x/../../../../MitraStar",
            ],
            cwd=ROOT, text=True, capture_output=True, check=False, timeout=30,
        )
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("YYYYMMDD-HHMMSS", proc.stdout + proc.stderr)
        self.assertTrue((ROOT / "tools").is_dir())

    def test_handoff_copy_helpers_reject_or_skip_symlinks(self) -> None:
        source = (ROOT / "tools/create_openmitrastar_tx5_handoff.py").read_text(encoding="utf-8")
        self.assertIn("source_candidate.is_symlink()", source)
        self.assertIn(".is_relative_to(root)", source)
        self.assertIn("(Path(_directory) / name).is_symlink()", source)
        for suffix in ('.pem', '.key', '.yaml', '.yml'):
            self.assertIn(f'"{suffix}"', source)
        self.assertIn('"id_ed25519"', source)

    def test_build_scripts_canonicalize_before_recursive_delete(self) -> None:
        realtek = (ROOT / "tools/build_realtek_8192ee_incremental.sh").read_text(encoding="utf-8")
        candidate = (ROOT / "tools/build_w2_2g_parity_ram_candidate.sh").read_text(encoding="utf-8")
        self.assertLess(realtek.index('bundle=$(canonical_path "$bundle")'), realtek.index('rm -rf -- "$bundle"'))
        self.assertLess(candidate.index('stage_a=$(canonical_path "$stage_a")'), candidate.index('rm -rf -- "$stage_a"'))
        self.assertIn('"$allowed_bundle_root"/*RAM-ONLY*', realtek)
        self.assertIn('"$allowed_build_root"/*', candidate)


if __name__ == "__main__":
    unittest.main()
