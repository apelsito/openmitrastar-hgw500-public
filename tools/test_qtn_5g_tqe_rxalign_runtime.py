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
BUILDER = ROOT / "tools/build_qtn_5g_tqe_rxalign_txpath_runtime.py"
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_rx.c"
EXPECTED_QDRV = "f9982924fa655fb24b47f902752cbb9e682419b3e4684f29cb110b42648200f1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Qtn5gTqeRxAlignRuntimeTests(unittest.TestCase):
    def test_tqe_path_realigns_before_handle_and_stack(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        handler = source[source.index("qdrv_rx_tqe_rx_handler(") : source.index("int qdrv_rx_init(")]
        remove_vlan = handler.index("qdrv_rx_remove_eapol_vlan")
        align = handler.index('qdrv_rx_stack_align(skb, "tqe")')
        handle = handler.index("if (handle_rx_msdu")
        stack = handler.index("netif_receive_skb")
        self.assertLess(remove_vlan, align)
        self.assertLess(align, handle)
        self.assertLess(handle, stack)
        self.assertIn("struct ieee80211_qosframe_addr4 wh_copy", handler)
        self.assertIn("memcpy(&wh_copy, whole_frm_hdr, sizeof(wh_copy))", handler)
        self.assertIn("wh = &wh_copy", handler)
        self.assertNotIn("whole_frm_hdr_offset", handler)
        self.assertLess(handler.index("memcpy(&wh_copy"), align)
        self.assertIn("ieee80211_free_node(ni);", handler)

    def test_builder_is_reproducible_and_single_variable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "runtime"
            proc = subprocess.run(
                [sys.executable, str(BUILDER), "--output-dir", str(output)],
                cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
            )
            self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
            manifest = json.loads((output / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(EXPECTED_QDRV, manifest["artifacts"]["qdrv"]["sha256"])
            self.assertEqual("RAM-ONLY-TQE-RXALIGN-WHCOPY-TXPATH-NO-FLASH", manifest["classification"])
            self.assertFalse(manifest["flash"])
            self.assertFalse(manifest["hardware_tested"])
            self.assertEqual(
                "copy the transient 802.11 header locally, then apply the target-gated ARC L3 alignment copy to the direct TQE RX path",
                manifest["single_behavior_change"],
            )

    def test_built_module_contains_both_rx_and_tx_markers(self) -> None:
        artifact = ROOT / (
            "outputs/kernel-port/quantenna-5g-tqe-rxalign-whcopy-v4-20260823/rootfs/"
            "lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
        )
        self.assertEqual(EXPECTED_QDRV, sha256(artifact))
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn('qdrv_rx_stack_align(skb, "tqe")', source)
        self.assertIn(b"OMQDRVTXPATH stage=enqueue", artifact.read_bytes())


if __name__ == "__main__":
    unittest.main(verbosity=2)
