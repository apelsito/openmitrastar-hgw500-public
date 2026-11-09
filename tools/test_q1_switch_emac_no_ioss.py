#!/usr/bin/env python3
from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tools/run_qtn_w3_switch_emac_handoff.py"
REMOTE = ROOT / "tools/qtn_w3_switch_emac_handoff_remote.sh"
PIPELINE = ROOT / "tools/run_qtn_w3_final_5g_open_pipeline.py"

SWITCH_ORDER = (
    "qtn_pm_qos_compat", "qtn_platform_support", "board_compat",
    "runtime_compat", "iputil", "dmautil", "switch_vlan", "fwt_if",
    "hbm", "topaz_congest_queue", "emac_lib", "dpi", "switch_tqe",
    "fwt_ctrl", "switch_emac",
)


class Q1SwitchEmacNoIossTests(unittest.TestCase):
    def test_q1_mode_is_explicit_and_default_path_is_preserved(self) -> None:
        runner = RUNNER.read_text(encoding="utf-8")
        remote = REMOTE.read_text(encoding="utf-8")
        self.assertIn("--skip-ioss-reset-pulse", runner)
        self.assertIn("W3_SKIP_IOSS_RESET_PULSE", runner)
        self.assertIn('stage=ioss-reset-skipped', remote)
        self.assertIn('stage=ioss-reset-policy mode=skip', remote)
        self.assertIn('reason=unexpected_reset_probe_enabled', remote)
        self.assertIn('reason=ioss_pulse_observed', remote)
        self.assertIn('w3_fwt_ioss_only_probe_enable=1', remote)
        self.assertRegex(remote, re.compile(r'if \[ "\$skip_ioss_reset_pulse" = 1 \]'))
        no_ioss_branch = remote.split(
            'if [ "$skip_ioss_reset_pulse" = 1 ]; then', 1
        )[1].split("\nelse\n", 1)[0]
        self.assertNotIn("w3_fwt_ioss_only_probe_enable=1", no_ioss_branch)
        self.assertIn("w3_fwt_ioss_only_probe_enable", no_ioss_branch)

    def test_exact_switch_module_order_is_pinned_and_uart_marked(self) -> None:
        runner = RUNNER.read_text(encoding="utf-8")
        remote = REMOTE.read_text(encoding="utf-8")
        previous = -1
        for module in SWITCH_ORDER:
            position = remote.index(f"load_module {module}.ko")
            self.assertGreater(position, previous, module)
            previous = position
            self.assertIn(module + ".ko", runner)
        self.assertIn("module_total=15", remote)
        self.assertIn("stage=module-load-enter", remote)
        self.assertIn("stage=module-load-pass", remote)
        self.assertIn("reason=module_order_incomplete", remote)

    def test_preload_rollback_is_armed_before_first_qtn_module(self) -> None:
        remote = REMOTE.read_text(encoding="utf-8")
        armed = remote.index("stage=preload-rollback-armed")
        first_load = remote.index("load_module qtn_pm_qos_compat.ko")
        disarmed = remote.index("stage=preload-rollback-disarmed")
        unbind = remote.index('>"$direct_driver/unbind"')
        self.assertLess(armed, first_load)
        self.assertLess(first_load, disarmed)
        self.assertLess(disarmed, unbind)
        self.assertIn('test "$rollback_armed" = 1', remote)
        self.assertIn("reason=rollback_not_armed", remote)
        self.assertIn("reason=module_load_failed", remote)
        self.assertIn("reason=new_fatal_kernel_marker", remote)

    def test_final_5g_pipeline_cannot_regress_to_ioss_pulse(self) -> None:
        pipeline = PIPELINE.read_text(encoding="utf-8")
        switch_call = pipeline.split(
            '"tools/run_qtn_w3_switch_emac_handoff.py"', 1
        )[1].split("], 1050)", 1)[0]
        self.assertIn('"--skip-ioss-reset-pulse"', switch_call)
        self.assertIn('"--no-uart-reboot-on-failure"', switch_call)
        self.assertIn('"--rx-align"', switch_call)
        self.assertIn('"skip_ioss_reset_pulse": True', pipeline)

    def test_dry_run_has_no_hardware_or_reboot(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(RUNNER), "--rx-align", "--use-current-no-watchdog-boot",
             "--host", "192.168.1.90", "--management-host", "192.168.1.90",
             "--preserve-2g", "--skip-ioss-reset-pulse", "--no-uart-reboot-on-failure"],
            cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        self.assertIn("W3_SWITCH_EMAC_HANDOFF_DRY_RUN_PASS=1", proc.stdout)
        self.assertIn("'flash': False", proc.stdout)
        self.assertIn("'skip_ioss_reset_pulse': True", proc.stdout)
        self.assertIn("'rollback_before_first_insmod': True", proc.stdout)


if __name__ == "__main__":
    unittest.main()
