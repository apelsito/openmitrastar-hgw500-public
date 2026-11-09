#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
QDRV_TX = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_tx.c"
QDRV_WLAN = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.c"
QDRV_WLAN_H = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_wlan.h"
BUILDER = ROOT / "tools/build_qtn_5g_auc_muc_discriminant_runtime.py"
V4_QDRV = ROOT / (
    "outputs/kernel-port/quantenna-5g-tqe-rxalign-whcopy-runtime-v4-20260823/"
    "qdrv-tqe-rxalign-whcopy-txpath.ko"
)
RUN_LOG = ROOT / "outputs/uart-live/qtn-5g-txpath-oob/txpath-oob-20260823-213354/uart.log"
EXPECTED_QDRV = "f9982924fa655fb24b47f902752cbb9e682419b3e4684f29cb110b42648200f1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Qtn5gAucMucDiscriminantTests(unittest.TestCase):
    def test_evidence_matches_direct_auc_bypass(self) -> None:
        log = RUN_LOG.read_text(encoding="utf-8", errors="replace")
        self.assertIn("stage=enqueue-result", log)
        self.assertIn("root_qlen=0", log)
        self.assertIn("queue_enabled=0", log)
        self.assertNotIn("OMQDRVTXPATH stage=dequeue-ready", log)
        self.assertNotIn("OMQDRVTXPATH stage=hardstart", log)

    def test_auc_is_default_and_runtime_switchable(self) -> None:
        wlan = QDRV_WLAN.read_text(encoding="utf-8")
        header = QDRV_WLAN_H.read_text(encoding="utf-8")
        self.assertIn("qw->flags_ext |= QDRV_WLAN_FLAG_AUC_TX;", wlan)
        self.assertIn("case IEEE80211_PARAM_AUC_TX:", wlan)
        self.assertIn("qw->flags_ext &= ~QDRV_WLAN_FLAG_AUC_TX;", wlan)
        self.assertIn("QDRV_WLAN_TX_USE_AUC(qw)", header)

    def test_disabling_auc_selects_existing_muc_path(self) -> None:
        tx = QDRV_TX.read_text(encoding="utf-8")
        start = tx.index("static __sram_text int qdrv_tx_sch_enqueue_to_node")
        end = tx.index("static __always_inline bool", start)
        block = tx[start:end]
        self.assertIn("if (QDRV_WLAN_TX_USE_AUC(qw))", block)
        self.assertIn("return qdrv_tx_to_auc(qv, skb);", block)
        self.assertIn("qdrv_sch_enqueue_node", block)
        self.assertLess(block.index("return qdrv_tx_to_auc"), block.index("qdrv_sch_enqueue_node"))

    def test_builder_preserves_v4_qdrv_and_is_reproducible(self) -> None:
        self.assertEqual(EXPECTED_QDRV, sha256(V4_QDRV))
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            outputs = []
            for directory in (a, b):
                proc = subprocess.run(
                    [sys.executable, str(BUILDER), "--output-dir", directory],
                    cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
                )
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                outputs.append(Path(directory))
            ma = json.loads((outputs[0] / "manifest.json").read_text(encoding="utf-8"))
            mb = json.loads((outputs[1] / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(ma, mb)
            self.assertEqual(EXPECTED_QDRV, ma["artifacts"]["qdrv"]["sha256"])

    def test_start_switches_before_rf_open(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(
                [sys.executable, str(BUILDER), "--output-dir", directory],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            text = (Path(directory) / "om-radio5-start-auctx-muc-v5").read_text(encoding="utf-8")
            set_at = text.index("iwpriv-qtn wifi0 auc_tx 0")
            rf_at = text.index("printf '1\\n' >\"$rf\"", set_at)
            self.assertLess(set_at, rf_at)
            self.assertIn("OMRADIO5_AUC_TX_MODE mode=muc value=0", text)

    def test_stop_restores_after_rf_closed_while_wifi_still_exists(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(
                [sys.executable, str(BUILDER), "--output-dir", directory],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            text = (Path(directory) / "om-radio5-stop-auctx-muc-v5").read_text(encoding="utf-8")
            down_at = text.index("ifconfig wifi0 down")
            rf_at = text.index("printf '0\\n' >\"$rf\"")
            restore_at = text.index("iwpriv-qtn wifi0 auc_tx 1")
            self.assertLess(rf_at, restore_at)
            self.assertLess(restore_at, down_at)
            self.assertIn('auc_tx_restore_rc=%s', text)
            self.assertIn('[ "$management" = preserved ] && [ "$auc_tx_restore_rc" = 0 ]', text)

    def test_no_persistent_write_commands(self) -> None:
        builder = BUILDER.read_text(encoding="utf-8").lower()
        for forbidden in ("flash_erase", "nandwrite", "mtd_debug", "fw_setenv", "/dev/mtd"):
            self.assertNotIn(forbidden, builder)


if __name__ == "__main__":
    unittest.main(verbosity=2)
