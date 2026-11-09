#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_tx.c"
EVALUATOR = ROOT / "tools/evaluate_qtn_5g_v6_scheduler_diag.py"
BUILDER = ROOT / "tools/build_qtn_5g_v6_scheduler_diag.py"
V62_BUILDER = ROOT / "tools/build_qtn_5g_v62_scheduler_diag_uafsafe.py"
spec = importlib.util.spec_from_file_location("v6_eval", EVALUATOR)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class V6SchedulerDiagTests(unittest.TestCase):
    def test_instrumentation_includes_only_relevant_management_replies(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("IEEE80211_FC0_SUBTYPE_AUTH", text)
        self.assertIn("IEEE80211_FC0_SUBTYPE_ASSOC_RESP", text)
        self.assertIn("IEEE80211_FC0_SUBTYPE_REASSOC_RESP", text)
        self.assertIn("mgmt=%u fc=%#x", text)
        self.assertNotIn("qw->queue_enabled = 1; /* v6", text)

    def test_enqueue_result_does_not_dereference_skb_after_enqueue(self) -> None:
        text = SOURCE.read_text(encoding="utf-8")
        self.assertIn("bool trace_mgmt = trace && omqdrvtx_trace_mgmt(skb);", text)
        self.assertIn("u16 trace_fc = trace_mgmt ? omqdrvtx_frame_control(skb) : 0;", text)
        enqueue_result = text.split('stage=enqueue-result', 1)[1].split("#endif", 1)[0]
        self.assertIn("trace_mgmt, trace_fc,", enqueue_result)
        self.assertNotIn("omqdrvtx_trace_mgmt(trace_skb)", enqueue_result)
        self.assertNotIn("omqdrvtx_frame_control(trace_skb)", enqueue_result)

    def test_management_packet_correlates_by_skb(self) -> None:
        lines = []
        for index, stage in enumerate(module.STAGES):
            fields = "skb=85aa0000 proto=0 len=30 mgmt=1 fc=0xb0"
            if stage in {"desc-ready", "mailbox-enter", "mailbox-published", "txdone"}:
                fields += " hd_pa=0x1234"
            lines.append(f"OMQDRVTXPATH stage={stage} seq={index} {fields}")
        result = module.parse("\n".join(lines))
        self.assertEqual(1, result["packet_count"])
        self.assertTrue(result["best_packet"]["complete"])
        self.assertEqual("85aa0000", result["best_packet"]["skb"])

    def test_first_missing_transition_is_reported(self) -> None:
        text = (
            "OMQDRVTXPATH stage=enqueue seq=0 skb=1 proto=0 len=30 mgmt=1 fc=0xb0\n"
            "OMQDRVTXPATH stage=enqueue-result seq=0 skb=1 proto=0 len=30 mgmt=1 fc=0xb0 rc=0\n"
            "OMQDRVTXPATH stage=dequeue-ready seq=0 skb=1 proto=0 len=30 mgmt=1 fc=0xb0"
        )
        result = module.parse(text)
        self.assertEqual("dequeue-ready", result["best_packet"]["frontier"])
        self.assertEqual("hardstart", result["best_packet"]["first_missing_transition"])

    def test_builder_is_reproducible_and_ram_only(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            manifests = []
            for directory in (first, second):
                proc = subprocess.run(
                    [sys.executable, str(BUILDER), "--output-dir", directory],
                    cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
                )
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                manifests.append(json.loads((Path(directory) / "manifest.json").read_text()))
            self.assertEqual(manifests[0], manifests[1])
            self.assertFalse(manifests[0]["flash"])
            self.assertFalse(manifests[0]["mtd"])

    def test_v62_uafsafe_packager_is_reproducible_and_ram_only(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            manifests = []
            for directory in (first, second):
                proc = subprocess.run(
                    [sys.executable, str(V62_BUILDER), "--output-dir", directory],
                    cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
                )
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                payload = json.loads((Path(directory) / "manifest.json").read_text())
                self.assertEqual("RAM-ONLY-INSTRUMENTATION-NO-FLASH", payload["classification"])
                self.assertFalse(payload["safety"]["flash"])
                self.assertFalse(payload["safety"]["mtd"])
                self.assertIn("use-after-free", payload["single_change"])
                manifests.append(payload)
            self.assertEqual(manifests[0], manifests[1])


if __name__ == "__main__":
    unittest.main(verbosity=2)
