from pathlib import Path
import hashlib
import json
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/kernel-port/realtek-loop/rx-rate-tx-v4-RAM-ONLY-NO-FLASH"


class WarmRxGuardTests(unittest.TestCase):
    def test_patch_markers_and_target_gate(self):
        warm = (ROOT / "work/kernel-port/linux-5.10/rtlwifi-mitrastar-warm-preclean-topaz.patch").read_text()
        pci = (ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c").read_text()
        self.assertIn("if (mitrastar_retry)", warm)
        self.assertIn("fw-warm-preclean reason=residual-ready", warm)
        self.assertIn("RTL_TOPAZ_RX_WORK_BUDGET 32", pci)
        self.assertIn("OMRTL stage=rx-defer", pci)
        self.assertIn("intb-only vector is real work", pci)
        self.assertIn("irq_line_lifecycle_managed", pci)
        self.assertIn("more = processed == RTL_TOPAZ_RX_WORK_BUDGET", pci)
        self.assertIn("A short or zero batch re-opens HIMR", pci)
        self.assertNotIn("_rtl_pci_topaz_rx_pending", pci)

    def test_bundle_integrity_and_embedded_markers(self):
        manifest = json.loads((BUNDLE / "manifest.json").read_text())
        self.assertEqual(manifest["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(manifest["candidate_eligible"])
        self.assertFalse(manifest["safety"]["flash_supported"])
        for item in manifest["artifacts"]:
            path = BUNDLE / item["path"]
            self.assertEqual(path.stat().st_size, item["bytes"])
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), item["sha256"])
        self.assertIn(b"fw-warm-preclean reason=residual-ready", (BUNDLE / "modules/rtl8192ee.ko").read_bytes())
        pci = (BUNDLE / "modules/rtl_pci.ko").read_bytes()
        self.assertIn(b"OMRTL stage=rx-defer", pci)
        self.assertIn(b"OMRTL stage=rx-work", pci)

    def test_runner_is_isolated_and_flash_free(self):
        runner = (ROOT / "tools/run_realtek_warm_rxguard_isolated.ps1").read_text()
        self.assertIn('topology = "isolated"', runner)
        self.assertIn('bridge_created = $false', runner)
        self.assertIn('test ! -e /sys/class/net/br0', runner)
        self.assertIn("OMRTL_UART_CAPTURE_GATE_PASS", runner)
        self.assertNotIn("flashcp", runner)
        self.assertNotIn("mtd_debug", runner)


if __name__ == "__main__":
    unittest.main()
