#!/usr/bin/env python3

import hashlib
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_q3_persistent_composite.sh"
PREP = ROOT / "tools/prepare_f66_2g_queue_guard_loader.ps1"
LOADER = ROOT / "work/mission-state/q3-persistent-composite-f66-2g-queue-guard/prep/om-radio-modules"
PREP_JSON = ROOT / "work/mission-state/q3-persistent-composite-f66-2g-queue-guard/prep/f66-loader-prep.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class F662gQueueGuardLoaderTests(unittest.TestCase):
    def test_builder_accepts_hash_pinned_radio_modules_override(self) -> None:
        text = BUILDER.read_text(encoding="utf-8")
        self.assertIn(
            'canonical_radio_modules="${OM_Q3_RADIO_MODULES_PATH:-$canonical_product_rootfs/usr/sbin/om-radio-modules}"',
            text,
        )
        self.assertIn(
            'expected_canonical_radio_modules=${OM_Q3_EXPECTED_RADIO_MODULES_SHA256:-428a91a54a0fce4d1475219142eb91e86999edaffcd9a1e4b5b4015b6d733786}',
            text,
        )
        self.assertIn('require_sha "$canonical_radio_modules" "$expected_canonical_radio_modules"', text)

    def test_f66_prep_script_is_non_hardware_and_fail_closed(self) -> None:
        text = PREP.read_text(encoding="utf-8")
        self.assertIn("touches_router", text)
        self.assertIn("opens_uart", text)
        self.assertIn("flash", text)
        self.assertIn("source loader does not contain expected text", text)
        self.assertIn("patch produced no changes", text)

    def test_f66_loader_has_expected_2g_autorate_reclaim_profile(self) -> None:
        self.assertTrue(LOADER.is_file(), "run prepare_f66_2g_queue_guard_loader.ps1 first")
        text = LOADER.read_text(encoding="utf-8")
        self.assertIn("hgw500_tx_reclaim_poll=1", text)
        self.assertIn("hgw500_tx_queue_guard=N", text)
        self.assertIn("hgw500_tx_reclaim_poll=Y", text)
        self.assertIn("profile=all64-autorate-eapol-mgntq-reclaim", text)
        self.assertIn("hgw500_force_data_mcs7=0", text)
        self.assertIn("hgw500_force_data_mcs7=N", text)
        self.assertIn("hgw500_txbd_be_data_split=1", text)
        self.assertNotIn("hgw500_tx_queue_guard=1", text)
        self.assertNotIn("hgw500_tx_queue_guard=Y", text)
        self.assertNotIn("hgw500_force_data_mcs7=1", text)
        self.assertNotIn("hgw500_force_data_mcs7=Y", text)

    def test_f66_prep_json_matches_loader_hash(self) -> None:
        self.assertTrue(PREP_JSON.is_file(), "run prepare_f66_2g_queue_guard_loader.ps1 first")
        text = PREP_JSON.read_text(encoding="ascii")
        observed = sha256(LOADER)
        self.assertIn(f'"output_sha256":  "{observed}"', text)
        self.assertIn('"OM_Q3_RADIO_MODULES_PATH"', text)
        self.assertIn('"OM_Q3_EXPECTED_RADIO_MODULES_SHA256"', text)


if __name__ == "__main__":
    unittest.main()
