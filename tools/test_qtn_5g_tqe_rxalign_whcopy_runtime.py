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
BUILDER = ROOT / "tools/build_qtn_5g_tqe_rxalign_whcopy_runtime.py"
SOURCE = ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_rx.c"
QDRV = ROOT / (
    "outputs/kernel-port/quantenna-5g-tqe-rxalign-whcopy-v4-20260823/rootfs/"
    "lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
)
EXPECTED_QDRV = "f9982924fa655fb24b47f902752cbb9e682419b3e4684f29cb110b42648200f1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Qtn5gTqeRxAlignWhcopyRuntimeTests(unittest.TestCase):
    def test_tqe_handler_copies_header_before_alignment(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        handler = source[source.index("qdrv_rx_tqe_rx_handler(") : source.index("int qdrv_rx_init(")]
        copy_at = handler.index("memcpy(&wh_copy, whole_frm_hdr, sizeof(wh_copy))")
        align_at = handler.index('qdrv_rx_stack_align(skb, "tqe")')
        handle_at = handler.index("if (handle_rx_msdu")
        self.assertLess(copy_at, align_at)
        self.assertLess(align_at, handle_at)
        self.assertIn("wh = &wh_copy", handler)
        self.assertNotIn("whole_frm_hdr_offset", handler)
        self.assertNotIn("skb->head + whole_frm_hdr_offset", handler)

    def test_header_copy_has_full_object_bounds_check(self) -> None:
        source = SOURCE.read_text(encoding="utf-8")
        handler = source[source.index("qdrv_rx_tqe_rx_handler(") : source.index("int qdrv_rx_init(")]
        self.assertIn("(unsigned long)whole_frm_hdr + sizeof(wh_copy) <=", handler)
        self.assertIn("(unsigned long)skb_end_pointer(skb)", handler)
        self.assertIn("wh = NULL", handler)

    def test_module_hash_and_abi(self) -> None:
        self.assertEqual(EXPECTED_QDRV, sha256(QDRV))
        self.assertIn(b"vermagic=5.10.260-openmitrastar-radiohw mod_unload ARC700", QDRV.read_bytes())
        self.assertIn(b"OMQDRVRX stage=stack-realign", QDRV.read_bytes())
        self.assertIn(b"OMQDRVTXPATH stage=enqueue", QDRV.read_bytes())

    def test_runtime_builder_is_reproducible(self) -> None:
        with tempfile.TemporaryDirectory() as first, tempfile.TemporaryDirectory() as second:
            outputs = []
            for directory in (first, second):
                proc = subprocess.run(
                    [sys.executable, str(BUILDER), "--output-dir", directory],
                    cwd=ROOT, text=True, capture_output=True, timeout=30, check=False,
                )
                self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
                outputs.append(Path(directory))
            first_manifest = json.loads((outputs[0] / "manifest.json").read_text(encoding="utf-8"))
            second_manifest = json.loads((outputs[1] / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(first_manifest, second_manifest)
            self.assertEqual(EXPECTED_QDRV, first_manifest["artifacts"]["qdrv"]["sha256"])
            self.assertFalse(first_manifest["header_preservation"]["old_skb_pointer_retained"])
            self.assertFalse(first_manifest["header_preservation"]["head_offset_rebase"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
