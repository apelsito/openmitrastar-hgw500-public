#!/usr/bin/env python3

from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_f78_5g_modules_precontrol_stage_guard_from_f77.py"
BUILD = ROOT / "work/mission-state/q3-persistent-composite-f78-2g-fast-5g-modules-precontrol-stage-guard/build"
RAW = BUILD / "openmitrastar-linux510-q3-persistent-f78-2g-fast-5g-modules-precontrol-stage-guard-LZMA-OFFLINE-NO-FLASH.decompressed.bin"


class F78PrecontrolStageGuardTests(unittest.TestCase):
    def test_builder_documents_precontrol_stage_guard(self) -> None:
        text = BUILDER.read_text(encoding="utf-8")
        self.assertIn("before any", text)
        self.assertIn("qdrv control write", text)
        self.assertIn("modules-stage-stop-moved-before-qdrv-control", text)
        self.assertIn("control=not-entered", text)
        self.assertIn("router_mutations", text)

    def test_built_script_stops_before_first_control_set(self) -> None:
        raw = RAW.read_bytes()
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        script = next(e.data.decode("ascii") for e in entries if e.name == "usr/sbin/om-radio5-start")
        stop = script.index("OMRADIO5_STAGE_STOP_PASS stage=modules qdrv=loaded control=not-entered")
        first_control = script.index("control_set 'set mucfw")
        self.assertLess(stop, first_control)
        self.assertIn("stage-stop-modules-precontrol", script)

    def test_manifest_and_build_result_are_pass_no_flash(self) -> None:
        manifest = json.loads((BUILD / "manifest.json").read_text(encoding="ascii"))
        result = json.loads((BUILD / "build-result.json").read_text(encoding="ascii"))
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["flash"])
        self.assertFalse(result["router_mutations"])
        self.assertEqual(manifest["bootbase_contract"]["result"], "PASS")
        self.assertTrue(manifest["slot"]["fits"])


if __name__ == "__main__":
    unittest.main()
