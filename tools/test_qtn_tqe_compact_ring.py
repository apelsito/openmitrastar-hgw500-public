#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_tqe.c"
RUNNER = ROOT / "tools/run_qtn_w3_switch_emac_handoff.py"
REMOTE = ROOT / "tools/qtn_w3_switch_emac_handoff_remote.sh"
ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-direct-compact-tqe256-sramgate-20260820"


class TqeCompactRingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_default_remains_vendor_512_constant(self) -> None:
        self.assertIn(
            "static unsigned int w3_rx_ring_entries = QTN_BUFS_LHOST_TQE_RX_RING;",
            self.source,
        )
        self.assertIn("w3_rx_ring_entries != 256", self.source)

    def test_compact_override_is_target_gated_and_bounded(self) -> None:
        gate = self.source.index('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")')
        validate = self.source.index("w3_rx_ring_entries != QTN_BUFS_LHOST_TQE_RX_RING")
        init = self.source.index("tqe_netdev = tqe_netdev_init()")
        self.assertLess(gate, validate)
        self.assertLess(validate, init)
        self.assertIn("is_power_of_2(w3_rx_ring_entries)", self.source)
        self.assertIn("w3_rx_ring_entries > U16_MAX", self.source)

    def test_allocation_linking_and_programming_use_runtime_count(self) -> None:
        self.assertIn("ALIGNED_DMA_DESC_ALLOC(&priv->rx, ring_entries", self.source)
        self.assertIn("i < priv->rx.desc_count", self.source)
        self.assertIn("(i + 1) % priv->rx.desc_count", self.source)
        self.assertIn("topaz_tqe_cpuif_setup_ring((void *)priv->rx.descs_dma_addr, priv->rx.desc_count)", self.source)
        self.assertNotRegex(
            self.source,
            re.compile(r"for \(i = 0; i < QTN_BUFS_LHOST_TQE_RX_RING; i\+\+\)"),
        )

    def test_runner_passes_compact_value_explicitly(self) -> None:
        runner = RUNNER.read_text(encoding="utf-8")
        remote = REMOTE.read_text(encoding="utf-8")
        self.assertIn('choices=(256, 512), default=512', runner)
        self.assertIn("W3_TQE_RING_ENTRIES", runner)
        self.assertIn('w3_rx_ring_entries=$tqe_ring_entries', remote)

    def test_artifact_is_clean_and_contains_bounded_markers(self) -> None:
        module = ARTIFACT / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/platform/topaz/switch_tqe.ko"
        self.assertTrue(module.is_file())
        manifest = (ARTIFACT / "module-manifest.tsv").read_text(encoding="utf-8")
        self.assertIn("platform/topaz/switch_tqe.ko\td41e530d65dae9dd", manifest)
        self.assertEqual((ARTIFACT / "depmod-unresolved.log").read_bytes(), b"")

    def test_direct_pipeline_dry_run(self) -> None:
        result = subprocess.run(
            [sys.executable, str(ROOT / "tools/run_qtn_w3_direct_emac_qdrv_core.py")],
            cwd=ROOT, text=True, capture_output=True, timeout=60, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("W3_DIRECT_EMAC_QDRV_CORE_DRY_RUN_PASS=1", result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
