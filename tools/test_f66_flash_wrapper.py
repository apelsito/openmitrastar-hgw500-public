#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
WRAPPER = ROOT / "tools/flash_f66_2g_qguard.ps1"
WATCHER = ROOT / "tools/watch_flash_f66_2g_qguard_until_bootbase.ps1"
ONE_SHOT = ROOT / "tools/run_q3_f45_radio5_powerselect_nonfatal_openlab_autostart_mtd4_flash_one_shot.py"


class F66FlashWrapperTests(unittest.TestCase):
    def test_wrapper_is_pinned_to_f66_candidate_and_ack(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn("q3-persistent-composite-f66-2g-queue-guard\\build", text)
        self.assertIn("openmitrastar-linux510-q3-persistent-f66-2g-autorate-reclaim-LZMA-OFFLINE-NO-FLASH", text)
        self.assertIn("021cd4896ee54db95addd3b3c4111eb811b2dcf77a69c87b28b94dd4bec4b341", text)
        self.assertIn("5613197", text)
        self.assertIn("OPENMITRASTAR_Q3_F66_2G_AUTORATE_RECLAIM_MTD4_FLASH_021CD489", text)
        self.assertIn("OM_Q3_FLASH_SSH_KEY", text)
        self.assertIn(".codex_tmp\\openmitrastar_ramssh_client_ed25519", text)
        self.assertIn("verify_f66_offline_preflight.py", text)
        self.assertIn("--current-live-crc32", text)
        self.assertIn("F66 offline preflight failed", text)

    def test_wrapper_defaults_to_measured_current_live_guard(self) -> None:
        text = WRAPPER.read_text(encoding="utf-8")
        self.assertIn('[string]$CurrentLiveCrc32 = "26523198"', text)
        self.assertIn("f81e68041e8f5e1fa4c51c47330186096a9e51a51ccfd43b6905ebcb57b29fe8", text)
        self.assertIn("-CurrentLiveCrc32", text)

    def test_one_shot_accepts_nested_candidate_contract_and_fixed_size_manifest(self) -> None:
        text = ONE_SHOT.read_text(encoding="utf-8")
        self.assertIn('contract_image = contract.get("candidate", contract)', text)
        self.assertIn('manifest_rootfs = manifest.get("rootfs", {}).get("rootfs", {})', text)
        self.assertIn('"FIXED_SIZE"', text)

    def test_watcher_uses_f66_wrapper_without_opening_parallel_com_in_test(self) -> None:
        text = WATCHER.read_text(encoding="utf-8")
        self.assertIn("openmitrastar.f66-flash-watch-status/v1", text)
        self.assertIn("flash_f66_2g_qguard.ps1", text)
        self.assertIn("f66-2g-autorate-reclaim", text)
        self.assertIn("021cd4896ee54db95addd3b3c4111eb811b2dcf77a69c87b28b94dd4bec4b341", text)
        self.assertIn('current_live_crc32 = $CurrentLiveCrc32', text)
        self.assertIn('[string]$CurrentLiveCrc32 = "26523198"', text)


if __name__ == "__main__":
    unittest.main()
