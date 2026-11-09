#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
BUILD = ROOT / "tools/build_product_netss_ioss_fwtfix_incremental.sh"
ARTIFACT = ROOT / "outputs/kernel-port/product-netss-ioss-fwtfix-20260818-0415-RAM-ONLY-NO-FLASH"
MANIFEST = ARTIFACT / "manifest.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class TopazNetssIossBootPulseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.driver = DRIVER.read_text(encoding="utf-8")
        cls.dts = DTS.read_text(encoding="utf-8")
        start = cls.driver.index("static int hgw500_netss_ioss_boot_pulse")
        end = cls.driver.index("\n}\n", start) + 2
        cls.pulse = cls.driver[start:end]

    def test_exact_machine_and_explicit_dt_property(self) -> None:
        self.assertIn('"mitrastar,netss-ioss-reset-pulse"', self.pulse)
        self.assertIn(
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            self.pulse,
        )
        self.assertIn("mitrastar,netss-ioss-reset-pulse;", self.dts)
        recovery = self.dts.index("recovery@e0000000")
        prop = self.dts.index("mitrastar,netss-ioss-reset-pulse;", recovery)
        emac = self.dts.index("emac1: ethernet@e8000000")
        self.assertLess(recovery, prop)
        self.assertLess(prop, emac)

    def test_exact_mask_wait_and_no_enet0(self) -> None:
        self.assertIn("HGW500_NETSS_IOSS_MASK != 0x000000a0U", self.pulse)
        self.assertIn("HGW500_NETSS_IOSS_MASK & HGW500_RESET_ENET0", self.pulse)
        self.assertIn("mdelay(HGW500_NETSS_IOSS_WAIT_MS)", self.pulse)
        self.assertIn("#define HGW500_NETSS_IOSS_WAIT_MS 50", self.driver)
        self.assertIn("enet0_reset=0", self.pulse)

    def test_fail_closed_preconditions_and_exact_readback(self) -> None:
        for marker in (
            "mask_before != 0",
            "HGW500_NETSS_IOSS_MASK",
            "mask_asserted != HGW500_NETSS_IOSS_MASK",
            "vec_released != vec_before",
            "mask_released != mask_before",
            "OMNETSS stage=precondition-refused",
            "OMNETSS stage=readback-failed",
        ):
            self.assertIn(marker, self.pulse)

    def test_exact_write_order_and_only_sysctl_vector_registers(self) -> None:
        mask = self.pulse.index("writel(HGW500_NETSS_IOSS_MASK,\n\t       rec->sysctl + SYSCTL_CPU_VEC_MASK)")
        assert_reset = self.pulse.index("writel(0, rec->sysctl + SYSCTL_CPU_VEC)")
        wait = self.pulse.index("mdelay(HGW500_NETSS_IOSS_WAIT_MS)")
        release = self.pulse.index("writel(HGW500_NETSS_IOSS_MASK, rec->sysctl + SYSCTL_CPU_VEC)")
        clear = self.pulse.index("writel(0, rec->sysctl + SYSCTL_CPU_VEC_MASK)")
        self.assertLess(mask, assert_reset)
        self.assertLess(assert_reset, wait)
        self.assertLess(wait, release)
        self.assertLess(release, clear)
        self.assertEqual(self.pulse.count("writel("), 4)
        for forbidden in (
            "TOPAZ_FWT",
            "RXP_CTRL",
            "DMA",
            "TQE",
            "VLAN",
            "qdrv",
            "wlan",
        ):
            self.assertNotIn(forbidden, self.pulse)

    def test_one_shot_and_probe_order_before_other_resources(self) -> None:
        self.assertIn("hgw500_netss_ioss_pulse_done", self.pulse)
        self.assertIn("hgw500_netss_ioss_pulse_lock", self.pulse)
        probe = self.driver.index("static int qtn_topaz_recovery_probe")
        sysctl = self.driver.index("rec->sysctl = devm_platform_ioremap_resource(pdev, 0)", probe)
        pulse = self.driver.index("hgw500_netss_ioss_boot_pulse(rec, dev)", sysctl)
        gpio = self.driver.index("rec->gpio = devm_platform_ioremap_resource(pdev, 1)", pulse)
        self.assertLess(sysctl, pulse)
        self.assertLess(pulse, gpio)

    def test_incremental_builder_is_ram_only_and_hash_manifested(self) -> None:
        text = BUILD.read_text(encoding="utf-8")
        self.assertIn("incremental_kernel_build", text)
        self.assertIn('"build_log": info(artifact / "build.log")', text)
        self.assertIn("RAM-ONLY-NO-FLASH", text)
        self.assertIn("hardware_actions", text)
        self.assertIn("flash_supported", text)
        self.assertIn("mitrastar,netss-ioss-reset-pulse", text)
        self.assertNotIn("2026" + "0819", text)

    def test_built_artifact_manifest(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["generated_utc"], "2026-08-18T04:15:00+00:00")
        self.assertTrue(manifest["incremental_kernel_build"])
        self.assertFalse(manifest["hardware_actions"])
        self.assertFalse(manifest["flash_supported"])
        self.assertEqual(manifest["dt_gate"]["pulse_mask"], "0x000000a0")
        self.assertFalse(manifest["dt_gate"]["enet0_reset"])
        for artifact in manifest["artifacts"].values():
            path = ARTIFACT / artifact["file"]
            if artifact["file"] == "linux510-product-netss-ioss-fwtfix-v1-RAM-ONLY.bin":
                path = ROOT / "work/tftp/omvl" / artifact["file"]
            self.assertEqual(sha(path), artifact["sha256"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
