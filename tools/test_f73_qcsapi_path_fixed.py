#!/usr/bin/env python3

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILD = ROOT / "work/mission-state/q3-persistent-composite-f73-5g-qcsapi-path-fixed/build"
MANIFEST = BUILD / "manifest.json"
REPORT_BUILD = BUILD / "build-result.json"
CONTRACT = BUILD / "bootbase-contract.json"
WEB = BUILD / "openmitrastar-linux510-q3-persistent-f73-5g-qcsapi-path-fixed-LZMA-OFFLINE-NO-FLASH.webformat.bin"
RAW = BUILD / "openmitrastar-linux510-q3-persistent-f73-5g-qcsapi-path-fixed-LZMA-OFFLINE-NO-FLASH.decompressed.bin"
TFTP_COPY = ROOT / "work/tftp/omvl/openmitrastar-linux510-q3-persistent-f73-5g-qcsapi-path-fixed-LZMA-OFFLINE-NO-FLASH.webformat.bin"
SOURCE_RAW = f71.SRC_BUILD / f"{f71.SRC_BASE}.decompressed.bin"


class F73QcsapiPathFixedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not MANIFEST.is_file():
            raise unittest.SkipTest("F73 has not been built yet")

    def test_artifacts_exist_and_bootbase_accepts_candidate(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
        contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
        self.assertEqual(manifest["schema"], "openmitrastar.q3-persistent-composite-f73-qcsapi-path-fixed/v1")
        self.assertEqual(manifest["classification"], "F73_FIXED_OFFSET_FROM_F70_QCSAPI_PATH_WRAPPER_ONLY")
        self.assertTrue(WEB.is_file())
        self.assertLessEqual(WEB.stat().st_size, 7_995_392)
        self.assertTrue(manifest["slot"]["fits"])
        self.assertEqual(manifest["bootbase_contract"]["result"], "PASS")
        self.assertTrue(manifest["bootbase_contract"]["candidate_accepted"])
        self.assertEqual(contract["result"], "PASS")
        self.assertTrue(contract["candidate"]["accepted_by_contract"])
        self.assertTrue(TFTP_COPY.is_file())
        self.assertEqual(TFTP_COPY.read_bytes(), WEB.read_bytes())

    def test_raw_size_cpio_end_and_remainder_are_preserved_from_f70(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
        source_raw = SOURCE_RAW.read_bytes()
        f73_raw = RAW.read_bytes()
        source_start, source_entries, source_remainder = f71.parse_first_cpio(source_raw)
        f73_start, f73_entries, f73_remainder = f71.parse_first_cpio(f73_raw)
        self.assertEqual(len(f73_raw), len(source_raw))
        self.assertEqual(f73_start, source_start)
        self.assertEqual(len(f73_raw) - len(f73_remainder), len(source_raw) - len(source_remainder))
        self.assertEqual(f73_remainder, source_remainder)
        self.assertEqual(manifest["patch"]["delta_bytes"], 0)
        self.assertEqual(manifest["patch"]["cpio_end"], len(source_raw) - len(source_remainder))
        names = {entry.name for entry in f73_entries}
        self.assertIn("usr/sbin/call_qcsapi", names)
        self.assertNotIn("www/img/icon_eye.png", names)

    def test_call_qcsapi_wrapper_is_executable_and_uses_scoped_loader(self) -> None:
        _, entries, _ = f71.parse_first_cpio(RAW.read_bytes())
        entry = next(item for item in entries if item.name == "usr/sbin/call_qcsapi")
        self.assertEqual(entry.mode & 0o170000, 0o100000)
        self.assertEqual(entry.mode & 0o777, 0o755)
        text = entry.data.decode("ascii")
        self.assertTrue(text.startswith("#!/bin/ash\n"))
        self.assertIn("/usr/libexec/openmitrastar/qcsapi-runtime", text)
        self.assertIn("ld-uClibc-0.9.29.so", text)
        self.assertIn("--library-path", text)
        self.assertIn('"$r/bin/call_qcsapi" "$@"', text)

    def test_no_hardware_scope(self) -> None:
        result = json.loads(REPORT_BUILD.read_text(encoding="ascii"))
        manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
        self.assertEqual(result["status"], "PASS")
        self.assertFalse(result["flash"])
        self.assertFalse(result["router_mutations"])
        self.assertFalse(manifest["security"]["touches_router"])
        self.assertFalse(manifest["security"]["opens_uart"])
        self.assertFalse(manifest["security"]["flash"])


if __name__ == "__main__":
    unittest.main()
