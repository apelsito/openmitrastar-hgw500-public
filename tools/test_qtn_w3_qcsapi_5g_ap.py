from __future__ import annotations

import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[1]
REMOTE = ROOT / "tools/qtn_w3_qcsapi_5g_ap_remote.sh"
ROLLBACK = ROOT / "tools/qtn_w3_qcsapi_5g_rollback_remote.sh"
RUNNER = ROOT / "tools/run_qtn_w3_qcsapi_5g_ap.py"
BUILDER = ROOT / "tools/build_qtn_w3_qcsapi_runtime.py"


class Qcsapi5gApOfflineTests(unittest.TestCase):
    def test_python_is_valid(self) -> None:
        ast.parse(RUNNER.read_text(encoding="utf-8"))
        ast.parse(BUILDER.read_text(encoding="utf-8"))

    def test_ram_only_and_no_flash_surface(self) -> None:
        text = REMOTE.read_text(encoding="utf-8") + RUNNER.read_text(encoding="utf-8")
        self.assertIn("W3_RAM_ONLY", text)
        self.assertIn('"W3_FLASH_ENABLE": "0"', text)
        self.assertNotRegex(
            text,
            re.compile(r"\b(?:flash_erase|nandwrite|mtd_debug|ubiformat|flashcp)\b"),
        )

    def test_fixed_regulatory_profile(self) -> None:
        text = REMOTE.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        for marker in (
            "set_regulatory_region wifi0 es",
            "set_bw wifi0 80",
            "set_channel wifi0 36",
            "set_SSID wifi0 OpenMitraStar-5G",
            "get_regulatory_channels es 80",
            "W3_DFS_BYPASS",
            'test "$(value W3_BRIDGE)" = br0',
            'test "$(value W3_RF_ENABLE)" = 1',
            "bridge=$(value W3_BRIDGE)",
            "rf_enable=$(value W3_RF_ENABLE)",
        ):
            self.assertIn(marker, text)
        self.assertIn('"W3_BRIDGE": "br0"', runner)
        self.assertIn('"W3_RF_ENABLE": "1"', runner)
        self.assertIn('bridge = gate["W3_BRIDGE"]', runner)

    def test_rf_transition_is_after_configuration_and_rollback_arm(self) -> None:
        text = REMOTE.read_text(encoding="utf-8")
        config = text.index("qc_set regulatory-region")
        bridge = text.index('brctl addif "$bridge" wifi0')
        rollback = text.index('log "rollback-armed')
        rf_write = "printf '%s\\n' \"$rf_enable\" >\"$rf_gate\""
        rf_open = text.index(rf_write)
        hostapd = text.index('"$runtime/bin/hostapd" -B')
        self.assertLess(config, bridge)
        self.assertLess(bridge, rollback)
        self.assertLess(rollback, rf_open)
        self.assertLess(rf_open, hostapd)
        self.assertEqual(text.count(rf_write), 1)
        self.assertIn('printf \'bridge=%s\\n\' "$bridge"', text)

    def test_external_psk_is_redacted_and_mode_0600(self) -> None:
        remote = REMOTE.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn("--psk-file", runner)
        self.assertIn('f"{remote_root}/private/wpa2.psk", "0600"', runner)
        self.assertIn("W3_PSK_BUNDLED", remote)
        self.assertIn("psk=redacted", remote)
        self.assertIn("wpa_passphrase=%s", remote)
        self.assertNotIn("qtn01234", remote)
        self.assertNotIn("stat -c", remote)
        self.assertIn("-rw-------", remote)

    def test_wpa2_aes_and_readbacks(self) -> None:
        text = REMOTE.read_text(encoding="utf-8")
        for marker in (
            "wpa=2",
            "wpa_key_mgmt=WPA-PSK",
            "wpa_pairwise=CCMP",
            "get_beacon_type wifi0",
            "get_IEEE11i_authentication_mode wifi0",
            "get_IEEE11i_encryption_modes wifi0",
            "get_key_passphrase wifi0 0",
            "state=ENABLED",
        ):
            self.assertIn(marker, text)

    def test_live_vap_state_replaces_brittle_old_dmesg_markers(self) -> None:
        remote = REMOTE.read_text(encoding="utf-8")
        self.assertIn("openmitrastar_single_vap_create", remote)
        self.assertIn("wlan_scan_ap", remote)
        self.assertIn("get_mode wifi0", remote)
        self.assertNotIn("qdrv_core_start_not_proven", remote)
        self.assertNotIn("vap_not_proven", remote)
        self.assertIn("mitrastar,product-watchdog-canary", remote)
        self.assertIn("watchdog_uptime_too_short", remote)

    def test_local_rollback_does_not_depend_on_ssh(self) -> None:
        remote = REMOTE.read_text(encoding="utf-8")
        rollback = ROLLBACK.read_text(encoding="utf-8")
        self.assertIn('test -e "$root/commit" || sh "$rollback" "$root" timeout "$bridge"', remote)
        self.assertIn("ifconfig wifi0 down", rollback)
        self.assertIn('bridge=${3:-br0}', rollback)
        self.assertIn('test "$bridge" = br0 || bridge=br0', rollback)
        self.assertIn('brctl delif "$bridge" wifi0', rollback)
        self.assertIn("printf '0\\n' >\"$gate\"", rollback)
        self.assertNotIn("ramssh", rollback)

    def test_fresh_management_commit_and_soak(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("W3_QCSAPI_5G_FRESH_SSH_COMMIT_PASS", text)
        self.assertIn("W3_QCSAPI_5G_SSH_SOAK_PASS", text)
        self.assertIn("private/hostapd.pid", text)
        self.assertIn("/var/run/hostapd/wifi0", text)
        self.assertIn('/sys/class/net/{bridge}/brif/wifi0', text)
        self.assertIn('/sys/class/net/{bridge}/brif/eth1_emac1', text)
        self.assertIn("wait_for_rollback", text)
        self.assertIn("capture_topaz_uart.ps1", text)

    def test_large_runtime_files_use_chunked_upload(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("ramssh_upload_chunked.py", text)
        self.assertIn("source.stat().st_size > 256 * 1024", text)


if __name__ == "__main__":
    unittest.main()
