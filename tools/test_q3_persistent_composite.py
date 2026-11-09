#!/usr/bin/env python3

import hashlib
import json
import os
import re
import stat
import subprocess
import unittest
from pathlib import Path


WORKSPACE = Path(__file__).resolve().parents[1]
LANE = Path(os.environ.get(
    "OM_Q3_LANE", WORKSPACE / "work/mission-state/q3-persistent-composite"
))
BUILD = LANE / "build"
ROOTFS_BUILD = LANE / "rootfs-build"
STAGE = Path(os.environ.get("OM_Q3_STAGE_A", "/home/user/openmitrastar-build/q3-persistent/rootfs-a"))
BASE = os.environ.get(
    "OM_Q3_BASE_NAME", "openmitrastar-linux510-q3-persistent-v1-LZMA-OFFLINE-NO-FLASH"
)
Q2_ROOTFS = WORKSPACE / "work/mission-state/q2-integrated-lzma-candidate/rootfs-build/openmitrastar-q2-parity-rootfs-v1.squashfs"
Q2_WEB = WORKSPACE / "work/mission-state/q2-mtd4-flash-candidate/openmitrastar-linux510-q2-parity-v1-webformat.bin"
TFTP = Path(os.environ.get(
    "OM_Q3_TFTP_PATH",
    WORKSPACE / "work/tftp/omvl/linux510-q3-persistent-v1-LZMA-RAM-TEST-NO-FLASH.bin",
))
PROFILE = os.environ.get("OM_Q3_PROFILE", "autostart-secure")
AUTOSTART = os.environ.get("OM_Q3_AUTOSTART", "1") == "1"
TQE_RING_ENTRIES = int(os.environ.get("OM_Q3_TQE_RING_ENTRIES", "256"))
BOOTENV_ARTIFACT = WORKSPACE / "outputs/kernel-port/q3-bootenv-wifiaddr-readonly"
CONTROLS_ARTIFACT = Path(os.environ.get(
    "OM_Q3_CONTROLS_ARTIFACT",
    WORKSPACE / "outputs/kernel-port/hgw500-led-controls-20260821",
))
BOOTENV_DTS = CONTROLS_ARTIFACT / "topaz_mitrastar_ramssh.dts"
BOOTENV_MANIFEST = BOOTENV_ARTIFACT / "manifest.json"
EXPECTED_CONTROLS_DTB = os.environ.get(
    "OM_Q3_EXPECTED_CONTROLS_DTB_SHA256",
    "7fa81f07fb13aa0d4caf549ce0e0d9fbb82bdee5f06f437a779309a4173f6d83",
)


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class Q3PersistentCompositeTests(unittest.TestCase):
    def test_rdinit_root_symlink_is_exact(self) -> None:
        rdinit = STAGE / "init"
        self.assertTrue(rdinit.is_symlink())
        self.assertEqual("sbin/init", os.readlink(rdinit))
        self.assertTrue((STAGE / "sbin/init").exists())

    def test_q2_is_exact_protected_base(self) -> None:
        self.assertEqual("951b31584e0fa7ce7734ba8d772327237236b9751f452da9aad9e1ec7c59fe95", sha(Q2_ROOTFS))
        self.assertEqual("cbe904ab7a807838fa12077fab924c79ce3c112a5ef40727cbaf9ec98f638cf1", sha(Q2_WEB))
        manifest = json.loads((BUILD / "manifest.json").read_text())
        self.assertTrue(manifest["protected_q2"]["unchanged"])
        self.assertEqual(sha(Q2_WEB), manifest["protected_q2"]["hashes"]["persistent_webformat"])

    def test_autonomous_entropy_replaces_uart_seed(self) -> None:
        helper = STAGE / "usr/sbin/om-entropy-seed"
        self.assertEqual("b078bb6de4b889963daadf42b3665bc8f808155df1ac54410f12147b3ce222f6", sha(helper))
        strings = subprocess.check_output(["strings", str(helper)], text=True)
        self.assertIn("jitterentropy_rng", strings)
        self.assertIn("OMPRODUCT_ENTROPY_LOCAL_OK", strings)
        self.assertNotIn("ENTROPY_SEED_REQUIRED", strings)
        rcs = (STAGE / "etc/init.d/rcS").read_text()
        self.assertIn("policy=entropy-fail-closed", rcs)
        ssh = (STAGE / "usr/sbin/om-ssh").read_text()
        self.assertIn("entropy-gate-not-ready", ssh)

    def test_origin_mtd5_is_read_only_runtime_import(self) -> None:
        self.assertTrue((STAGE / "etc/init.d/S25-origin-import").is_file())
        importer = STAGE / "usr/sbin/om-origin-import"
        self.assertEqual("85cdb3d25317eddbfd973939ace81ed139f2f6e1be3a86ae8d34b4609d40d4fb", sha(importer))
        text = importer.read_text()
        self.assertIn("readonly-mount-missing", text)
        self.assertIn("mount-not-readonly", text)
        self.assertIn("proc_mounts_file", text)
        self.assertIn("secrets_root=${OM_SECRETS_ROOT:-/run/openmitrastar/secrets}", text)
        self.assertIn('"$secrets_root/wpa2.psk"', text)
        self.assertIn('od -x |', text)
        self.assertIn('[ "$magic" = 1985 ]', text)
        self.assertNotIn("od -An -tx1", text)
        self.assertNotIn("mount -t jffs2 -o rw", text)
        policy = STAGE / "usr/share/openmitrastar/origin-mtd5/current-unit.policy"
        self.assertEqual(stat.S_IMODE(policy.stat().st_mode), 0o600)
        self.assertEqual("dbcb46f33e8bca80223042ac112e0b7cbd9c990b3f117b2cf2a53d9c4c71940e", sha(policy))
        for forbidden in ("flash_erase", "nandwrite", "mtd_debug", "mtd_write"):
            self.assertFalse(any(STAGE.rglob(forbidden)), forbidden)

        persist = STAGE / "usr/sbin/om-persist"
        self.assertEqual("a411323a97391c76f2d7439dd5ae99263d189151e3e0b76e79699ec0cee8af20", sha(persist))
        persist_text = persist.read_text()
        self.assertIn('run_mount -t jffs2 -o ro "$block_dev" "$persist_mount"', persist_text)
        self.assertNotIn('run_mount -t jffs2 -o ro,noatime', persist_text)

    def test_2g_autostart_is_preserved(self) -> None:
        for rel in ("etc/init.d/S35-radio-modules", "etc/init.d/S50-radio-ap"):
            path = STAGE / rel
            self.assertTrue(path.is_file(), rel)
            self.assertTrue(path.stat().st_mode & stat.S_IXUSR, rel)
        self.assertTrue((STAGE / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko").is_file())
        s35 = STAGE / "etc/init.d/S35-radio-modules"
        self.assertEqual("bc79afe8f23eab00db8864a8a0b676c072eaf4131b1320523e55f49c9615ec5d", sha(s35))
        s35_text = s35.read_text()
        self.assertIn('while [ "$attempt" -lt 10 ]', s35_text)
        self.assertIn("sleep 3", s35_text)
        self.assertIn("OMRADIO_MODULE_BOOT_PASS", s35_text)
        self.assertIn("OMRADIO_MODULE_BOOT_FAIL", s35_text)

        loader = STAGE / "usr/sbin/om-radio-modules"
        expected_loader = os.environ.get(
            "OM_Q3_EXPECTED_RADIO_MODULES_SHA256",
            "428a91a54a0fce4d1475219142eb91e86999edaffcd9a1e4b5b4015b6d733786",
        )
        self.assertEqual(expected_loader, sha(loader))
        loader_text = loader.read_text()
        self.assertIn("msi=0 dma64=0 aspm=0 ips=0 fwlps=0 swenc=1", loader_text)
        self.assertIn("disable_watchdog=0 debug_level=0 hgw500_force_txbd64_width=1", loader_text)
        self.assertIn("hgw500_txbd_be_data_split=1", loader_text)
        self.assertIn("profile=all64-mcs7-eapol-mgntq-q2", loader_text)
        self.assertIn('/usr/sbin/ram-insmod-qtn', loader_text)
        self.assertIn('"$module_loader" "$path" "$parameters"', loader_text)
        self.assertIn("OMRADIO_MODULE_PARAMS_PASS", loader_text)
        self.assertIn("radio2g_eapol_mgnt_queue=1", loader_text)
        self.assertIn("hgw500_eapol_mgnt_queue=$radio2g_eapol_mgnt_queue", loader_text)
        self.assertIn("verify_optional_module_parameter rtl_pci", loader_text)
        self.assertIn("OMRADIO_MODULE_PARAM_WARN", loader_text)
        self.assertIn('refuse "module-param-rtl8192ee-$parameter"', loader_text)

        s50 = STAGE / "etc/init.d/S50-radio-ap"
        self.assertEqual("1a0bb8918139fc08f0a06d7c1153c81eb31b728fa7c450a61f9af98120921d71", sha(s50))
        s50_text = s50.read_text()
        self.assertIn('while [ "$attempt" -lt 30 ]', s50_text)
        self.assertIn("radio2g/modules-ready", s50_text)
        self.assertIn("/sys/class/net/wlan0", s50_text)
        self.assertIn("OMRADIO_AP_BOOT_FAIL", s50_text)
        self.assertIn("exec /usr/sbin/om-radio-start", s50_text)
        start = STAGE / "usr/sbin/om-radio-start"
        expected_start = os.environ.get(
            "OM_Q3_EXPECTED_RADIO_START_SHA256",
            "46bd158c0e0c200cc5f8adea30e962cbfe3b8a72b7defbb17d4d70aaa6c9cd97",
        )
        self.assertEqual(expected_start, sha(start))
        start_text = start.read_text()
        self.assertNotIn('"$hostapd" -B', start_text)
        self.assertIn('"$iw" reg set "$country"', start_text)
        self.assertIn("OMRADIO_REGDOM_SET country=$country", start_text)
        self.assertIn("OMRADIO_REGDOM_WARN country=$country", start_text)
        self.assertIn('"$hostapd" -f "$state/hostapd.log" "$state/hostapd.conf"', start_text)
        self.assertIn('printf \'%s\\n\' "$!" >"$state/hostapd.pid"', start_text)
        self.assertIn('kill -0 "$(cat "$state/hostapd.pid")"', start_text)
        self.assertIn("state=ENABLED", start_text)

    def test_oem_gpio4_dual_current_and_persistent_5g_toggle_are_embedded(self) -> None:
        control = (STAGE / "usr/sbin/om-control-event").read_text()
        toggle = (STAGE / "usr/sbin/om-radio5g-toggle").read_text()
        config_get = (STAGE / "usr/sbin/om-config-get").read_text()
        defaults = (STAGE / "usr/share/openmitrastar/config-schema/v1/defaults.conf").read_text()
        radio5_start = (STAGE / "usr/sbin/om-radio5-start").read_text()
        radio5_init = (STAGE / "etc/init.d/S55-radio5-ap").read_text()
        self.assertIn("wifi5g-toggle", control)
        self.assertIn("RADIO5G_ENABLE", toggle)
        self.assertIn("persisted=1", toggle)
        self.assertIn("RADIO5G_ENABLE", config_get)
        self.assertIn("RADIO5G_ENABLE=1", defaults)
        self.assertIn("gpio set wps 4 0", radio5_start)
        self.assertIn("OMRADIO5_WPS_GPIO_WARN reason=sysfs-absent", radio5_start)
        self.assertIn("OMRADIO5_AUTOSTART_DISABLED", radio5_init)

    def test_complete_front_panel_led_control_is_embedded(self) -> None:
        control = STAGE / "usr/sbin/om-ledctl"
        contract_path = STAGE / "usr/share/openmitrastar/leds/hgw500-leds.json"
        self.assertTrue(control.is_file())
        self.assertEqual(0o755, stat.S_IMODE(control.stat().st_mode))
        self.assertTrue(contract_path.is_file())
        contract = json.loads(contract_path.read_text(encoding="utf-8"))
        self.assertEqual(3, contract["physical_windows"])
        self.assertEqual({1, 7, 9, 10, 11}, {row["gpio"] for row in contract["channels"]})
        self.assertIn("--diagnostic identify", control.read_text(encoding="utf-8"))
        root_manifest = json.loads((ROOTFS_BUILD / "manifest.json").read_text())
        self.assertTrue(root_manifest["capabilities"]["front_panel_led_control"])
        self.assertEqual(
            5,
            root_manifest["contracts"]["front_panel_led_control"]["independent_channels"],
        )

    def test_ready_reconciles_only_proven_service_health(self) -> None:
        clear = STAGE / "usr/sbin/om-degraded-clear"
        self.assertEqual("f6c5fa02f538469b5d7841e766c46c46984d830bfd316f0a2006371913e75eeb", sha(clear))
        clear_text = clear.read_text()
        self.assertIn("S25-origin-import|S34-ipv6-local-policy|S35-radio-modules|S44-oem-web|S50-radio-ap", clear_text)
        self.assertIn("OMDEGRADED_CLEAR_REFUSED", clear_text)
        self.assertIn("boot_state=ready", clear_text)

        ready = STAGE / "etc/init.d/S90-ready"
        self.assertEqual("492ba7cd10e7c41f4c4b8c2645678c03fae2bfdd68d98dc67f6540f0a2a44d32", sha(ready))
        ready_text = ready.read_text()
        for marker in (
            "origin-mtd5-state", "radio2g/modules-ready", "hostapd.pid",
            "state=ENABLED", "mini_httpd.pid", "mini_httpd-getinfo.pid",
            "S25-origin-import", "S35-radio-modules", "S44-oem-web", "S50-radio-ap",
            "OMPRODUCT_READY state=$state schema=1",
        ):
            self.assertIn(marker, ready_text)

    def test_oem_ipv6_local_policy_is_embedded_after_network(self) -> None:
        helper = STAGE / "usr/sbin/om-ipv6-local-policy"
        init = STAGE / "etc/init.d/S34-ipv6-local-policy"
        self.assertTrue(helper.is_file())
        self.assertTrue(init.is_file())
        source = helper.read_text(encoding="utf-8")
        self.assertIn("mitrastar,hgw-500bna-qcv2", source)
        self.assertIn("all default eth0 br0", source)
        self.assertIn("bridge_l2_ipv6_untouched", source)
        self.assertIn('[ "$waited" -lt 5 ]', source)
        self.assertIn("wait_bounded=5", source)
        self.assertIn(
            "exec /usr/sbin/om-ipv6-local-policy",
            init.read_text(encoding="utf-8"),
        )
        self.assertLess("S32-network", "S34-ipv6-local-policy")
        self.assertLess("S34-ipv6-local-policy", "S35-radio-modules")

    def test_api_status_alias_preserves_cgi_auth_contract(self) -> None:
        alias = STAGE / "www/api/status"
        canonical = STAGE / "www/cgi-bin/status"
        self.assertTrue(alias.is_file())
        self.assertEqual(canonical.read_text(), alias.read_text())
        self.assertEqual(0o755, stat.S_IMODE(alias.stat().st_mode))
        self.assertIn("om-oem-cgi", alias.read_text())
        self.assertIn(" status", alias.read_text())
        http = (STAGE / "etc/minihttpd-oem.conf").read_text()
        https = (STAGE / "etc/minihttpd-https.conf").read_text()
        self.assertIn("cgipat=**.cgi|cgi-bin/*|api/status", http)
        self.assertIn("cgipat=**.cgi|cgi-bin/*|api/status", https)
        stamp = json.loads((STAGE / "usr/share/openmitrastar/cgi-overlay-v1.json").read_text())
        self.assertIn("api/status", stamp["routes"])
        self.assertEqual("**.cgi|cgi-bin/*|api/status", stamp["httpd_runtime"]["cgipat"])
        root_manifest = json.loads((ROOTFS_BUILD / "manifest.json").read_text())
        self.assertTrue(root_manifest["capabilities"]["api_status_alias"])
        contract = root_manifest["contracts"]["api_status_alias"]
        self.assertEqual("same-session-dispatcher", contract["auth"])
        self.assertEqual(sha(alias), contract["sha256"])

    def test_5g_autostart_and_bootenv_mac_are_fail_closed(self) -> None:
        radio = STAGE / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g"
        modules = sorted(radio.glob("*.ko"))
        self.assertEqual(22, len(modules))
        self.assertFalse((radio / "fwt_ctrl.ko").exists())
        self.assertEqual("0969752af8257a03a6951b82c5e1a269f4aeb99036e38cf6a781cf1a58cef97d", sha(radio / "board_compat.ko"))
        self.assertEqual("9c45dcf6300b1ac668b73c3fce92d8e6f25599604850a293bbac0f0e58992c87", sha(radio / "switch_emac.ko"))
        expected_switch_tqe = os.environ.get(
            "OM_Q3_EXPECTED_SWITCH_TQE_OVERRIDE_SHA256",
            "d41e530d65dae9ddbc5ff5893b9c44e07a829fba52759e466f71e26ba5d1047b",
        )
        self.assertEqual(expected_switch_tqe, sha(radio / "switch_tqe.ko"))
        expected_qdrv = os.environ.get(
            "OM_Q3_EXPECTED_QDRV_SHA256",
            "37527d16fa93325b676fde7247314fa0a9179095f3e6a7eb8dc19c63962b6f5f" if PROFILE == "open-lab-beacon-lifetime" else ("0d9bf9e92231e0db77b8c3320e09f7af40de691086618ab1d83464234f01f982" if PROFILE == "open-lab-beacon-preflight" else "b406f17333fe41114a2d8f307d9d6e71fad3b96be210cf55e8110b4afc141ca2"),
        )
        expected_wlan = os.environ.get(
            "OM_Q3_EXPECTED_WLAN_SHA256",
            "09c5e347f6c0fa9acad4a7e0e3571d5d976a2cf4a5f0e304730eb825badbc872" if PROFILE == "open-lab-beacon-lifetime" else ("f8449c18a08e46dfe9b9d581bb7eed060d3d260d5e9d36a5364913e3c5b561c8" if PROFILE == "open-lab-beacon-preflight" else "d286d8f5792193ad4c4c63e4d4a23e7e540e56184aafb765b393fd4ae01ed48b"),
        )
        self.assertEqual(expected_qdrv, sha(radio / "qdrv.ko"))
        self.assertEqual(expected_wlan, sha(radio / "wlan.ko"))
        service = STAGE / "etc/init.d/S55-radio5-ap"
        self.assertTrue(service.is_file())
        expected_s55 = os.environ.get(
            "OM_Q3_EXPECTED_RADIO5_S55_SHA256",
            "06c0efbbb951a84f4990fd9fd99dbbedfd99f19695edea7bc94385e80bc4daa2",
        )
        self.assertEqual(expected_s55, sha(service))
        self.assertIn("hardware-gate-closed", service.read_text())
        self.assertIn("mac-producer-not-ready", service.read_text())
        calibration_init = STAGE / "etc/init.d/S53-qtn-calibration"
        calibration_producer = STAGE / "usr/sbin/om-qtn-cal-readonly"
        expected_s53 = (
            "056dcc1034429419e32f16bb052340f69dde22859abd836c20386a5a2fb41b11"
            if AUTOSTART else
            "23f9a6e661fcc67d8b62444b06164bb27d30167bdfbb0d679dc0f168d87bd404"
        )
        self.assertEqual(expected_s53, sha(calibration_init))
        expected_cal_producer = os.environ.get(
            "OM_Q3_EXPECTED_QTN_CAL_PRODUCER_SHA256",
            "3e3f3d19c65a17df52e25b5dee783a1a781eef79a926cb49e472ee8179e30eb2",
        )
        self.assertEqual(expected_cal_producer, sha(calibration_producer))
        self.assertIn("OMQTNCAL_READY", calibration_producer.read_text())
        feature = STAGE / "etc/openmitrastar/features/q3-radio5-autostart"
        if AUTOSTART:
            self.assertTrue(feature.is_file())
            self.assertEqual("Q3_RADIO5_AUTOSTART=1", feature.read_text().strip())
            self.assertEqual(0o644, stat.S_IMODE(feature.stat().st_mode))
        else:
            self.assertFalse(feature.exists())
        self.assertTrue((STAGE / "usr/share/openmitrastar/radio5g/q3-radio5-autostart.feature").is_file())
        if PROFILE.startswith("open-lab"):
            open_feature = STAGE / "etc/openmitrastar/features/q3-radio5-open-lab"
            self.assertTrue(open_feature.is_file())
            self.assertEqual("Q3_RADIO5_OPEN_LAB=1", open_feature.read_text().strip())
            self.assertEqual(0o644, stat.S_IMODE(open_feature.stat().st_mode))
            self.assertEqual([], list(STAGE.rglob("*.psk")))
            if PROFILE == "open-lab-tqe512":
                tqe_feature = STAGE / "etc/openmitrastar/features/q3-radio5-tqe512-discriminator"
                self.assertTrue(tqe_feature.is_file())
                self.assertEqual("Q3_RADIO5_TQE_RING_ENTRIES=512", tqe_feature.read_text().strip())
                self.assertEqual(0o644, stat.S_IMODE(tqe_feature.stat().st_mode))
            if PROFILE == "open-lab-beacon-preflight":
                beacon_feature = STAGE / "etc/openmitrastar/features/q3-radio5-beacon-preflight"
                self.assertTrue(beacon_feature.is_file())
                self.assertEqual("Q3_RADIO5_BEACON_PREFLIGHT=1", beacon_feature.read_text().strip())
                self.assertEqual(0o644, stat.S_IMODE(beacon_feature.stat().st_mode))
            if PROFILE == "open-lab-beacon-lifetime":
                lifetime_feature = STAGE / "etc/openmitrastar/features/q3-radio5-beacon-lifetime"
                self.assertTrue(lifetime_feature.is_file())
                self.assertEqual("Q3_RADIO5_BEACON_LIFETIME=1", lifetime_feature.read_text().strip())
                self.assertEqual(0o644, stat.S_IMODE(lifetime_feature.stat().st_mode))

        bootenv = STAGE / "usr/sbin/om-bootenv-readonly"
        consumer = STAGE / "usr/sbin/om-qtn-mac-prepare"
        s54 = STAGE / "etc/init.d/S54-qtn-mac"
        self.assertEqual("7ae702dafca99b95fa95a0098a2662622278e10788869d70e00f61b5738fdb96", sha(bootenv))
        self.assertEqual("26d39272d932a77f1c58a38f0a0065e3e56022bdfaea28d9dfb8633d5531ddd2", sha(consumer))
        expected_s54 = (
            "c2559268692b5568288f4df3b4b3e8febe550a45825e7d80f6bd7506b2a3ef70"
            if AUTOSTART else
            "cd3cd913ec763e1a0ce58f9b40d990931deac82118226ead57b0fe8a9588715d"
        )
        self.assertEqual(expected_s54, sha(s54))
        if not AUTOSTART:
            s53_text = calibration_init.read_text()
            s54_text = s54.read_text()
            self.assertNotIn("q3-radio5-autostart", s53_text)
            self.assertNotIn("q3-radio5-autostart", s54_text)
            self.assertIn("OMQTNCAL_PREP_START", s53_text)
            self.assertIn("exec /usr/sbin/om-qtn-cal-readonly", s53_text)
            self.assertIn("OMQTN_MAC_PREP_START", s54_text)
            self.assertIn("exec /usr/sbin/om-qtn-mac-prepare", s54_text)
        consumer_text = consumer.read_text()
        self.assertIn('"$bootenv_producer" || refuse bootenv-producer-failed', consumer_text)
        self.assertIn("source=mtd1+mtd2-redundant-readonly", consumer_text)
        self.assertIn("primary_crc=valid", consumer_text)
        self.assertIn("backup_crc=valid", consumer_text)
        self.assertIn("copies=match", consumer_text)
        self.assertNotIn("/sys/class/net/eth0/address", consumer_text)
        self.assertNotIn("+ 1", consumer_text)
        self.assertEqual([], re.findall(r"\b(?:[0-9a-fA-F]{2}:){5}[0-9a-fA-F]{2}\b", consumer_text))
        producer_text = subprocess.check_output(["strings", str(bootenv)], text=True)
        for forbidden in ("flash_erase", "nandwrite", "mtd_debug", "dd of=", "remount,rw"):
            self.assertNotIn(forbidden, producer_text)
        for forbidden in ("/bin/sh", "/bin/ash", "hexdump"):
            self.assertNotIn(forbidden, producer_text)
        elf_header = subprocess.check_output(["readelf", "-h", str(bootenv)], text=True)
        self.assertIn("Class:                             ELF32", elf_header)
        self.assertIn("Machine:                           ARCompact", elf_header)
        elf_program_headers = subprocess.check_output(["readelf", "-l", str(bootenv)], text=True)
        self.assertNotIn("INTERP", elf_program_headers)
        self.assertNotIn("DYNAMIC", elf_program_headers)
        producer_manifest = json.loads((STAGE / "usr/share/openmitrastar/bootenv-wifiaddr-producer.json").read_text())
        self.assertEqual("openmitrastar.bootenv-wifiaddr-producer/v1", producer_manifest["schema"])
        self.assertEqual("7ae702dafca99b95fa95a0098a2662622278e10788869d70e00f61b5738fdb96", producer_manifest["binary_sha256"])
        self.assertEqual("arc700-syscall-only-no-libc-no-tls-no-atomics", producer_manifest["runtime"])
        self.assertTrue(producer_manifest["read_only"])
        self.assertFalse(producer_manifest["writes_flash"])

        start = STAGE / "usr/sbin/om-radio5-start"
        expected_start = os.environ.get("OM_Q3_EXPECTED_RADIO5_START_SHA256", "2fc6ca62a469578e76741a15fe8ee6e8073d3da5ea7c24c135a484462e212aca")
        self.assertEqual(expected_start, sha(start))
        start_text = start.read_text()
        self.assertIn("sed 's/\\r$//'", start_text)
        for forbidden in (
            "qcsapi_runtime=",
            "qcsapi_gate",
            "qc_set ",
            "qc_get ",
            "call_qcsapi",
            "OMRADIO5_QCSAPI_READBACK_PASS",
        ):
            self.assertNotIn(forbidden, start_text)
        self.assertIn("OMRADIO5_NATIVE_BYPASS_PASS", start_text)
        self.assertIn("OMRADIO5_NATIVE_READBACK_PASS", start_text)
        self.assertIn("native-channel-readback", start_text)
        self.assertIn("native-ssid-readback", start_text)
        manifest = STAGE / "usr/share/openmitrastar/radio5g/artifacts.sha256"
        self.assertNotIn(b"\r", manifest.read_bytes())
        runtime_env = STAGE / "usr/share/openmitrastar/radio5g/runtime.env"
        self.assertNotIn(b"\r", runtime_env.read_bytes())
        runtime_text = runtime_env.read_text()
        if PROFILE == "open-lab-beacon-lifetime":
            self.assertIn(f"Q3_QDRV_SHA256={expected_qdrv}", runtime_text)
            self.assertIn("Q3_WLAN_SHA256=09c5e347f6c0fa9acad4a7e0e3571d5d976a2cf4a5f0e304730eb825badbc872", runtime_text)
            self.assertIn(f"expected_qdrv_sha={expected_qdrv}", start_text)
            self.assertIn("expected_wlan_sha=09c5e347f6c0fa9acad4a7e0e3571d5d976a2cf4a5f0e304730eb825badbc872", start_text)
            self.assertNotIn("expected_qdrv_sha=e01465aa2f017fbb8bf6c7a87837babaea8b21e3ef6284f06ca3b3d9664cdd12", start_text)
            self.assertIn("[ \"$(value Q3_BOARD_COMPAT_SHA256 \"$share/runtime.env\")\" = 0969752af8257a03a6951b82c5e1a269f4aeb99036e38cf6a781cf1a58cef97d ]", start_text)
            self.assertIn("[ \"$(value Q3_SWITCH_EMAC_SHA256 \"$share/runtime.env\")\" = 9c45dcf6300b1ac668b73c3fce92d8e6f25599604850a293bbac0f0e58992c87 ]", start_text)
            self.assertIn("[ \"$(value Q3_HBM_SHA256 \"$share/runtime.env\")\" = c5084d18167b20f250718c2e97ad94bf36f059543eb37d7372513352b3aa357b ]", start_text)
        self.assertIn("last-refusal", start_text)

        loader = STAGE / "usr/sbin/ram-insmod-qtn"
        self.assertEqual("8eb902dcc5e1bdab1aba356aafca04102ab394352c1685434ac9a9a09c5baba6", sha(loader))
        loader_text = subprocess.check_output(["strings", str(loader)], text=True)
        self.assertIn('"$loader" "$module" "$*"', start_text)
        self.assertIn("RAM_INSMOD_OK", loader_text)
        self.assertIn("RAM_INSMOD_LOAD_FAIL", loader_text)
        self.assertIn("hbm_lifecycle_enable", start_text)
        self.assertIn("switch_tqe_only_enable", start_text)
        self.assertIn("w3_symbols_only", start_text)
        self.assertIn('w3_rx_ring_entries="$tqe_ring_entries"', start_text)
        self.assertIn('parameters/w3_rx_ring_entries)" = "$tqe_ring_entries"', start_text)
        if TQE_RING_ENTRIES == 512:
            self.assertIn("Q3_RADIO5_TQE_RING_ENTRIES=512", start_text)
            self.assertIn("tqe_ring_entries=512", start_text)
        self.assertIn("allow_dram_sram_fallback=1", start_text)
        self.assertIn('parameters/allow_dram_sram_fallback)" = Y', start_text)
        self.assertIn("OMSRAM stage=gate-pass backend=dram-lab target=mitrastar,hgw-500bna-qcv2", start_text)
        self.assertNotIn("hostapd-qtn -B", start_text)
        self.assertNotIn("hostapd-qtn -dd -P", start_text)
        self.assertNotIn("pid_file=", start_text)
        self.assertNotIn("hostapd.shell.pid", start_text)
        self.assertIn('hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &', start_text)
        self.assertIn('printf \'%s\\n\' "$hostapd_shell_pid" >"$state/hostapd.pid"', start_text)
        self.assertIn('chmod 0600 "$state/hostapd.pid"', start_text)
        self.assertIn('[ "$hostapd_pid" = "$hostapd_shell_pid" ]', start_text)
        self.assertIn("ctrl_interface=/var/run/hostapd", start_text)
        self.assertIn("hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping", start_text)
        self.assertIn("grep -qx PONG", start_text)
        self.assertIn("led_dir=/sys/class/leds/openmitrastar:green:wlan5g", start_text)
        self.assertIn('while [ "$led_attempt" -lt 10 ]', start_text)
        self.assertIn("hostapd-died-waiting-led", start_text)
        self.assertIn("wifi0-carrier-lost-waiting-led", start_text)
        self.assertIn("rf-lost-waiting-led", start_text)
        self.assertIn('if [ "$led_brightness" = "$led_max" ]', start_text)
        self.assertIn("wifi0-carrier-evidence-lost-after-led", start_text)
        self.assertIn("led_gate=dmesg-carrier-marker", start_text)
        self.assertIn("wifi0-not-running-after-led", start_text)
        self.assertIn("rf-lost-after-led", start_text)
        self.assertIn("OMQDRVLED stage=ap-state carrier=on", start_text)
        if PROFILE.startswith("open-lab"):
            self.assertIn("Q3_RADIO5_OPEN_LAB=1", start_text)
            self.assertIn("MOVISTAR_PLUS_55CB", start_text)
            self.assertIn("OpenMitraStar-5G-DIAG", start_text)
            self.assertIn("security_profile=open-lab", start_text)
            self.assertIn("'wpa=0'", start_text)
            self.assertIn("open-lab-wpa0-missing", start_text)
            self.assertIn("open-lab-wpa-config-present", start_text)
            self.assertIn("! grep -Eqi '^key_mgmt=.*WPA'", start_text)
            self.assertIn("! grep -Eqi 'CCMP'", start_text)
            self.assertIn("! grep -Eq '^wpa=[1-9]'", start_text)
            self.assertIn("OPEN-LAB-NO-FLASH", start_text)
            self.assertEqual(1, start_text.count('/usr/sbin/hostapd-qtn -dd -f "$state/hostapd.log" "$conf" &'))
            if PROFILE == "open-lab-beacon-preflight":
                self.assertIn("openmitrastar_beacon_preflight_enable=1", start_text)
                self.assertIn("beacon-preflight-readback", start_text)
                self.assertIn("OMQDRVBC stage=preflight-fail", start_text)
                self.assertIn("OMQDRVBC stage=preflight-pass", start_text)
                for field in ("count=", "total=", "used=", "beacon_len=", "head_dma=", "args_dma="):
                    self.assertIn(field, start_text)
            if PROFILE == "open-lab-beacon-lifetime":
                self.assertIn("Q3_RADIO5_BEACON_LIFETIME=1", start_text)
                self.assertIn("beacon-lifetime-runtime-failed", start_text)
                self.assertIn("OMQDRVBC stage=preflight-pass", start_text)
                self.assertIn("OMQDRVBC stage=quarantined", start_text)
                self.assertIn("OMQDRVHLINK stage=quarantine", start_text)
                self.assertIn('while [ "$beacon_lifetime_wait" -lt 15 ]', start_text)
                self.assertIn("hostapd-died-waiting-beacon-lifetime", start_text)
                self.assertIn("hostapd-pong-lost-waiting-beacon-lifetime", start_text)
                self.assertIn("rf-lost-waiting-beacon-lifetime", start_text)
                self.assertIn("beacon-lifetime-fatal-during-wait", start_text)
                self.assertIn("OMQDRVBC stage=ioctl-send", start_text)
                self.assertIn("beacon-lifetime-markers-timeout", start_text)

        stop = STAGE / "usr/sbin/om-radio5-stop"
        expected_stop = "4c749599172491d85d09f8f4668b1dff5a0d8308d4485f7f325e2372cdf5b1c5" if PROFILE in ("open-lab-beacon-preflight", "open-lab-beacon-lifetime") else "481b35f34f32f61739f12f018b50fec1812c835d1cacfb0b948e9e7b352b0132"
        self.assertEqual(expected_stop, sha(stop))
        stop_text = stop.read_text()
        self.assertIn('"$state/hostapd.pid"', stop_text)
        self.assertNotIn("hostapd.shell.pid", stop_text)
        self.assertIn("/var/run/hostapd/wifi0", stop_text)

        executable = (
            "etc/init.d/S55-radio5-ap", "usr/sbin/om-radio5-start",
            "usr/sbin/om-radio5-stop", "usr/sbin/hostapd-qtn",
            "usr/sbin/hostapd-cli-qtn", "usr/sbin/iwconfig-qtn",
            "usr/sbin/iwpriv-qtn", "usr/sbin/ram-insmod-qtn",
            "usr/sbin/om-bootenv-readonly", "usr/sbin/om-qtn-mac-prepare",
            "etc/init.d/S54-qtn-mac",
        )
        for rel in executable:
            self.assertEqual(0o755, stat.S_IMODE((STAGE / rel).stat().st_mode), rel)
        for module in modules:
            self.assertEqual(0o644, stat.S_IMODE(module.stat().st_mode), str(module))
        for rel in (
            "usr/share/openmitrastar/radio5g/artifacts.sha256",
            "usr/share/openmitrastar/radio5g/modules.order",
            "usr/share/openmitrastar/radio5g/runtime-contract.json",
            "usr/share/openmitrastar/radio5g/runtime.env",
            "etc/qtn_regulatory_db.bin", "etc/power_tables/power_table.conf",
            "etc/power_tables/tx_power_QSR1000_es.txt",
        ):
            self.assertEqual(0o644, stat.S_IMODE((STAGE / rel).stat().st_mode), rel)

    def test_w3_direct_emac_contract(self) -> None:
        contract = json.loads((STAGE / "usr/share/openmitrastar/q3-w3-direct-emac.json").read_text())
        self.assertEqual("preserved", contract["direct_emac"])
        self.assertEqual("w3_symbols_only=1", contract["switch_emac_mode"])
        self.assertEqual(AUTOSTART, contract["autostart"])
        if not AUTOSTART:
            self.assertEqual("Q3-MAINTENANCE-MANUAL-5G-RAM-ONLY-NO-FLASH", contract["classification"])
        self.assertEqual("excluded-from-safe-ladder", contract["fwt_ctrl_runtime"])
        self.assertEqual(22, len(contract["modules"]))
        preparation = contract["maintenance_preparation"]
        self.assertEqual(not AUTOSTART, preparation["boot_calibration_read_only"])
        self.assertEqual(not AUTOSTART, preparation["boot_mac_read_only"])
        self.assertFalse(preparation["hidden_manual_prerequisites"])
        switch = (STAGE / "usr/libexec/openmitrastar/w3-no-ioss/switch-emac-handoff").read_text()
        self.assertIn("w3_symbols_only=1", switch)
        self.assertIn("reason=q3_ioss_reset_forbidden", switch)
        self.assertIn("W3_TQE_RING_ENTRIES", switch)
        self.assertIn("w3_rx_ring_entries=$tqe_ring_entries", switch)

    def test_kernel_contract_and_origin_dtb(self) -> None:
        config = (BUILD / f"{BASE}.config").read_text()
        for symbol in (
            "CONFIG_CRYPTO_JITTERENTROPY=y", "CONFIG_CRYPTO_USER_API_RNG=y",
            "CONFIG_MTD_ROM=y", "CONFIG_MTD_PHYSMAP_OF=y", "CONFIG_MTD_BLOCK_RO=y",
            "CONFIG_JFFS2_FS=y",
        ):
            self.assertIn(symbol, config)
        self.assertIn("# CONFIG_MTD_BLOCK is not set", config)
        built_dtb = BUILD / f"{BASE}.dtb"
        self.assertEqual(EXPECTED_CONTROLS_DTB, sha(built_dtb))
        dtb_strings = subprocess.check_output(["strings", str(built_dtb)], text=True)
        for marker in (
            "mtd-rom", "uboot_env", "uboot_env_bak", "data",
            "no-unaligned-direct-access", "qtn,irq-poll-fallback",
            "mitrastar,wlan2g-led-active-low", "mitrastar,wifi-release-ms",
        ):
            self.assertIn(marker, dtb_strings)
        dts = BOOTENV_DTS.read_text()
        self.assertEqual(3, dts.count('compatible = "mtd-rom";'))
        for marker in ("flash@90020000", "flash@90030000", "flash@90f80000"):
            self.assertIn(marker, dts)
        bootenv_manifest = json.loads(BOOTENV_MANIFEST.read_text())
        self.assertTrue(bootenv_manifest["read_only"])
        self.assertTrue(bootenv_manifest["copies_must_match"])
        self.assertFalse(bootenv_manifest["writes_flash"])

    def test_packaging_slot_and_reproducibility(self) -> None:
        root_manifest = json.loads((ROOTFS_BUILD / "manifest.json").read_text())
        manifest = json.loads((BUILD / "manifest.json").read_text())
        contract = json.loads((BUILD / "bootbase-contract.json").read_text())
        self.assertEqual(sha(ROOTFS_BUILD / root_manifest["rootfs"]["file"]), root_manifest["rootfs"]["sha256"])
        self.assertTrue(contract["accepted_by_contract"])
        self.assertTrue(manifest["slot"]["fits"])
        self.assertGreater(manifest["slot"]["spare_bytes"], 0)
        self.assertTrue(manifest["reproducibility"]["rootfs_two_builds_identical"])
        self.assertTrue(manifest["reproducibility"]["kernel_two_incremental_trees_identical"])
        self.assertEqual(AUTOSTART, root_manifest["capabilities"]["w3_5g_autostart"])
        self.assertEqual(not AUTOSTART, root_manifest["capabilities"]["w3_5g_manual_start"])
        if not AUTOSTART:
            self.assertEqual("Q3-MAINTENANCE-MANUAL-5G-RAM-ONLY-NO-FLASH", manifest["classification"])
            self.assertEqual("Q3_MAINTENANCE_MANUAL_5G", manifest["profile"])
        self.assertEqual(sha(TFTP), manifest["artifacts"]["webformat"]["sha256"])
        self.assertEqual(TFTP.read_bytes(), (BUILD / f"{BASE}.webformat.bin").read_bytes())
        if PROFILE.startswith("open-lab") and AUTOSTART:
            expected_class = "OPEN-LAB-TQE512-DISCRIMINATOR-RAM-ONLY-NO-FLASH" if PROFILE == "open-lab-tqe512" else ("OPEN-LAB-BEACON-PREFLIGHT-RAM-ONLY-NO-FLASH" if PROFILE == "open-lab-beacon-preflight" else ("OPEN-LAB-BEACON-LIFETIME-RAM-ONLY-NO-FLASH" if PROFILE == "open-lab-beacon-lifetime" else "OPEN-LAB-RAM-ONLY-NO-FLASH"))
            expected_profile = "Q3_OPEN_LAB_TQE512" if PROFILE == "open-lab-tqe512" else ("Q3_OPEN_LAB_BEACON_PREFLIGHT" if PROFILE == "open-lab-beacon-preflight" else ("Q3_OPEN_LAB_BEACON_LIFETIME" if PROFILE == "open-lab-beacon-lifetime" else "Q3_OPEN_LAB"))
            self.assertEqual(expected_class, manifest["classification"])
            self.assertEqual(expected_profile, manifest["profile"])
            self.assertEqual("OPEN", manifest["security"]["radio5_security"])
            self.assertFalse(manifest["security"]["radio5_psk_required"])

    def test_runtime_gates_are_honest(self) -> None:
        manifest = json.loads((BUILD / "manifest.json").read_text())
        gates = manifest["runtime_gates"]
        self.assertEqual("pending", gates["cold_boot_autonomous_entropy"])
        self.assertEqual("pending", gates["origin_mtd5_read_only_import"])
        self.assertEqual("pending", gates["bootenv_redundant_read_only_import"])
        self.assertEqual("pending", gates["quantenna_auto_mac"])
        self.assertEqual("pending", gates["realtek_2g_autostart"])
        self.assertEqual(
            "pending-exact-image-hardware-validation" if AUTOSTART else "disabled-by-build",
            gates["quantenna_5g_autostart"],
        )
        self.assertEqual(
            "not-applicable" if AUTOSTART else "pending-exact-image-hardware-validation",
            gates["quantenna_5g_manual_start"],
        )
        self.assertIn("forbidden", gates["flash"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
