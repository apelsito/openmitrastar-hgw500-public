#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/diagnostics/hgw500-gpio4-diag/hgw500-gpio4-diag.c"


class Gpio4DiagnosticTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = SOURCE.read_text(encoding="utf-8")

    def test_exact_target_and_explicit_arm(self):
        self.assertIn('module_param(diagnostic, bool, 0400)', self.source)
        self.assertIn('if (!diagnostic)', self.source)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.source)

    def test_oem_gpio4_active_low_contract(self):
        self.assertIn('#define HGW500_GPIO4\t\t4', self.source)
        self.assertIn('return !(readl(', self.source)
        self.assertIn('active_low=1', self.source)

    def test_bounded_debounce_and_release_coalescing(self):
        for marker in (
            'HGW500_POLL_MS\t\t20',
            'HGW500_PRESS_DEBOUNCE_MS\t50',
            'HGW500_RELEASE_QUIET_MS\t500',
            'HGW500_LONG_PRESS_MS\t5000',
            'raw && !diag->stable',
            '!raw && diag->stable',
            '!diag->long_reported',
        ):
            self.assertIn(marker, self.source)

    def test_markers_are_observational_only(self):
        for marker in (
            'kind=%s', '"short"', '"long"', 'kind=pressed',
            'released-after-long', 'action=observation-only',
        ):
            self.assertIn(marker, self.source)

    def test_no_control_or_persistence_paths(self):
        lowered = self.source.split("*/", 1)[1].lower()
        for forbidden in (
            'wps_pbc', 'hostapd', 'qcsapi', 'wifi2g-toggle', 'wifi5g-toggle',
            'kernel_restart', 'orderly_reboot', '/dev/mtd', 'flash_erase',
            'call_usermodehelper', 'kobject_uevent_env',
        ):
            self.assertNotIn(forbidden, lowered)

    def test_cleanup_is_synchronous(self):
        self.assertIn('cancel_delayed_work_sync(&probe->work)', self.source)
        self.assertIn('input_unregister_device(probe->input)', self.source)
        self.assertIn('iounmap(probe->gpio)', self.source)


if __name__ == "__main__":
    unittest.main()
