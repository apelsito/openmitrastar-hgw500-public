#!/usr/bin/env python3

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/misc/qtn-topaz-recovery.c"
DTS = ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts"
KCONFIG = ROOT / "work/kernel-port/linux-5.10/drivers/misc/Kconfig.qtn-topaz"
FRAGMENT = ROOT / "work/kernel-port/configs/topaz-ramssh.fragment"
EVIDENCE = ROOT / "outputs/kernel-port/hgw500-controls/OEM_LED_BUTTON_EVIDENCE.md"
MANIFEST = ROOT / "outputs/kernel-port/hgw500-controls/manifest.json"

OEM_HASHES = {
    ROOT / "work/hgw500-rootfs-live/squashfs-root/usr/sbin/monitor_button":
        "efcafebf78c12f11e8c0ede7f04c4cbe086b59c5c7ac74f24cc7081e07e587e0",
    ROOT / "work/hgw500-rootfs-live/squashfs-root/sbin/monitor_wifi":
        "ffbdb7d3bf3b099a106be532df02595c8eef20da7ace0b27d43bc27746aca734",
    ROOT / "work/hgw500-rootfs-live/squashfs-root/usr/sbin/sys":
        "75c89924ef6a1871a3bd50d996c6dcb51a1dae3d4ff81fde0444f70fc39a09f6",
}


class Hgw500ControlsOfflineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.driver = DRIVER.read_text(encoding="utf-8")
        cls.dts = DTS.read_text(encoding="utf-8")
        cls.kconfig = KCONFIG.read_text(encoding="utf-8")
        cls.fragment = FRAGMENT.read_text(encoding="utf-8")
        cls.evidence = EVIDENCE.read_text(encoding="utf-8")

    def test_oem_inputs_are_the_reconstructed_binaries(self):
        for path, expected in OEM_HASHES.items():
            self.assertTrue(path.is_file(), path)
            actual = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(actual, expected, path)

    def test_exact_machine_and_explicit_opt_in(self):
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.driver)
        self.assertIn('mitrastar,wlan2g-controls', self.driver)
        self.assertIn('compatible = "mitrastar,hgw-500bna-qcv2"', self.dts)
        self.assertIn('mitrastar,wlan2g-controls;', self.dts)

    def test_oem_gpio_and_polarity_contract(self):
        for marker in (
            '#define HGW500_WLAN2G_LED_PIN\t11',
            '#define HGW500_WIFI_BUTTON_PIN\t2',
            '#define HGW500_WIFI5G_BUTTON_PIN\t4',
            'mitrastar,wlan2g-led-pin = <11>;',
            'mitrastar,wlan2g-led-active-low;',
            'mitrastar,wifi-button-pin = <2>;',
            'mitrastar,wifi-button-active-low;',
            'mitrastar,wifi-short-action-none;',
            'mitrastar,wifi-long-action-userspace-toggle;',
            'mitrastar,wifi5g-button-pin = <4>;',
            'mitrastar,wifi5g-button-active-low;',
            'mitrastar,wifi5g-short-action-qdrv-wps;',
            'mitrastar,wifi5g-long-action-userspace-toggle;',
        ):
            self.assertIn(marker, self.driver + self.dts)
        self.assertIn('rec->wlan_led_active_low', self.driver)
        self.assertNotIn('mitrastar,wlan2g-led-active-high;', self.dts)

    def test_gpio2_matches_exact_oem_long_toggle_policy(self):
        self.assertIn('GPIO2 short press: OEM no-action policy', self.driver)
        self.assertIn('"wifi2g-toggle", "gpio2"', self.driver)
        self.assertNotIn('hgw500_toggle_wlan2g(rec)', self.driver)
        long_body = re.search(
            r"static void hgw500_button_long\(.*?\n\}\n",
            self.driver,
            re.DOTALL,
        )
        self.assertIsNotNone(long_body)
        body = long_body.group(0).lower()
        self.assertIn('wifi2g-toggle', body)
        for forbidden in ('restart_handler', 'kernel_restart', 'reboot', 'mtd', 'flash', 'factory'):
            self.assertNotIn(forbidden, body)

    def test_gpio4_preserves_independent_oem_wps_and_hold_currents(self):
        for marker in (
            '#define HGW500_WIFI5G_SAMPLE_MS\t500',
            '#define HGW500_WIFI5G_HOLD_SAMPLES\t10',
            'wifi5g_low_samples',
            '"wifi5g-toggle", "gpio4"',
            'qdrv independently owns',
            'INIT_DELAYED_WORK(&rec->wifi5g_button_work',
            'cancel_delayed_work_sync(&rec->wifi5g_button_work)',
        ):
            self.assertIn(marker, self.driver)
        self.assertNotIn('"wps5g-start"', self.driver)

    def test_debounce_and_long_press_are_bounded(self):
        self.assertIn('debounce-interval = <50>;', self.dts)
        self.assertIn('mitrastar,wifi-release-ms = <500>;', self.dts)
        self.assertIn('mitrastar,long-press-ms = <5000>;', self.dts)
        self.assertIn('rec->debounce_ms < 20 || rec->debounce_ms > 500', self.driver)
        self.assertIn('rec->button_release_ms < 100 || rec->button_release_ms > 2000', self.driver)
        self.assertIn('rec->long_press_ms < 1000 || rec->long_press_ms > 10000', self.driver)
        self.assertIn('msecs_to_jiffies(HGW500_BUTTON_POLL_MS)', self.driver)

    def test_rear_button_release_chatter_is_coalesced(self):
        self.assertIn('msecs_to_jiffies(rec->button_release_ms)', self.driver)
        self.assertIn('raw_pressed && !rec->button_stable', self.driver)
        self.assertIn('!raw_pressed && rec->button_stable', self.driver)
        self.assertIn('coalesces a complete actuation into one release event', self.driver)

    def test_led_requires_wlan0_running_in_ap_mode(self):
        self.assertIn('netif_running(ndev)', self.driver)
        self.assertIn('ndev->ieee80211_ptr->iftype == NL80211_IFTYPE_AP', self.driver)
        self.assertIn('case NETDEV_POST_TYPE_CHANGE:', self.driver)
        self.assertIn('case NETDEV_PRE_TYPE_CHANGE:', self.driver)

    def test_stage0_alive_policy_is_explicit_and_target_gated(self):
        self.assertIn('bool stage0_alive_managed;', self.driver)
        self.assertIn('of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")', self.driver)
        self.assertIn('"mitrastar,stage0-alive-until-userspace-ready"', self.driver)
        self.assertIn('if (rec->led_pin != 7)', self.driver)
        self.assertIn('led_set_brightness(&rec->led, LED_FULL);', self.driver)
        self.assertIn('led_set_brightness(&rec->led, LED_OFF);', self.driver)
        self.assertIn('mitrastar,stage0-alive-until-userspace-ready;', self.dts)

    def test_config_enables_only_the_scoped_platform_extension(self):
        self.assertIn('config OPENMITRASTAR_HGW500_CONTROLS', self.kconfig)
        self.assertIn('depends on QTN_TOPAZ_RECOVERY && INPUT && NET', self.kconfig)
        for marker in (
            'CONFIG_INPUT=y',
            'CONFIG_INPUT_EVDEV=y',
            '# CONFIG_INPUT_KEYBOARD is not set',
            '# CONFIG_INPUT_MOUSE is not set',
            '# CONFIG_SERIO is not set',
            '# CONFIG_HID is not set',
            'CONFIG_OPENMITRASTAR_HGW500_CONTROLS=y',
        ):
            self.assertIn(marker, self.fragment)

    def test_evidence_records_gpio2_gpio11_and_oem_timing(self):
        for marker in ('GPIO2', 'GPIO11', 'active-low', '500000', 'five seconds'):
            self.assertIn(marker, self.evidence)

    def test_built_dtb_retains_exact_properties(self):
        wsl = shutil.which("wsl.exe") or shutil.which("wsl")
        if not wsl:
            self.skipTest("WSL unavailable")
        dtb = os.environ.get(
            "OM_Q1_CONTROLS_DTB",
            "/home/user/openmitrastar-build/hgw500-q1-controls-parity-20260820/kernel-out/arch/arc/boot/dts/topaz_mitrastar_ramssh.dtb",
        )
        completed = subprocess.run(
            [wsl, "dtc", "-I", "dtb", "-O", "dts", dtb],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=30,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stdout)
        for marker in (
            'mitrastar,wlan2g-led-pin = <0x0b>;',
            'mitrastar,wifi-button-pin = <0x02>;',
            'mitrastar,wifi5g-button-pin = <0x04>;',
            'mitrastar,wlan2g-ifname = "wlan0";',
            'mitrastar,long-press-ms = <0x1388>;',
        ):
            self.assertIn(marker, completed.stdout)

    def test_manifest_hashes_are_current_and_non_flash(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["classification"], "RAM-ONLY-NO-FLASH")
        self.assertFalse(manifest["hardware_executed"])
        self.assertFalse(manifest["flash_supported"])
        base = MANIFEST.parent
        for name, metadata in manifest["artifacts"].items():
            path = base / name
            self.assertEqual(path.stat().st_size, metadata["size"], name)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), metadata["sha256"], name)


if __name__ == "__main__":
    unittest.main()
