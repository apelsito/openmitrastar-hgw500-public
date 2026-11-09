import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HBM = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/hbm.c"
RUNNERS = (
    ROOT / "tools/qtn_w3_hbm_only_remote.sh",
    ROOT / "tools/qtn_w3_congest_only_remote.sh",
    ROOT / "tools/qtn_w3_switch_tqe_only_remote.sh",
    ROOT / "tools/qtn_w3_switch_tqe_dramlab_remote.sh",
    ROOT / "tools/qtn_w3_fwt_tdes_probe_remote.sh",
    ROOT / "tools/qtn_w3_fwt_reset_probe_remote.sh",
    ROOT / "tools/qtn_w3_fwt_reflect_probe_remote.sh",
    ROOT / "tools/qtn_w3_fwt_ctrl_only_remote.sh",
    ROOT / "tools/qtn_w3_switch_emac_handoff_remote.sh",
)


class HbmWarmLifecycleTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = HBM.read_text(encoding="utf-8")

    def test_exact_target_and_explicit_parameter_gate(self):
        self.assertIn("module_param(w3_hbm_lifecycle_enable, int, 0400)", self.source)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.source)
        self.assertIn("hw_rev != HARDWARE_REVISION_TOPAZ_A2", self.source)
        self.assertIn("OMHBM stage=gate-refused", self.source)

    def test_preflight_is_read_only_before_pool_or_payload_writes(self):
        init = self.source.index("static int __init topaz_hbm_module_init")
        preflight = self.source.index('omhbm_wait_lhost_idle("preflight")', init)
        disable = self.source.index('omhbm_disable_csr("preinit")', preflight)
        pool_init = self.source.index("topaz_hbm_init_payload_pools()", disable)
        self.assertLess(preflight, disable)
        self.assertLess(disable, pool_init)
        self.assertIn("destructive_writes=0", self.source[preflight:pool_init])

    def test_wait_is_bounded_and_does_not_cancel_pool_req(self):
        self.assertIn("#define OMHBM_WAIT_US", self.source)
        self.assertRegex(self.source, r"waited\s*<\s*OMHBM_WAIT_US")
        self.assertIn("return -ETIMEDOUT", self.source)
        writes = re.findall(
            r"qtn_mproc_sync_mem_write(?:_wmb)?\s*\(\s*TOPAZ_HBM_POOL_REQ",
            self.source,
        )
        self.assertEqual(writes, [], "the port must not forge/cancel POOL_REQ DONE")

    def test_each_pool_and_module_exit_drain_before_teardown(self):
        self.assertIn('omhbm_wait_lhost_idle("pool-drain")', self.source)
        self.assertIn('omhbm_wait_lhost_idle("exit-drain")', self.source)
        self.assertIn('omhbm_disable_csr("exit")', self.source)
        self.assertIn('omhbm_clear_pool_registers("exit")', self.source)
        self.assertRegex(
            self.source,
            r"g_pools_inited\s*=\s*0;\s*\n\s*topaz_hbm_stat_exit",
        )

    def test_csr_and_irq21_route_are_disabled(self):
        self.assertIn("RUBY_SYS_CTL_LHOST_ORINT_EN", self.source)
        self.assertIn("after = before & ~TOPAZ_HBM_INT_EN", self.source)
        self.assertIn("OMHBM_Q_EN_MASK", self.source)
        self.assertIn("OMHBM_INT_EN_MASK", self.source)
        self.assertIn("OMHBM_INT_MASK_MASK", self.source)
        self.assertIn("OMHBM_INT_RAW_MASK", self.source)
        self.assertIn("stage=%s-csr-disabled", self.source)

    def test_all_hardware_runners_pass_explicit_gate(self):
        for runner in RUNNERS:
            text = runner.read_text(encoding="utf-8")
            self.assertRegex(
                text,
                r'hbm\.ko["\']?\s+w3_hbm_lifecycle_enable=1',
                runner.name,
            )


if __name__ == "__main__":
    unittest.main()
