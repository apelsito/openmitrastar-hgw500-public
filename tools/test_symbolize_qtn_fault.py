#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/symbolize_qtn_fault.py"
spec = importlib.util.spec_from_file_location("symbolize_qtn_fault", SCRIPT)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class QtnFaultSymbolizerTests(unittest.TestCase):
    def test_fault_parser_extracts_register_relation(self) -> None:
        text = """
Workqueue: events 0x700f9e38
ECR: 0x00230400 EFA: 0x86f900a9 ERET: 0x701fce3c
STAT: 0x00000006 [K] BTA: 0x8525f8cf
 SP: 0x8583bd80  FP: 0x00000000 BLK: 0x700f9acc
r00: 0x00000000\tr01: 0x86f90091\tr02: 0x00000001
"""
        parsed = module.parse_fault_addresses(text)
        self.assertEqual(0x700F9E38, parsed["workqueue"])
        self.assertEqual(0x701FCE3C, parsed["eret"])
        self.assertEqual(0x700F9ACC, parsed["blk"])
        self.assertEqual(0x18, parsed["efa_minus_r01"])

    def test_module_map_parser_accepts_runner_format(self) -> None:
        text = """
OMW3TX7_MODULE_MAP_BEGIN
qdrv 669332 1 - Loading 0
wlan 628704 1 qdrv, Live 0
qdrv=0x700dfe6c
wlan=0x701c2e68
fwt_if=missing
OMW3TX7_MODULE_MAP_END
"""
        parsed = module.parse_module_map(text)
        self.assertEqual(669332, parsed["qdrv"]["module_size"])
        self.assertEqual(0x700DFE6C, parsed["qdrv"]["text_base"])
        self.assertEqual(0x701C2E68, parsed["wlan"]["text_base"])
        self.assertNotIn("text_base", parsed["fwt_if"])

    def test_resolver_maps_to_nearest_symbol(self) -> None:
        addresses = {"workqueue": 0x700F9E38, "eret": 0x701FCE3C, "efa_minus_r01": 0x18}
        modules = {
            "qdrv": {"text_base": 0x700DFE6C, "module_size": 669332},
            "wlan": {"text_base": 0x701C2E68, "module_size": 628704},
        }
        original = module.load_symbols
        try:
            module.load_symbols = lambda path, nm: {  # type: ignore[assignment]
                "qdrv.ko": [(0x19FCC, "scan_work")],
                "wlan.ko": [(0x39FD4, "ieee80211_recv_mgmt")],
            }.get(path.name, [])
            rows = module.resolve_addresses(
                addresses,
                modules,
                {"qdrv": Path("qdrv.ko"), "wlan": Path("wlan.ko")},
                Path("llvm-nm"),
            )
        finally:
            module.load_symbols = original  # type: ignore[assignment]
        self.assertEqual("workqueue", rows[0]["address_name"])
        self.assertEqual("qdrv", rows[0]["candidates"][0]["module"])
        self.assertEqual("scan_work", rows[0]["candidates"][0]["nearest_symbol"]["name"])
        self.assertEqual("eret", rows[1]["address_name"])
        self.assertEqual("wlan", rows[1]["candidates"][0]["module"])
        self.assertEqual("ieee80211_recv_mgmt", rows[1]["candidates"][0]["nearest_symbol"]["name"])

    def test_cli_outputs_json(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            fault = Path(tmp) / "fault.log"
            module_map = Path(tmp) / "module-map.txt"
            fault.write_text(
                "Workqueue: events 0x700f9e38\n"
                "ECR: 0x00230400 EFA: 0x86f900a9 ERET: 0x701fce3c\n"
                " SP: 0x8583bd80  FP: 0x00000000 BLK: 0x700f9acc\n"
                "r00: 0x00000000\tr01: 0x86f90091\n",
                encoding="utf-8",
            )
            module_map.write_text(
                "OMW3TX7_MODULE_MAP_BEGIN\nqdrv 669332 1 - Live 0\n"
                "qdrv=0x700dfe6c\nOMW3TX7_MODULE_MAP_END\n",
                encoding="utf-8",
            )
            result = subprocess.run(
                [
                    sys.executable, str(SCRIPT),
                    "--fault-log", str(fault),
                    "--module-map", str(module_map),
                    "--json",
                ],
                cwd=ROOT, text=True, capture_output=True, timeout=15, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)
            self.assertIn('"efa_minus_r01": 24', result.stdout)
            self.assertIn('"qdrv"', result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
