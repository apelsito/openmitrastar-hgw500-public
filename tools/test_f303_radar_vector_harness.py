#!/usr/bin/env python3

import importlib.util
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).with_name("f303_radar_vector_harness.py")
SPEC = importlib.util.spec_from_file_location("f303_radar_vector_harness", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class F303RadarVectorHarnessTests(unittest.TestCase):
    def test_decodes_modulo_width_pri_and_tag(self):
        pulses = MODULE.decode_fifo_pairs(
            [0xF7FFFFF0, 0x00000020],
            [0x08000010, 0x00000030],
        )
        self.assertEqual(pulses[0]["start"], 0x07FFFFF0)
        self.assertEqual(pulses[0]["stop"], 0x10)
        self.assertEqual(pulses[0]["width"], 0x20)
        self.assertTrue(pulses[0]["tag_bit"])
        self.assertEqual(pulses[1]["pri"], 0x30)

    def test_itlv_dispatch_fires_registered_callback(self):
        result = MODULE.model_dispatch(
            {"itlv_enabled": True, "itlv_hit": True, "callback_registered": True}
        )
        self.assertEqual(result["classes"], ["itlv"])
        self.assertTrue(result["mark_radar_callback_fired"])

    def test_ssr_path_is_selected_only_when_itlv_path_is_not_selected(self):
        result = MODULE.model_dispatch(
            {"itlv_enabled": False, "ssr_bounds_hit": True, "callback_registered": True}
        )
        self.assertEqual(result["classes"], ["ssr"])

    def test_lsr_can_add_a_detection_to_the_primary_path(self):
        result = MODULE.model_dispatch(
            {
                "itlv_enabled": False,
                "ssr_bounds_hit": True,
                "lsr_enabled": True,
                "lsr_hit": True,
            }
        )
        self.assertEqual(result["classes"], ["ssr", "lsr"])

    def test_poll_lsr_path_is_modelled_separately(self):
        result = MODULE.model_dispatch({"poll_lsr_hit": True})
        self.assertEqual(result["classes"], ["lsr_poll"])

    def test_rejection_blocks_callback_without_erasing_candidate(self):
        result = MODULE.model_dispatch(
            {"lsr_enabled": True, "lsr_hit": True, "check_radar_rejected": True}
        )
        self.assertTrue(result["candidate"])
        self.assertFalse(result["mark_radar_callback_fired"])

    def test_noreject_override_allows_callback(self):
        result = MODULE.model_dispatch(
            {
                "lsr_enabled": True,
                "lsr_hit": True,
                "post_filter_reject_input": True,
                "noreject_override": True,
            }
        )
        self.assertFalse(result["suppressed"])
        self.assertTrue(result["mark_radar_callback_fired"])

    def test_zero_crossing_poll_cap_is_enforced(self):
        with self.assertRaisesRegex(ValueError, "18-pulse cap"):
            MODULE.validate_zero_crossings([{"pulses": [[] for _ in range(19)]}], 19)

    def test_harness_refuses_to_claim_classifier(self):
        result = MODULE.run_vector(
            {
                "schema": "openmitrastar.f303-radar-vector/v1",
                "fifo": {"mem_h_words": [], "mem_l_words": []},
                "oracle": {},
            }
        )
        self.assertEqual(result["classification_algorithm"], "NOT_IMPLEMENTED")


if __name__ == "__main__":
    unittest.main()
