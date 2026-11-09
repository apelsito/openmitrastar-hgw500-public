from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f170_lyoko_foundation_runtime_fix as f170  # noqa: E402


class F170FoundationTests(unittest.TestCase):
    def test_overlay_uses_live_linux510_interfaces(self) -> None:
        api = (f170.OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
        txn = (f170.OVERLAY / "usr/sbin/om-config-transaction").read_text(encoding="utf-8")
        self.assertIn("hostapd-cli-qtn", api)
        self.assertIn("iwconfig-qtn", api)
        self.assertIn("iwpriv-qtn", api)
        self.assertIn("origin-mtd5/wireless_conf.txt", api)
        self.assertIn("config_apply_enabled", api)
        self.assertIn("changed_marker", txn)
        self.assertIn("OPENMITRASTAR_CONFIG_APPLY=1", txn)

    def test_built_artifact_contract(self) -> None:
        manifest_path = f170.OUT / "manifest.json"
        if not manifest_path.is_file():
            self.skipTest("F170 has not been built yet")
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        self.assertEqual("openmitrastar.f170-lyoko-foundation-runtime-fix/v1", manifest["schema"])
        self.assertTrue(manifest["candidate_eligible"])
        self.assertTrue(manifest["flash_supported"])
        self.assertEqual("F169", manifest["source"]["firmware"])
        self.assertEqual(16, len(manifest["foundation_assets"]["build_id"]))

    def test_flash_wrapper_prefers_remote_tftp(self) -> None:
        wrapper = (ROOT / "tools/build_flash_test_f170_lyoko_foundation.ps1").read_text(encoding="utf-8")
        self.assertIn('preferred_transport = "TFTP from APELSITO@$AelitaHost"', wrapper)
        self.assertIn("aelita_tftp_server.py", wrapper)
        self.assertIn("--external-tftp", wrapper)
        self.assertIn("--uart-attach-topaz", wrapper)


if __name__ == "__main__":
    unittest.main(verbosity=2)
