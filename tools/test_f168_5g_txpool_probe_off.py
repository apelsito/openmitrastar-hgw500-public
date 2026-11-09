from __future__ import annotations

import hashlib
import json
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import compose_f168_5g_txpool_probe_off as f168  # noqa: E402


class F168TxPoolProbeOffTests(unittest.TestCase):
    def test_source_gates_hbm_reads_default_off(self) -> None:
        text = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_tx.c").read_text(encoding="ascii")
        self.assertIn("static bool openmitrastar_txpool_probe_enable;", text)
        self.assertIn("bool txpool_probe = hgw_target && READ_ONCE(openmitrastar_txpool_probe_enable);", text)
        self.assertIn("if (txpool_probe) {\n\t\temac_avail_before", text)
        self.assertIn("if (txpool_probe &&", text)

    def test_built_contract(self) -> None:
        path = f168.OUT / "manifest.json"
        if not path.is_file():
            self.skipTest("F168 has not been composed")
        manifest = json.loads(path.read_text(encoding="ascii"))
        self.assertEqual("openmitrastar.f168-5g-txpool-probe-off/v1", manifest["schema"])
        self.assertFalse(manifest["candidate_eligible"])
        self.assertFalse(manifest["flash_supported"])
        self.assertTrue(manifest["hypothesis"]["physical_proof_required"])
        self.assertEqual(
            "ed5314b5f24e6ae4f3dd07ef1efc57c68e4246c9e3fdf055657f80c5798f7f26",
            json.loads((f168.ASSETS / "assets-manifest.json").read_text(encoding="ascii"))["qdrv"]["new_sha256"],
        )
        self.assertEqual(
            hashlib.sha256((f168.OUT / f"{f168.BASE}.kernel.lzma").read_bytes()).hexdigest(),
            "7c92556a4b39c9014c0e4f77501d361827080d564329d1130d0196f572f5ec26",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
