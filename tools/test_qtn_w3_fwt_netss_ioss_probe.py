#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/platform/ruby/board_compat.c"
REMOTE = ROOT / "tools/qtn_w3_fwt_netss_ioss_probe_remote.sh"
RUNNER = ROOT / "tools/run_qtn_w3_fwt_netss_ioss_probe.py"
WAITER = ROOT / "tools/wait_topaz_uart_marker.ps1"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_FWT_NETSS_IOSS_PROBE_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_FWT_NETSS_IOSS_PROBE_GATE.approved.env"
MANIFEST = ROOT / "work/mission-state/w3-offline/W3_V89_RADIOHW_FWT_NETSS_IOSS_SIGNED_ARTIFACT.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FwtNetssIossProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")
        start = cls.text.index("static int w3_fwt_netss_ioss_pulse_probe(void)")
        end = cls.text.index("\n}\n#endif", start) + 2
        cls.probe = cls.text[start:end]

    def test_exact_target_and_explicit_mutually_exclusive_gate(self) -> None:
        self.assertIn(
            "module_param(w3_fwt_netss_ioss_pulse_probe_enable, int, 0400)",
            self.text,
        )
        self.assertIn(
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            self.text,
        )
        self.assertIn("w3_fwt_rxp_quiesce_probe_enable != 0", self.text)
        self.assertIn("w3_fwt_netss_ioss_pulse_probe_enable != 0", self.text)

    def test_exact_oem_pulse_order_and_50ms_wait(self) -> None:
        self.assertIn("BUILD_BUG_ON(OMFWT_NI_RESET_MASK != 0x000000a0U)", self.probe)
        self.assertIn("BUILD_BUG_ON(OMFWT_NI_RESET_MASK & RUBY_SYS_CTL_RESET_ENET0)", self.probe)
        snapshot = self.probe.index("mask_before = qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC_MASK)")
        mask = self.probe.index("qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC_MASK,")
        assert_reset = self.probe.index("qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC, 0)")
        wait = self.probe.index("mdelay(OMFWT_NI_WAIT_MS)")
        release = self.probe.index("qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC,\n\t\tOMFWT_NI_RESET_MASK)")
        clear_mask = self.probe.index("qtn_mproc_sync_mem_write_wmb(RUBY_SYS_CTL_CPU_VEC_MASK, 0)")
        request = self.probe.index("__topaz_fwt_cpu_access_start_wait()")
        release_fwt = self.probe.index("__topaz_fwt_cpu_access_stop()")
        self.assertLess(snapshot, mask)
        self.assertLess(mask, assert_reset)
        self.assertLess(assert_reset, wait)
        self.assertLess(wait, release)
        self.assertLess(release, clear_mask)
        self.assertLess(clear_mask, request)
        self.assertLess(request, release_fwt)

    def test_preconditions_and_exact_readback_are_fail_closed(self) -> None:
        self.assertIn("mask_before != 0", self.probe)
        self.assertIn("vec_released != vec_before", self.probe)
        self.assertIn("mask_released != mask_before", self.probe)
        self.assertIn("mask_asserted != OMFWT_NI_RESET_MASK", self.probe)
        self.assertIn("return -EIO", self.probe)

    def test_no_fwt_table_or_other_subsystem_writes(self) -> None:
        self.assertEqual(self.probe.count("qtn_mproc_sync_mem_write_wmb("), 4)
        for forbidden in (
            "TOPAZ_FWT_ENTRY",
            "topaz_fwt_get_hw_entry",
            "topaz_fwt_insert_entry",
            "TOPAZ_EMAC_RXP_CTRL",
            "topaz_tqe_cpuif_setup",
            "request_irq",
            "dma_",
            "vlan",
            "qdrv",
            "wlan",
        ):
            self.assertNotIn(forbidden, self.probe)

    def test_remote_is_detached_and_loads_only_symbol_provider_and_board(self) -> None:
        text = REMOTE.read_text(encoding="utf-8")
        self.assertIn("trap '' HUP", text)
        provider = text.index('"$root/ram_insmod" "$root/qtn_platform_support.ko"')
        board = text.index('"$root/ram_insmod" "$root/board_compat.ko"')
        self.assertLess(provider, board)
        self.assertIn("w3_fwt_netss_ioss_pulse_probe_enable=1", text)
        self.assertNotIn("load switch_tqe", text)
        self.assertNotIn("load fwt_ctrl", text)
        self.assertNotIn("load qdrv", text)
        self.assertNotIn("load wlan", text)

    def test_runner_uses_uart_then_sysrq_not_ssh_completion(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("wait_topaz_uart_marker.ps1", text)
        self.assertIn("OMFWTNI stage=complete", text)
        self.assertIn("except subprocess.TimeoutExpired", text)
        self.assertIn("UART remains authoritative", text)
        marker_wait = text.index("uart_wait.wait(timeout=135)")
        sysrq = text.index('"tools/uart_sysrq_reboot.ps1"', marker_wait)
        restore = text.index("restore_product(args.host)", sysrq)
        self.assertLess(marker_wait, sysrq)
        self.assertLess(sysrq, restore)
        self.assertIn('"ssh_completion_dependency": False', text)
        self.assertIn('LOGICAL_DATE = "20260818"', text)
        self.assertNotIn("2026" + "0819", text)

    def test_uart_waiter_is_receive_only(self) -> None:
        text = WAITER.read_text(encoding="utf-8")
        self.assertIn("TOPAZ_UART_MARKER_PASS", text)
        self.assertIn("$serial.Read(", text)
        self.assertNotIn("$serial.Write(", text)
        self.assertNotIn("BreakState = $true", text)

    def test_gates_are_split_and_narrow(self) -> None:
        self.assertIn("W3_FWT_NETSS_IOSS_PROBE_APPROVED=0", CLOSED.read_text(encoding="utf-8"))
        approved = APPROVED.read_text(encoding="utf-8")
        for marker in (
            "W3_FWT_NETSS_IOSS_PROBE_APPROVED=1",
            "W3_HARDWARE_ACTIVE_APPROVED=0",
            "W3_FWT_TABLE_ACCESS_ALLOWED=0",
            "W3_RESET_PULSE_MASK=0x000000a0",
            "W3_RESET_WAIT_MS=50",
            "W3_ENET0_RESET_ALLOWED=0",
            "W3_OTHER_MMIO_WRITES_ALLOWED=0",
        ):
            self.assertIn(marker, approved)

    def test_runner_dry_run_and_signed_manifest(self) -> None:
        result = subprocess.run(
            ["python", str(RUNNER)], cwd=ROOT, capture_output=True, text=True, timeout=60
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("'approved': '0'", result.stdout)
        self.assertIn("W3_FWT_NETSS_IOSS_PROBE_DRY_RUN_PASS=1", result.stdout)
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["generated_utc"], "2026-08-18T03:45:00+00:00")
        self.assertEqual(len(manifest["modules"]), 22)
        artifact = ROOT / manifest["artifact"]
        release = manifest["release"]
        rows = {row["path"]: row for row in manifest["modules"]}
        board = artifact / "rootfs/lib/modules" / release / "extra/quantenna/platform/ruby/board_compat.ko"
        support = artifact / "rootfs/lib/modules" / release / "extra/quantenna/platform/ruby/qtn_platform_support.ko"
        self.assertEqual(sha(board), rows["platform/ruby/board_compat.ko"]["sha256"])
        self.assertEqual(sha(support), rows["platform/ruby/qtn_platform_support.ko"]["sha256"])
        digest = sha(MANIFEST)
        for gate in (CLOSED, APPROVED):
            gate_text = gate.read_text(encoding="utf-8")
            self.assertIn(f"W3_MANIFEST_SHA256={digest}", gate_text)
            self.assertIn(f"W3_BOARD_COMPAT_SHA256={sha(board)}", gate_text)
            self.assertIn(f"W3_QTN_PLATFORM_SUPPORT_SHA256={sha(support)}", gate_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
