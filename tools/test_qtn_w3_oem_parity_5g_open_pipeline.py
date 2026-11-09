#!/usr/bin/env python3
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
PIPELINE = ROOT / "tools/run_qtn_w3_final_5g_open_pipeline.py"
HANDOFF = ROOT / "tools/run_qtn_w3_switch_emac_handoff.py"
HANDOFF_REMOTE = ROOT / "tools/qtn_w3_switch_emac_handoff_remote.sh"
AP = ROOT / "tools/qtn_w3_native_madwifi_open_ap.sh"
SOAK = ROOT / "tools/run_qtn_w3_native_open_soak.py"
HBM_GATE = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_RXALIGN_GATE.approved.env"
QDRV_GATE = ROOT / "work/mission-state/w3-offline/W3_QDRV_HOSTLINK_CORE_RXALIGN_GATE.approved.env"


class OemParity5gOpenPipelineTests(unittest.TestCase):
    def test_pins_watchdog_safe_hbm_and_actual_qdrv(self):
        text = PIPELINE.read_text(encoding="utf-8")
        self.assertIn("c5084d18167b20f250718c2e97ad94bf36f059543eb37d7372513352b3aa357b", text)
        self.assertIn("9ba6cd3ff63e23fb03fc8e8d5cd6e93f9d710e0d56a0693852f4227cf9dabb20", text)
        self.assertIn("HBM: HBM_SHA256", text)
        self.assertIn("QDRV: QDRV_SHA256", text)
        expected_manifest = "6f5b86911e45a08934049305589bdfb0cff488012936f162b9c826f4adddfca7"
        self.assertIn(f"W3_MODULE_MANIFEST_SHA256={expected_manifest}", HBM_GATE.read_text())
        self.assertIn(f"W3_MODULE_MANIFEST_SHA256={expected_manifest}", QDRV_GATE.read_text())

    def test_oem_management_and_2g_preservation_contract(self):
        pipeline = PIPELINE.read_text(encoding="utf-8")
        handoff = HANDOFF.read_text(encoding="utf-8")
        remote = HANDOFF_REMOTE.read_text(encoding="utf-8")
        self.assertIn('parser.add_argument("--management-host", default="192.168.1.90")', pipeline)
        self.assertIn('"--preserve-2g"', pipeline)
        self.assertIn("run_product_rootfs_secure_ap.ps1", pipeline)
        self.assertIn("OPENMITRASTAR_PRODUCT_SECURE_AP_RAM_ONLY", pipeline)
        self.assertIn("--use-current-no-watchdog-boot", pipeline)
        self.assertIn("--no-hw-watchdog", pipeline)
        self.assertIn("--skip-ioss-reset-pulse", pipeline)
        self.assertIn("--no-uart-reboot-on-failure", pipeline)
        self.assertIn('parser.add_argument("--management-host")', handoff)
        self.assertIn("W3_MANAGEMENT_IPV4=192.168.1.200", handoff)
        self.assertIn('printf \'%s\\n\' "$had_wlan0" >"$state/had-wlan0"', remote)
        self.assertIn("reason=wlan0_not_preserved", remote)
        self.assertIn("brctl addif br0 eth1_emac1", remote)
        self.assertIn('>"$direct_driver/bind"', remote)

    def test_timer_reclaim_is_explicitly_disabled(self):
        remote = HANDOFF_REMOTE.read_text(encoding="utf-8")
        soak = SOAK.read_text(encoding="utf-8")
        self.assertIn("w3_hbm_timer_reclaim_enable=0", remote)
        self.assertIn("hbm_timer_reclaim_not_disabled", remote)
        self.assertIn("w3_hbm_timer_reclaim_enable", soak)
        self.assertIn("timer_reclaim=0", soak)

    def test_uart_precedes_rf_and_local_rollback_spans_soak(self):
        pipeline = PIPELINE.read_text(encoding="utf-8")
        ap = AP.read_text(encoding="utf-8")
        self.assertLess(pipeline.index("capture = subprocess.Popen"), pipeline.index("run_qtn_w3_native_open_ap.py"))
        self.assertIn('"--defer-commit"', pipeline)
        self.assertIn('"--external-uart-capture"', pipeline)
        self.assertIn("run_qtn_w3_native_open_soak.py", pipeline)
        self.assertIn('sleep "$rollback_seconds"', ap)
        self.assertIn('case "$commit_mode" in auto|deferred)', ap)
        self.assertIn('if [ "$commit_mode" = auto ]', ap)
        self.assertIn("W3_FINAL_5G_OPEN_LOCAL_ROLLBACK_COMMIT_PASS=1", pipeline)
        self.assertIn("qtn-native-ap-rollback.sh", pipeline)

    def test_baseline_is_non_dfs_open_36_80_and_soak_is_at_least_180(self):
        pipeline = PIPELINE.read_text(encoding="utf-8")
        soak = SOAK.read_text(encoding="utf-8")
        for token in ('"channel": 36', '"bandwidth_mhz": 80', '"security": "OPEN"'):
            self.assertIn(token, pipeline)
        self.assertIn('parser.add_argument("--soak-seconds", type=int, default=180)', pipeline)
        self.assertIn('if not 180 <= args.soak_seconds <= 600', pipeline)
        self.assertIn("association_required", pipeline)
        self.assertIn('raise SoakError(f"no-progress:{key}")', soak)
        self.assertIn("no-progress:{key}", soak)
        self.assertIn('"dfs": False', soak)

    def test_ram_only_and_dry_run(self):
        combined = "\n".join(
            path.read_text(encoding="utf-8").lower()
            for path in (PIPELINE, HANDOFF, HANDOFF_REMOTE, AP, SOAK)
        )
        for forbidden in ("flash_erase", "nandwrite", "saveenv", "mtd write"):
            self.assertNotIn(forbidden, combined)
        result = subprocess.run(
            [sys.executable, "-B", str(PIPELINE)], cwd=ROOT,
            text=True, capture_output=True, check=True,
        )
        self.assertIn("W3_FINAL_5G_OPEN_PIPELINE_DRY_RUN_PASS=1", result.stdout)
        self.assertIn("'management_host': '192.168.1.90'", result.stdout)
        self.assertIn("'soak_seconds': 180", result.stdout)


if __name__ == "__main__":
    unittest.main()
