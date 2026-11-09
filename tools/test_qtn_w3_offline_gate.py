#!/usr/bin/env python3
from __future__ import annotations

import unittest

from qtn_w3_offline_gate import (
    DEFAULT_BOOTCFG,
    DEFAULT_FW62_TAR,
    DEFAULT_FW89,
    DEFAULT_HBM_HEADER,
    DEFAULT_HBM_MODULE,
    DEFAULT_OEM_BOOT_LOG,
    DEFAULT_OEM_HBM_DISASM,
    DEFAULT_QDRV_BLD,
    HBM_META_BASE,
    build_report,
    parse_board_config,
    parse_cfg_descriptor,
    parse_env,
    runtime_gate_text,
)


class QuantennaW3OfflineGateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.boot_blob = DEFAULT_BOOTCFG.read_bytes()
        cls.env = parse_env(cls.boot_blob)
        offset, size = parse_cfg_descriptor(cls.env["qtn_hw_board_config.bin"])
        cls.records = parse_board_config(cls.boot_blob, offset, size)
        cls.report = build_report(
            DEFAULT_BOOTCFG,
            DEFAULT_FW89,
            DEFAULT_FW62_TAR,
            DEFAULT_QDRV_BLD,
            DEFAULT_HBM_HEADER,
            DEFAULT_HBM_MODULE,
            DEFAULT_OEM_HBM_DISASM,
            DEFAULT_OEM_BOOT_LOG,
        )

    def test_exact_oem_board_parameters(self) -> None:
        board = self.report["bootcfg"]["selected_board_values"]
        expected = {
            "board_id": 65535,
            "name": "QHS860",
            "emac0": 1,
            "emac1": 1,
            "phy0_addr": 1,
            "phy1_addr": 3,
            "wifi_hw": 7,
            "rfic": 4,
            "pcie": 7,
        }
        for key, value in expected.items():
            with self.subTest(key=key):
                self.assertEqual(board[key], value)

    def test_absent_boot_values_keep_vendor_defaults(self) -> None:
        defaults = self.report["bootcfg"]["absent_value_semantics"]
        self.assertFalse(defaults["bond_opt"]["present"])
        self.assertEqual(defaults["bond_opt"]["effective_source_default"], 0xFFFFFFFF)
        self.assertEqual(defaults["power_recheck"]["effective_source_default"], 1)
        self.assertEqual(defaults["post_mask"]["effective_source_default"], 0)
        self.assertEqual(defaults["dev_mode"]["effective_source_default"], 0)

    def test_62_host_rejects_89_fwinfo_version(self) -> None:
        abi = self.report["firmware_abi"]
        self.assertEqual(abi["host_build_name"], "v37.4.0.62.1")
        self.assertEqual(abi["host_version"], 0x2504003E)
        self.assertFalse(abi["host_62_with_fw89_compatible"])
        self.assertEqual({entry["version"] for entry in abi["firmware_89"]}, {0x25040059})
        self.assertTrue(all(not entry["info_present"] for entry in abi["firmware_62"]))

    def test_auc_89_overwrites_external_hbm_metadata(self) -> None:
        boundary = self.report["auc_hbm_boundary"]
        self.assertEqual(boundary["hbm_meta_base"], HBM_META_BASE)
        self.assertTrue(boundary["external_meta_source_enabled"])
        self.assertTrue(boundary["external_meta_binary_enabled"])
        self.assertFalse(boundary["safe"])
        self.assertEqual(boundary["classification"], "OEM_QUIRK_PROVEN")
        self.assertTrue(boundary["oem_contract"]["oem_overlap_contract_proven"])
        self.assertEqual(boundary["affected_emac_metadata_indices"], [0, 1])
        self.assertFalse(boundary["coherent_current_pair"])
        self.assertEqual(
            sorted(item["overlap_bytes"] for item in boundary["overlaps"]), [196, 200]
        )
        self.assertTrue(all(item["overlap_nonzero_bytes"] > 0 for item in boundary["overlaps"]))

    def test_runtime_gate_matches_report_and_stays_closed(self) -> None:
        expected = runtime_gate_text(self.report)
        actual = (
            DEFAULT_BOOTCFG.parents[1]
            / "work/mission-state/w3-offline/W3_RUNTIME_GATE.env"
        ).read_text(encoding="utf-8")
        self.assertEqual(actual, expected)
        self.assertIn("W3_PAIR_APPROVED=1", expected)
        self.assertIn("W3_HARDWARE_ACTIVE_APPROVED=0", expected)
        self.assertIn("W3_OVERLAP_CLASS=OEM_QUIRK_PROVEN", expected)


if __name__ == "__main__":
    unittest.main(verbosity=2)
