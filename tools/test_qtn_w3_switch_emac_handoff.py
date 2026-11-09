#!/usr/bin/env python3

from pathlib import Path
import re
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
REMOTE = ROOT / "tools/qtn_w3_switch_emac_handoff_remote.sh"
RUNNER = ROOT / "tools/run_qtn_w3_switch_emac_handoff.py"
SWITCH_EMAC = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_emac.c"
FWT_CPUIF = ROOT / "work/sources/Quantenna-GPL/include/qtn/topaz_fwt_cpuif.h"
FWT_SW = ROOT / "work/linux510-radio-port/quantenna/platform/fwt/fwt_sw.c"
SWITCH_VLAN = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_vlan.c"
QTN_PLATFORM = ROOT / "work/linux510-radio-port/quantenna/platform/ruby/qtn_platform_support.c"
HBM = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/hbm.c"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_SWITCH_EMAC_HANDOFF_GATE.approved.env"


class SwitchEmacHandoffTests(unittest.TestCase):
    def test_gate_pair_differs_only_in_approval_and_reason(self):
        closed = CLOSED.read_text()
        approved = APPROVED.read_text()
        normalized_closed = re.sub(r"W3_SWITCH_EMAC_HANDOFF_APPROVED=0", "W3_SWITCH_EMAC_HANDOFF_APPROVED=1", closed)
        normalized_closed = normalized_closed.replace("SWITCH_EMAC_HANDOFF_NOT_APPROVED", "SWITCH_EMAC_HANDOFF_ONE_SHOT_APPROVED")
        self.assertEqual(normalized_closed, approved)

    def test_remote_has_local_rollback_before_unbind(self):
        text = REMOTE.read_text()
        armed = text.index("stage=rollback-armed")
        bridge = text.index("stage=baseline-bridge-created")
        unbind = text.index('>"$direct_driver/unbind"')
        self.assertLess(armed, unbind)
        self.assertLess(armed, bridge)
        self.assertLess(bridge, unbind)
        self.assertIn('>"$direct_driver/bind"', text)
        self.assertIn("rollback deadline", text)
        self.assertIn("awaiting-host-commit", text)
        self.assertIn("source=new-ssh", text)
        self.assertNotRegex(text, re.compile(r"\b(?:flash_erase|nandwrite|mtd_debug|ubiformat)\b"))
        self.assertNotRegex(text, re.compile(r"\bip\s+link\b"))
        self.assertIn("brctl addif br0 eth1_emac1", text)
        self.assertIn("brif/eth1_emac1", text)
        self.assertIn("stage=traffic-snapshot", text)
        self.assertIn("stage=irq-snapshot", text)
        self.assertIn("w3_force_lhost=1", text)
        self.assertIn("lhost_route_not_forced", text)

    def test_remote_preserves_management_contract(self):
        text = REMOTE.read_text()
        for token in (
            "old_mac=$(cat /sys/class/net/eth0/address)",
            "ifconfig br0 hw ether \"$old_mac\"",
            "W3_MANAGEMENT_IPV4",
            "e8000000.ethernet",
            "eth1_emac1",
            "phy=3",
            "eth1_emac0 0.0.0.0 down",
            "test ! -e /sys/class/net/br0/brif/tqe",
            "stage=baseline-bridge-created",
            'printf \'%s\\n\' "$had_br0" >"$state/had-br0"',
        ):
            self.assertIn(token, text)
        self.assertNotIn("reason=br0_absent", text)
        self.assertNotRegex(text, re.compile(r"brctl addif br0 tqe|ip link set tqe master"))

    def test_runner_is_closed_by_default_and_verifies_25_profile(self):
        text = RUNNER.read_text()
        self.assertIn('parser.add_argument("--execute", action="store_true")', text)
        self.assertIn('parser.add_argument("--wait-for-cold-power-cycle", action="store_true")', text)
        self.assertIn('boot_command.append("-SkipReboot")', text)
        self.assertIn("--use-current-watchdog-boot", text)
        self.assertIn("W3_CURRENT_WATCHDOG_BOOT_PREFLIGHT_PASS", text)
        self.assertIn("current RAM boot preflight marker missing", text)
        self.assertIn("--use-current-no-watchdog-boot", text)
        self.assertIn("HBM_COLD_MARKER", text)
        self.assertIn("requires a physical cold cycle", text)
        self.assertNotIn('parser.add_argument("--manifest", type=Path)', text)
        self.assertIn('switch-emac profile hash mismatch', text)
        self.assertIn('artifact has duplicate exported symbols', text)
        self.assertIn('artifact source gate found NULL Linux DMA API calls', text)
        self.assertIn('gate module manifest hash mismatch', text)
        self.assertIn('gate switch_emac hash mismatch', text)
        self.assertIn('"logical_date": "2026-08-19"', text)
        self.assertNotIn('qtn_w3_artifact_gate.py', text)
        self.assertIn("W3_SWITCH_EMAC_HANDOFF_DRY_RUN_PASS=1", text)
        self.assertIn("linux510-product-watchdog-canary-v1-RAM-ONLY.bin", text)
        self.assertIn("W3_SWITCH_EMAC_NEW_SSH_COMMIT", text)
        self.assertNotRegex(text, re.compile(r"\b(?:flash_erase|nandwrite|mtd_debug|ubiformat)\b"))
        self.assertIn('relative != "platform/fwt/fwt_ctrl.ko"', text)
        self.assertIn('"fwt_acceleration": "disabled-local-shims"', text)

    def test_nonbonded_port_compiles_out_proprietary_fwt_dependency(self):
        text = SWITCH_EMAC.read_text()
        self.assertIn("OMEMACSW stage=profile-pass bonding=0 fwt-remapper=compiled-out", text)
        self.assertIn("OPENMITRASTAR_SWITCH_EMAC_PORT", text)
        self.assertIn("fwt_sw_register_port_remapper", text)
        self.assertIn("EMAC_BONDING", RUNNER.read_text())
        self.assertIn("FWT_REMAPPER", RUNNER.read_text())

    def test_no_ioss_path_bypasses_fwt_ctrl_fail_closed(self):
        text = REMOTE.read_text()
        self.assertIn('if [ "$skip_ioss_reset_pulse" = 1 ]; then', text)
        self.assertIn("module_total=14", text)
        self.assertIn("OMFWTBYPASS stage=active policy=no-ioss", text)
        self.assertIn("provider=qdrv-wlan-local-shims", text)
        self.assertIn("switch_emac=nonbonded-remapper-compiled-out", text)
        self.assertIn("acceleration=disabled", text)
        self.assertIn("reason=fwt_ctrl_loaded_on_no_ioss_path", text)
        bypass = text.index("OMFWTBYPASS stage=active policy=no-ioss")
        explicit = text.index("load_module fwt_ctrl.ko w3_fwt_ctrl_only_enable=1")
        self.assertLess(bypass, explicit)
        self.assertIn('if [ "$skip_ioss_reset_pulse" = 0 ]; then', text)

    def test_current_artifact_declares_no_fwt_dependency_for_no_ioss_consumers(self):
        artifact = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-rxalign-20260820"
        deps = (artifact / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/modules.dep").read_text()
        for module in (
            "extra/quantenna/platform/topaz/switch_emac.ko:",
            "extra/quantenna/qdrv/qdrv.ko:",
            "extra/quantenna/wlan/wlan.ko:",
        ):
            row = next(line for line in deps.splitlines() if line.startswith(module))
            self.assertNotIn("platform/fwt/fwt_ctrl.ko", row)
        self.assertIn("qdrv_fwt_compat.o", (ROOT / "work/linux510-radio-port/quantenna/qdrv/Makefile").read_text())
        self.assertIn("wlan_fwt_compat.o", (ROOT / "work/linux510-radio-port/quantenna/wlan/Makefile").read_text())

    def test_hbm_irq_uses_arc_irqdomain_and_fwt_logging_is_bounded(self):
        switch_text = SWITCH_EMAC.read_text()
        self.assertIn("irq_create_mapping(domain, TOPAZ_IRQ_HBM)", switch_text)
        self.assertIn("OMEMACSW stage=hbm-irq-map", switch_text)
        self.assertIn("topaz_hbm_release_linux_irq", switch_text)
        fwt_text = FWT_CPUIF.read_text()
        self.assertIn("omfwtarb_success_logs < 4", fwt_text)
        self.assertIn("OMFWTARB stage=delayed-grant", fwt_text)
        self.assertIn("OMFWTARB stage=timeout", fwt_text)
        self.assertIn("OMFWT stage=reset-complete scanned=%u valid=%u deleted=%u", FWT_SW.read_text())

    def test_switch_vlan_uses_real_32bit_dma_device(self):
        vlan_text = SWITCH_VLAN.read_text()
        platform_text = QTN_PLATFORM.read_text()
        self.assertNotRegex(vlan_text, re.compile(r"dma_(?:alloc|free)_coherent\(NULL"))
        self.assertIn("qtn_platform_dma_device()", vlan_text)
        self.assertIn("OMVLAN stage=alloc-pass", vlan_text)
        self.assertIn("platform_device_alloc(\"openmitrastar-qtn-dma\"", platform_text)
        self.assertIn("DMA_BIT_MASK(32)", platform_text)

    def test_hbm_copy_path_restores_arc_ip_alignment(self):
        text = HBM.read_text()
        self.assertIn("alloc_skb(buf_size + NET_IP_ALIGN", text)
        self.assertIn("skb_reserve(skb, NET_IP_ALIGN)", text)
        self.assertIn("OMHBM stage=skb-align", text)

    def test_python_and_shell_syntax_and_dry_run(self):
        compile_result = subprocess.run(
            [sys.executable, "-m", "py_compile", str(RUNNER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(compile_result.returncode, 0, compile_result.stderr)
        shell_result = subprocess.run(
            ["wsl.exe", "sh", "-n", "/workspace/user-home/Desktop/MitraStar/tools/qtn_w3_switch_emac_handoff_remote.sh"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        self.assertEqual(shell_result.returncode, 0, shell_result.stderr)
        dry = subprocess.run(
            [sys.executable, str(RUNNER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(dry.returncode, 0, dry.stderr)
        self.assertIn("W3_SWITCH_EMAC_HANDOFF_DRY_RUN_PASS=1", dry.stdout)


if __name__ == "__main__":
    unittest.main()
