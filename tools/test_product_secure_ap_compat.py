#!/usr/bin/env python3

from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "work/mission-state/w4-rootfs-product"
BUILD = (PRODUCT / "scripts/build_product_rootfs.sh").read_text(encoding="utf-8")
RADIO = (PRODUCT / "rootfs/usr/sbin/om-radio-start").read_text(encoding="utf-8")
CGI = (PRODUCT / "rootfs/www/cgi-bin/config").read_text(encoding="utf-8")
DISPATCHER = (
    PRODUCT / "rootfs/usr/libexec/openmitrastar/om-oem-cgi"
).read_text(encoding="utf-8")
READY = (PRODUCT / "rootfs/etc/init.d/S90-ready").read_text(encoding="utf-8")
DEGRADED = (PRODUCT / "rootfs/usr/sbin/om-degraded-clear").read_text(encoding="utf-8")
DTS = (ROOT / "work/kernel-port/linux-5.10/arch/arc/boot/dts/topaz_mitrastar_ramssh.dts").read_text(encoding="utf-8")
RUNNER = (ROOT / "tools/run_product_rootfs_secure_ap.ps1").read_text(encoding="utf-8")


class SecureApCompatibilityTests(unittest.TestCase):
    def test_busybox_ls_is_required_and_installed(self):
        required = re.search(r"required_applets='([^']+)'", BUILD).group(1).split()
        self.assertIn("ls", required)
        symlinks = re.search(r"for applet in (.*?)\; do\n\tln -s busybox", BUILD, re.DOTALL).group(1).split()
        self.assertIn("ls", symlinks)

    def test_psk_mode_uses_busybox_compatible_ls(self):
        self.assertIn('psk_mode=$(ls -ld "$psk_file"', RADIO)
        self.assertIn('[ "$psk_mode" = -rw------- ]', RADIO)
        self.assertNotIn('stat -c %a "$psk_file"', RADIO)

    def test_bridge_policy_uses_sysfs_exact_values(self):
        for marker in (
            'bridge_sysfs="/sys/class/net/$br_if/bridge"',
            'printf \'0\\n\' >"$bridge_sysfs/stp_state"',
            'printf \'0\\n\' >"$bridge_sysfs/forward_delay"',
            'printf \'720000\\n\' >"$bridge_sysfs/ageing_time"',
        ):
            self.assertIn(marker, RADIO)
        self.assertNotIn('brctl setageing "$br_if"', RADIO)

    def test_cgi_token_mode_uses_ls_and_stays_locked(self):
        self.assertIn('exec "${OM_WEB_DISPATCHER:-/usr/libexec/openmitrastar/om-oem-cgi}" config', CGI)
        self.assertIn('metadata=$(ls -ln "$password_hash_file"', DISPATCHER)
        self.assertIn('[ "$mode" = -rw------- ]', DISPATCHER)
        self.assertIn('chmod 600 "$tmp"', DISPATCHER)
        self.assertIn('403 Forbidden', DISPATCHER)
        self.assertNotIn('stat -c %a "$token_file"', DISPATCHER)

    def test_degraded_cleanup_is_after_radio_ready_and_exact(self):
        self.assertLess(RADIO.index("OMRADIO_READY interface="), RADIO.index("om-degraded-clear S50-radio-ap"))
        self.assertIn('S25-origin-import|S34-ipv6-local-policy|S35-radio-modules|S44-oem-web|S50-radio-ap)', DEGRADED)
        self.assertIn("$1 != service", DEGRADED)
        self.assertIn("printf 'ready\\n' >\"$boot_state\"", DEGRADED)

    def test_green_stage0_contract_remains_intact(self):
        self.assertIn('qtn,recovery-led-pin = <9>;', DTS)
        self.assertIn('qtn,recovery-led-active-low;', DTS)
        self.assertIn('mitrastar,stage0-alive-until-userspace-ready;', DTS)
        self.assertLess(READY.index('/usr/sbin/om-stage0-ready'), READY.index('OMPRODUCT_READY'))

    def test_secure_ap_runner_is_ram_only_and_redacted(self):
        self.assertIn('OPENMITRASTAR_PRODUCT_SECURE_AP_RAM_ONLY', RUNNER)
        self.assertIn('classification = "RAM-ONLY-NO-FLASH"', RUNNER)
        self.assertIn('psk = "external-0600-redacted"', RUNNER)
        self.assertIn('flash_supported = $false', RUNNER)
        self.assertNotIn('Get-Content -LiteralPath $PskFile', RUNNER)

    def test_hostapd_wpa2_profile_keeps_oem_parity_timing(self):
        for line in (
            "'beacon_int=100'",
            "'dtim_period=3'",
            "'wpa_group_rekey=86400'",
            "'wpa_ptk_rekey=0'",
            "'ieee80211w=0'",
        ):
            self.assertIn(line, RADIO)
        self.assertIn('"hostapd_oem_parity": {"beacon_int": 100, "dtim_period": 3, "ieee80211w": 0, "wpa_group_rekey": 86400, "wpa_ptk_rekey": 0}', BUILD)


if __name__ == "__main__":
    unittest.main()
