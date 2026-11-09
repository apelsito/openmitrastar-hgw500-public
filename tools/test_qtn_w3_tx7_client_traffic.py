#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_qtn_w3_tx7_client_traffic.py"
MONITOR = ROOT / "tools/q3_client_stream_single_session.py"
spec = importlib.util.spec_from_file_location("run_qtn_w3_tx7_client_traffic", RUNNER)
module = importlib.util.module_from_spec(spec)
assert spec.loader
spec.loader.exec_module(module)


class Tx7QuantennaClientGateTests(unittest.TestCase):
    def test_pinned_tx7_and_fixed_quantenna_inputs(self) -> None:
        manifest = module.verify_local()
        module.verify_safe_modules()
        self.assertEqual(module.IMAGE_SHA256, manifest["artifacts"]["tftp_copy"]["sha256"])
        self.assertFalse(manifest["security"]["radio5g_autostart"])
        self.assertEqual(
            "368c347eac8fdf895cc4ec37c394a0a97b4c0297f892a506bf5986a21e532c74",
            module.SWITCH_TQE_SHA256,
        )

    def test_runner_is_ram_only_and_preserves_management_and_2g(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        for required in (
            "/sys/class/net/br0/brif/eth0",
            "/sys/class/net/br0/brif/wlan0",
            "/sys/class/net/br0/brif/wifi0",
            '"{SAFE_OVERLAY}/bin/om-radio5-start"',
            'stop_radio5(args.host, "tx7-client-gate-failed")',
            "--require-client-traffic",
            "target_local_rollback",
            "hostapd-open.pid",
            "SAFE_OVERLAY",
            "OM_RADIO5_MODULE_DIR",
            "OM_RADIO5_SHARE",
            "stage_safe_overlay",
            "cleanup_safe_overlay",
            "collect_radio5_failure_snapshot",
            "OMW3TX7_FAILURE_SNAPSHOT_LOCAL",
        ):
            self.assertIn(required, source)
        for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "reboot_boot_ramssh"):
            self.assertNotIn(forbidden, source)

    def test_open_assoc_trace_profile_is_explicit_and_ephemeral(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("Q3_RADIO5_OPEN_LAB=1", source)
        self.assertIn("Q3_RADIO5_BEACON_LIFETIME=1", source)
        self.assertIn("/run/openmitrastar/w3-tx7-client-gate", source)
        self.assertIn("OpenMitraStar-5G-DIAG", source)
        self.assertIn("OMW3SAFE stage=active", source)
        for expected in (
            module.QDRV_SHA256,
            module.WLAN_SHA256,
            module.HBM_SHA256,
            module.SWITCH_TQE_SHA256,
            module.BASE_QDRV_SHA256,
            module.SAFE_QDRV_SHA256,
            module.QDRV_PROFILE_SHA256,
            module.BASE_WLAN_SHA256,
            module.BASE_HBM_SHA256,
            module.BASE_SWITCH_TQE_SHA256,
            module.F38_QDRV_SHA256,
            module.F38_WLAN_SHA256,
            module.F38_HBM_SHA256,
            module.F38_SWITCH_TQE_SHA256,
        ):
            self.assertIn(expected, source)

    def test_qdrv_preflight_accepts_historical_safe_and_trace_identities(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertEqual(
            "a4a4e277bf815e8b408594d67a1d1afcec03251af5bc4d05b51567abbb41ef33",
            module.SAFE_QDRV_SHA256,
        )
        self.assertIn(
            "check_any4 {module_dir}/qdrv.ko "
            "{BASE_QDRV_SHA256} {SAFE_QDRV_SHA256} {QDRV_SHA256} {F38_QDRV_SHA256}",
            source,
        )
        self.assertIn('check "$root/upload/qdrv.ko" {QDRV_SHA256}', source)
        self.assertIn(
            "awk -F= -v q={QDRV_PROFILE_SHA256}",
            source,
        )
        self.assertIn(
            "grep -qx 'Q3_QDRV_SHA256={QDRV_PROFILE_SHA256}'",
            source,
        )

    def test_safe_module_overlay_is_hash_pinned_and_contract_rebased(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        for marker in (
            "quantenna-linux510-radiohw-calibration-20260821/rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko",
            "quantenna-linux510-radiohw-calibration-rtnl-20260821/rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/wlan/wlan.ko",
            "qtn-hbm-clear-probe-20260821/hbm.ko",
            "qtn-switch-tqe-dma-device-fix-20260821/switch_tqe.ko",
            "quantenna-5g-isolated-l3-runtime-20260823/om-radio5-start-isolated-l3",
            "quantenna-5g-isolated-l3-runtime-20260823/om-radio5-stop-isolated-l3",
            "q3-calibration-overlay/inspect-20260821-1645/usr/sbin/ram-insmod-qtn",
            "tools/ramssh_upload.py",
            'Q3_QDRV_SHA256',
            'Q3_WLAN_SHA256',
            'Q3_HBM_SHA256',
            'Q3_SWITCH_TQE_SHA256',
            'artifacts.sha256.new',
            'OM_RADIO5_MODULE_DIR',
            'OM_RADIO5_SHARE',
            'OM_RADIO5_STOP',
            'OM_RADIO5_LOADER',
            'Q3_RADIO5_TQE_RING_ENTRIES=512',
            'OM_RADIO5_TQE512_FEATURE',
            '/sys/module/switch_tqe/parameters/w3_rx_ring_entries)" = 512',
            'safe_overlay=1 tqe_ring=512 isolated_l3=192.168.77.1/24',
        ):
            self.assertIn(marker, source)
        isolated_start = module.SAFE_START[0].read_text(encoding="utf-8")
        self.assertIn('case "$tqe_ring_entries" in 256|512)', isolated_start)
        self.assertNotIn("brctl addif br0 wifi0", isolated_start)

    def test_safe_overlay_rollback_preserves_radio2g(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        self.assertIn("rm -rf {SAFE_OVERLAY}", source)
        self.assertIn("cleanup_safe_overlay(args.host)", source)
        self.assertIn("hostapd-open.pid", source)
        self.assertIn("isolated_l3=1 br0_wifi0=0", source)
        self.assertIn('"--isolated-l3"', source)
        changed = source[source.index("def stage_safe_overlay"):source.index("def cleanup_safe_overlay")]
        for forbidden in ("rmmod rtl", "hostapd-open.pid\" )", "om-radio-start", "wlan0 down"):
            self.assertNotIn(forbidden, changed)

    def test_rollback_is_armed_before_qdrv_start(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        main = source[source.index("def main()") :]
        self.assertLess(
            main.index("prepare_radio5_gate(args.host, args.run_id)"),
            main.index("arm_rollback(args.host, 240, args.run_id)"),
        )
        self.assertLess(
            main.index("arm_rollback(args.host, 240, args.run_id)"),
            main.index("start_radio5(args.host, args.run_id)"),
        )
        self.assertIn("OMQTN5G_RUN stage=qdrv-load-begin", source)
        self.assertIn("OMRADIO5_ROLLBACK_COMPLETE", source)
        self.assertIn("OMW3TX7_FAILURE_SNAPSHOT_BEGIN", source)
        self.assertIn("/dev/kmsg", source)
        self.assertIn("console_loglevel", source)
        self.assertIn('echo 6 >/proc/sys/kernel/printk', source)
        self.assertIn('console-loglevel.original', source)
        self.assertIn('if [ "$active_console_loglevel" -lt 6 ]', source)

    def test_commit_validates_and_restores_before_cancelling_rollback(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        commit = source[source.index("def commit(") : source.index("def main()")]
        bridge_check = commit.index("test -e /sys/class/net/br0/brif/eth0")
        restore = commit.index('echo "$original" >/proc/sys/kernel/printk')
        verify_restore = commit.index('[ "$restored" = "$original" ]')
        commit_file = commit.index('touch "$gate/commit"')
        kill_rollback = commit.index('kill "$(cat "$gate/rollback.pid")"')
        marker = commit.index("OMQTN5G_RUN stage=commit")
        self.assertLess(bridge_check, restore)
        self.assertLess(restore, verify_restore)
        self.assertLess(verify_restore, commit_file)
        self.assertLess(commit_file, kill_rollback)
        self.assertLess(kill_rollback, marker)

    def test_failure_snapshot_is_collected_before_stop_and_cleanup(self) -> None:
        source = RUNNER.read_text(encoding="utf-8")
        main = source[source.index("def main()") :]
        self.assertLess(
            main.index("collect_radio5_failure_snapshot(args.host, failure_log, args.run_id)"),
            main.index('stop_radio5(args.host, "tx7-client-gate-failed")'),
        )
        self.assertLess(
            main.index('stop_radio5(args.host, "tx7-client-gate-failed")'),
            main.index("cleanup_safe_overlay(args.host)"),
        )
        self.assertIn("/run/openmitrastar/radio5g-failures/latest", source)
        self.assertIn("SECTION_DMESG_QTN", source)

    def test_monitor_uses_one_session_and_real_health_fields(self) -> None:
        source = MONITOR.read_text(encoding="utf-8")
        runner = RUNNER.read_text(encoding="utf-8")
        self.assertIn("paramiko.SSHClient()", source)
        self.assertIn("AP-STA-DISCONNECTED", source)
        self.assertIn("br_eth=", source)
        self.assertIn("br_2g=", source)
        self.assertIn("br_5g=", source)
        self.assertIn("radio2g=", source)
        self.assertIn("fatal=$(dmesg", source)
        self.assertIn("Misaligned Access", source)
        self.assertIn("Oops", source)
        self.assertNotIn("fatal=0\n", source[source.index("def remote_command"):source.index("def parse_line")])
        self.assertIn("OMW3TX7_MODULE_MAP_BEGIN", runner)
        self.assertIn("Misaligned Access", runner)
        self.assertIn("fwt_if", runner)
        self.assertIn("rtl8192ee rtl_pci rtlwifi", runner)
        self.assertNotIn("fwt_ctrl", runner)
        self.assertIn("/sys/module/$module/sections/.text", runner)
        self.assertIn(".module-map.txt", runner)

    def test_dry_run(self) -> None:
        result = subprocess.run(
            [sys.executable, str(RUNNER)], cwd=ROOT, text=True,
            capture_output=True, timeout=15, check=False,
        )
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn("W3_TX7_5G_CLIENT_TRAFFIC_DRY_RUN_PASS=1", result.stdout)
        self.assertIn('"flash": false', result.stdout)
        self.assertIn('"reboot": false', result.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
