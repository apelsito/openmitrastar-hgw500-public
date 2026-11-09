#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f302_radar_native_fail_closed/qtn_radar_native_f302.c"
CONSUMER = ROOT / "work/kernel-port/modules/f302_radar_native_fail_closed/qtn_radar_native_f302_consumer_probe.c"
BUILDER = ROOT / "tools/build_f302_radar_native_offline.py"
OUT = ROOT / "outputs/kernel-port/f302-radar-native-fail-closed-v8-20260904"


class F302RadarNativeOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="ascii")
        cls.consumer = CONSUMER.read_text(encoding="ascii")
        cls.builder = BUILDER.read_text(encoding="ascii")
        cls.manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))

    def test_fail_closed_runtime_contract(self) -> None:
        self.assertIn("bool radar_start", self.source)
        self.assertIsNotNone(re.search(r"bool radar_start\([^)]*\)\s*\{.*?return false;", self.source, re.S))
        self.assertIsNotNone(re.search(r"bool radar_get_status\([^)]*\)\s*\{.*?return false;", self.source, re.S))
        self.assertIn("return DFS_RQMT_UNKNOWN;", self.source)
        self.assertGreaterEqual(self.source.count("return -EOPNOTSUPP;"), 5)

    def test_no_hardware_activation_primitives(self) -> None:
        for marker in (
            "ioremap", "iounmap", "readl", "writel", "request_irq", "free_irq",
            "proc_create", "debugfs_create", "timer_setup", "schedule_work",
            "schedule_delayed_work", "mod_timer", "qtn_mproc_sync_shared_params_get",
        ):
            self.assertNotIn(marker, self.source)

    def test_all_expected_symbols_exported(self) -> None:
        expected = set(self.manifest["qdrv_contract"]["header_api_symbols"])
        actual = set(self.manifest["provider"]["exports"])
        self.assertEqual(expected, actual)
        for symbol in expected:
            self.assertIn(f"EXPORT_SYMBOL({symbol});", self.source)
            self.assertIn(symbol, self.consumer)

    def test_exact_f301_abi_is_pinned(self) -> None:
        target = self.manifest["target"]
        self.assertEqual(target["kernel_release"], "5.10.260-openmitrastar-radiohw")
        self.assertEqual(target["f301_config_sha256"], "cf01ec531be114cd77412712f2fdb54057ac65ddf3d30e8f4bfabe0f0c1aad9e")
        self.assertEqual(target["f301_vmlinux_sha256"], "8d7a81947e43f2e9763e0228347802fb008956c754431e75e0db0b66e73d7fbc")
        self.assertEqual(target["f301_module_symvers_sha256"], "29e86facebed934166e4c52bf9e0a95972d677d49b0bc4e0a49df19e8b7c1269")
        self.assertFalse(target["modversions"])
        self.assertEqual(self.manifest["provider"]["vermagic"], "5.10.260-openmitrastar-radiohw mod_unload ARC700")

    def test_consumer_link_probe_covers_complete_api(self) -> None:
        self.assertTrue(self.manifest["consumer_link_probe"]["imports_all_expected_api"])
        self.assertFalse(self.manifest["consumer_link_probe"]["loadable_by_design"])
        self.assertEqual(self.manifest["consumer_link_probe"]["init_result"], "-EOPNOTSUPP")

    def test_qdrv_external_link_probe_uses_provider(self) -> None:
        contract = self.manifest["qdrv_contract"]
        self.assertEqual(contract["current_source_externalized_link_probe"], "PASS")
        self.assertTrue(contract["current_source_externalized_all_imports_present"])
        self.assertEqual(contract["current_source_externalized_import_count"], 16)
        self.assertEqual(contract["unused_oem_api_exports"], ["radar_get_chan", "radar_set_shared_params"])
        modinfo = (OUT / "qdrv-external-provider-modinfo.txt").read_text(encoding="utf-8")
        self.assertIn("qtn_radar_native_f302", modinfo)

    def test_oem_binary_boundary_is_explicit(self) -> None:
        oem = self.manifest["oem_radar_binary"]
        self.assertEqual(oem["vermagic"], "2.6.35.12 mod_unload ARC700")
        self.assertEqual(oem["license"], "Proprietary")
        self.assertFalse(oem["direct_reuse_on_f301"])
        self.assertTrue(oem["exports_complete_16_symbol_qdrv_contract"])
        self.assertEqual(oem["does_not_export_header_only_symbols"], ["radar_get_chan", "radar_set_shared_params"])
        self.assertEqual(
            oem["imports_missing_from_f301"],
            ["boot_tvec_bases", "create_proc_entry", "do_gettimeofday", "schedule_delayed_work", "slowpath_copy_from_user"],
        )

    def test_not_integrated_or_hardware_validated(self) -> None:
        safety = self.manifest["safety"]
        self.assertTrue(all(value is False for value in safety.values()))
        self.assertEqual(self.manifest["physical_validation"], "NOT_RUN")
        self.assertEqual(self.manifest["classification"], "OFFLINE_ABI_SKELETON_NOT_A_RADAR_DETECTOR")

    def test_artifact_hashes_match(self) -> None:
        for key in ("provider", "consumer_link_probe"):
            entry = self.manifest[key]
            path = OUT / entry["file"]
            self.assertEqual(path.stat().st_size, entry["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), entry["sha256"])

    def test_builder_refuses_mutating_scope(self) -> None:
        for marker in ("ssh.exe", "scp.exe", "tiny_tftp", "open_uart", "com3", "mtd erase", "mtd write"):
            self.assertNotIn(marker, self.builder.lower())


if __name__ == "__main__":
    unittest.main()
