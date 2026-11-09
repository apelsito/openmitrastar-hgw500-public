from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f171_lyoko_foundation_health_fix as f171  # noqa: E402
import post_flash_f171_foundation_gate as gate  # noqa: E402


class F171FoundationHealthTests(unittest.TestCase):
    def test_gate_json_parser_ignores_cgi_headers(self) -> None:
        rows = gate.json_rows(
            'Content-Type: application/json\n\n'
            '{"ok":true,"schema":"lyoko.api.status/v1"}\n'
            'not-json\n'
        )
        self.assertEqual([{"ok": True, "schema": "lyoko.api.status/v1"}], rows)

    def test_source_contract(self) -> None:
        ready = (f171.OVERLAY / "etc/init.d/S90-ready").read_text(encoding="utf-8")
        txn = (f171.OVERLAY / "usr/sbin/om-config-transaction").read_text(encoding="utf-8")
        api = (f171.OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
        self.assertIn("om-degraded-clear S34-ipv6-local-policy", ready)
        self.assertIn('"rollback_available":false', txn)
        self.assertIn("hostapd-cli-qtn", api)
        self.assertIn("iwconfig-qtn", api)
        self.assertIn("config_apply_enabled", api)

    def test_built_artifact_contract(self) -> None:
        manifest_path = f171.OUT / "manifest.json"
        if not manifest_path.is_file():
            self.skipTest("F171 has not been built yet")
        manifest = json.loads(manifest_path.read_text(encoding="ascii"))
        self.assertEqual("openmitrastar.f171-lyoko-foundation-health-fix/v1", manifest["schema"])
        self.assertTrue(manifest["candidate_eligible"])
        self.assertTrue(manifest["flash_supported"])
        self.assertEqual("F170", manifest["source"]["firmware"])
        self.assertEqual(0x620000, manifest["layout"]["rootfs_window_bytes"])
        self.assertEqual(
            "openmitrastar.f171-lyoko-foundation-assets/v1",
            manifest["foundation_assets"]["schema"],
        )
        self.assertEqual(
            "openmitrastar.f171-foundation-rootfs-diff/v1",
            manifest["foundation_assets"]["rootfs_diff"]["schema"],
        )
        changed = manifest["foundation_assets"]["rootfs_diff"]["new"]
        self.assertEqual("0o755", changed["etc/init.d/S90-ready"]["mode"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
