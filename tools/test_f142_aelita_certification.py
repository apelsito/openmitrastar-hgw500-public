#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_f142_5g_aelita_certification.py"


class F142AelitaCertificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = RUNNER.read_text(encoding="utf-8")

    def test_preflight_is_pinned_to_f142_artifacts(self) -> None:
        self.assertIn('marker = f"OM{profile}_AELITA_PREFLIGHT_PASS"', self.text)
        self.assertIn("EXPECTED_QDRV_SHA", self.text)
        self.assertIn("92381049063ec04d4e6e744c340345a1f1cb2feea18d4c7765a3b35b9f22d343", self.text)
        self.assertIn("Tx-Power[:=]__TXPOWER__ dBm", self.text)
        self.assertIn("--expected-txpower-dbm", self.text)
        self.assertIn('"__TXPOWER__", str(txpower_dbm)', self.text)

    def test_f143_profile_is_pinned_to_rebuilt_qdrv(self) -> None:
        self.assertIn('"F143": "OPENMITRASTAR_F143_5G_AELITA_CERTIFICATION"', self.text)
        self.assertIn("db498a534bf388f2e0ddf75e6802c99fb868e9dc6e9a4e3a56f5ab69f785a8e9", self.text)
        self.assertIn('choices=sorted(PROFILE_QDRV_SHA)', self.text)

    def test_f144_profile_is_pinned_to_qdisc_binding_qdrv(self) -> None:
        self.assertIn('"F144": "OPENMITRASTAR_F144_5G_AELITA_CERTIFICATION"', self.text)
        self.assertIn("89139dbf883e254b8b74ad57a61d8b35ed5bb85b4654cf73787910134016c684", self.text)

    def test_f145_profile_is_pinned_to_node_scheduler_trace_qdrv(self) -> None:
        self.assertIn('"F145": "OPENMITRASTAR_F145_5G_AELITA_CERTIFICATION"', self.text)
        self.assertIn("5efe71b0431b5867f172a1abebe0b99534e07f7db9f6c5c1dcb89bc6c1c79341", self.text)

    def test_f146_profile_is_pinned_to_auc_submit_trace_qdrv(self) -> None:
        self.assertIn('"F146": "OPENMITRASTAR_F146_5G_AELITA_CERTIFICATION"', self.text)
        self.assertIn("f92761b610eb715d5811275d00935391f9e9fbfb50e213949f3d019f276273c4", self.text)

    def test_f147_profile_is_pinned_to_readonly_get_qdrv(self) -> None:
        self.assertIn('"F147": "OPENMITRASTAR_F147_5G_AELITA_CERTIFICATION"', self.text)
        self.assertIn("ed2a1ce601089bb2cbb6b52d0d4444839da927dd6443124d11856cddc900f387", self.text)

    def test_runner_uses_openssh_monitor_and_never_flashes(self) -> None:
        self.assertIn("q3_client_stream_openssh.py", self.text)
        self.assertIn('"router_flash": False', self.text)
        self.assertNotIn("om-radio5-stop", self.text)
        self.assertNotIn("om-radio5-start", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
