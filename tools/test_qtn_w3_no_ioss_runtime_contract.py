#!/usr/bin/env python3
"""Offline contract for the post-power-cycle 5 GHz no-IOSS runtime ladder."""

from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SWITCH_RUNNER = ROOT / "tools/run_qtn_w3_switch_emac_handoff.py"
SWITCH_REMOTE = ROOT / "tools/qtn_w3_switch_emac_handoff_remote.sh"
QDRV_RUNNER = ROOT / "tools/run_qtn_w3_qdrv_hostlink_core.py"
QDRV_REMOTE = ROOT / "tools/qtn_w3_qdrv_hostlink_core_remote.sh"
PIPELINE = ROOT / "tools/run_qtn_w3_final_5g_open_pipeline.py"
AP_REMOTE = ROOT / "tools/qtn_w3_native_madwifi_open_ap.sh"

SWITCH_ORDER = (
    "qtn_pm_qos_compat", "qtn_platform_support", "board_compat",
    "runtime_compat", "iputil", "dmautil", "switch_vlan", "fwt_if",
    "hbm", "topaz_congest_queue", "emac_lib", "dpi", "switch_tqe",
    "fwt_ctrl", "switch_emac",
)
QDRV_ORDER = ("gpio", "temp_sensor", "temp_sens", "wlan", "qdrv")
WLAN_PLUGIN_ORDER = ("wlan_scan_ap", "wlan_ccmp", "wlan_xauth")


class NoIossRuntimeContractTests(unittest.TestCase):
    def test_exact_runtime_module_order(self) -> None:
        switch = SWITCH_REMOTE.read_text(encoding="utf-8")
        qdrv = QDRV_REMOTE.read_text(encoding="utf-8")
        pipeline = PIPELINE.read_text(encoding="utf-8")

        previous = -1
        for module in SWITCH_ORDER:
            position = switch.index(f"load_module {module}.ko")
            self.assertGreater(position, previous, module)
            previous = position

        previous = -1
        for module in QDRV_ORDER:
            needle = (
                "if grep -Eq '^gpio '" if module == "gpio"
                else f"load {module}.ko"
            )
            position = qdrv.index(needle)
            self.assertGreater(position, previous, module)
            previous = position

        previous = -1
        for module in WLAN_PLUGIN_ORDER:
            position = pipeline.index(f'"{module}"')
            self.assertGreater(position, previous, module)
            previous = position

    def test_switch_rollback_and_no_ioss_guards_precede_first_insmod(self) -> None:
        switch = SWITCH_REMOTE.read_text(encoding="utf-8")
        armed = switch.index("stage=preload-rollback-armed")
        first = switch.index("load_module qtn_pm_qos_compat.ko")
        policy = switch.index("stage=ioss-reset-policy mode=skip")
        board = switch.index("load_module board_compat.ko")
        self.assertLess(armed, first)
        self.assertLess(policy, board)
        self.assertIn('test "$rollback_armed" = 1', switch)
        self.assertIn("reason=unexpected_reset_probe_enabled", switch)
        self.assertIn("reason=ioss_pulse_observed", switch)
        self.assertIn("reason=direct_emac_lost_before_handoff", switch)
        self.assertIn("reason=new_fatal_kernel_marker", switch)

    def test_final_pipeline_forces_safe_switch_mode_and_ap_rollback(self) -> None:
        pipeline = PIPELINE.read_text(encoding="utf-8")
        ap = AP_REMOTE.read_text(encoding="utf-8")
        switch_call = pipeline.split(
            '"tools/run_qtn_w3_switch_emac_handoff.py"', 1
        )[1].split("], 1050)", 1)[0]
        for token in (
            '"--rx-align"', '"--skip-ioss-reset-pulse"',
            '"--no-uart-reboot-on-failure"', '"--preserve-2g"',
        ):
            self.assertIn(token, switch_call)
        self.assertLess(ap.index("OMNATIVEOPEN rollback-armed"), ap.index("printf '1\\n' >\"$rf\""))
        self.assertIn('sh "$rollback" "$root" script-failure', ap)
        self.assertIn('test -e /sys/class/net/br0/brif/eth1_emac1', ap)

    def test_uart_markers_and_stop_records_are_machine_readable(self) -> None:
        switch = SWITCH_REMOTE.read_text(encoding="utf-8")
        for marker in (
            "stage=runtime-begin", "stage=preload-rollback-armed",
            "stage=module-load-enter", "stage=module-load-pass",
            "stage=ioss-reset-policy mode=skip", "stage=ioss-reset-skipped",
            "stage=preload-complete", "stage=rollback-armed",
            "stage=awaiting-host-commit", "stage=committed",
            "W3_SWITCH_EMAC_STOP code=",
        ):
            self.assertIn(marker, switch)
        self.assertIn("module_index=${module_index:-0}", switch)

    def test_offline_dry_runs_and_shell_syntax(self) -> None:
        commands = (
            [sys.executable, "-B", str(SWITCH_RUNNER), "--rx-align",
             "--use-current-no-watchdog-boot", "--skip-ioss-reset-pulse",
             "--no-uart-reboot-on-failure"],
            [sys.executable, "-B", str(QDRV_RUNNER), "--rx-align", "--no-hw-watchdog"],
            [sys.executable, "-B", str(PIPELINE)],
        )
        expected = (
            "W3_SWITCH_EMAC_HANDOFF_DRY_RUN_PASS=1",
            "W3_QDRV_HOSTLINK_CORE_DRY_RUN_PASS=1",
            "W3_FINAL_5G_OPEN_PIPELINE_DRY_RUN_PASS=1",
        )
        for command, marker in zip(commands, expected, strict=True):
            result = subprocess.run(
                command, cwd=ROOT, text=True, capture_output=True, timeout=60,
                check=False,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)
            self.assertIn(marker, result.stdout)

        for script in (SWITCH_REMOTE, QDRV_REMOTE, AP_REMOTE):
            linux_path = "/workspace/user-home/Desktop/MitraStar/" + str(
                script.relative_to(ROOT)
            ).replace("\\", "/")
            result = subprocess.run(
                ["wsl.exe", "sh", "-n", linux_path], cwd=ROOT,
                text=True, capture_output=True, timeout=30, check=False,
            )
            self.assertEqual(0, result.returncode, result.stderr)


if __name__ == "__main__":
    unittest.main()
