#!/usr/bin/env python3

from pathlib import Path
import json
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import build_f71_qcsapi_interp_from_f70 as f71  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_f83_5g_post_hostapd_stage_from_f78.py"
BUILD = ROOT / "work/mission-state/q3-persistent-composite-f83-5g-post-hostapd-stage-2g-mcs7/build"
RAW = BUILD / "openmitrastar-linux510-q3-persistent-f83-5g-post-hostapd-stage-2g-mcs7-LZMA-OFFLINE-NO-FLASH.decompressed.bin"


class F83PostHostapdStageTests(unittest.TestCase):
    def test_builder_documents_precise_frontier(self) -> None:
        text = BUILDER.read_text(encoding="utf-8")
        self.assertIn("OM_RADIO5_STAGE_STOP=post-hostapd", text)
        self.assertIn("before the beacon-lifetime and COC blocks", text)
        self.assertIn("post-hostapd-stage-stop-before-beacon-coc", text)
        self.assertIn("router_mutations", text)

    def test_built_script_stops_after_wps_before_beacon_and_coc(self) -> None:
        raw = RAW.read_bytes()
        _start, entries, _remainder = f71.parse_first_cpio(raw)
        script = next(e.data.decode("ascii") for e in entries if e.name == "usr/sbin/om-radio5-start")
        wps = script.index("OMRADIO5_WPS_GPIO_PASS")
        stop = script.index("OMRADIO5_STAGE_STOP_PASS stage=post-hostapd")
        beacon = script.index('if [ "$beacon_v89_wire_enable" = 1 ]; then', stop)
        coc = script.index("wait_wifi0_carrier_ready", stop)
        self.assertLess(wps, stop)
        self.assertLess(stop, beacon)
        self.assertLess(stop, coc)
        self.assertIn("stage-stop-post-hostapd", script)

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
