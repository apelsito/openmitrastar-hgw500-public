#!/usr/bin/env python3

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
DRIVER = (ROOT / "work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-early-wdt.c").read_text(encoding="utf-8")
KCONFIG = (ROOT / "work/kernel-port/linux-5.10/drivers/misc/Kconfig.qtn-topaz").read_text(encoding="utf-8")
DTS = (ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts").read_text(encoding="utf-8")
RAMSSH = (ROOT / "work/kernel-port/configs/topaz-ramssh.fragment").read_text(encoding="utf-8")
FRAGMENT = (ROOT / "work/mission-state/w5-product-watchdog-candidate/kernel/topaz-product-watchdog.fragment").read_text(encoding="utf-8")
BUILD = (ROOT / "work/mission-state/w5-product-ram-candidate/scripts/build_product_ram_candidate.sh").read_text(encoding="utf-8")


class ProductWatchdogTests(unittest.TestCase):
    def test_arm_requires_exact_machine_and_explicit_opt_in(self):
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', DRIVER)
        self.assertIn('qtn_topaz_early_wdt_param_seen', DRIVER)
        self.assertIn('mitrastar,product-watchdog-canary', DRIVER)
        self.assertIn('reason=no-explicit-opt-in', DRIVER)
        init = DRIVER[DRIVER.index("static int __init qtn_topaz_early_wdt_init"):]
        self.assertNotIn('qtn_topaz_early_wdt_arm("early_initcall")', init)

    def test_dt_policy_and_product_fragment_are_exact(self):
        self.assertIn('mitrastar,product-watchdog-canary;', DTS)
        self.assertIn('qtn,product-watchdog-timeout-range = <15>;', DTS)
        self.assertIn('qtn,product-watchdog-pet-seconds = <1>;', DTS)
        self.assertIn('CONFIG_QTN_TOPAZ_EARLY_WDT_CANARY=y', FRAGMENT)
        self.assertIn('# CONFIG_QTN_TOPAZ_EARLY_WDT_CANARY is not set', RAMSSH)

    def test_normal_timer_pets_and_hard_lock_can_expire(self):
        pet = DRIVER[DRIVER.index("static void qtn_topaz_early_wdt_pet"):DRIVER.index("static int __init qtn_topaz_early_wdt_arm")]
        self.assertIn('QTN_TOPAZ_WDT_COUNTER_RESTART', pet)
        self.assertIn('qtn_topaz_early_wdt_pet_seconds * HZ', pet)
        self.assertIn('OMWDT stage=pet first=1', pet)
        self.assertNotIn('workqueue', pet.lower())

    def test_lifecycle_markers_are_bounded(self):
        for marker in ('stage=opt-in', 'stage=armed', 'stage=pet', 'stage=skip', 'stage=failed'):
            self.assertIn(marker, DRIVER)
        self.assertEqual(DRIVER.count('stage=pet first=1'), 1)

    def test_kconfig_help_matches_runtime(self):
        block = KCONFIG[KCONFIG.index("config QTN_TOPAZ_EARLY_WDT_CANARY"):KCONFIG.index("config QTN_TOPAZ_HEAD_WDT_CANARY")]
        self.assertIn("Merely enabling this option does not", block)
        self.assertIn("exact MitraStar machine", block)
        self.assertIn("approximately forty seconds", block)

    def test_w5_builder_has_separate_opt_in_and_gates(self):
        self.assertIn('OM_PRODUCT_WDT_FRAGMENT', BUILD)
        self.assertIn('--enable QTN_TOPAZ_EARLY_WDT_CANARY', BUILD)
        self.assertIn('product_watchdog_canary', BUILD)
        self.assertIn('product_watchdog_hardware_timing', BUILD)
        self.assertIn('OM_PRODUCT_TFTP_OUTPUT', BUILD)
        self.assertIn('OM_PRODUCT_RAM_ARTIFACT_DIR', BUILD)

    def test_oem_timeout_basis_is_documented(self):
        soc = (ROOT / "work/sources/Quantenna-GPL/drivers/ruby/soc.h").read_text(encoding="utf-8")
        self.assertIn("watchdog timer for 5 Seconds", soc)
        self.assertIn("writel(0xC", soc)


if __name__ == "__main__":
    unittest.main()

