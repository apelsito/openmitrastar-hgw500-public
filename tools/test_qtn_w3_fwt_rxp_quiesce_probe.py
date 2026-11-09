#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/platform/ruby/board_compat.c"
REMOTE = ROOT / "tools/qtn_w3_fwt_rxp_quiesce_probe_remote.sh"
RUNNER = ROOT / "tools/run_qtn_w3_fwt_rxp_quiesce_probe.py"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_FWT_RXP_QUIESCE_PROBE_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_FWT_RXP_QUIESCE_PROBE_GATE.approved.env"
MANIFEST = ROOT / "work/mission-state/w3-offline/W3_V89_RADIOHW_FWT_RXPQUIESCE_SIGNED_ARTIFACT.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FwtRxpQuiesceProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")
        start = cls.text.index("static int w3_fwt_rxp_quiesce_probe(void)")
        end = cls.text.index("\n}\n#endif", start) + 2
        cls.probe = cls.text[start:end]

    def test_exact_target_and_explicit_gate(self) -> None:
        self.assertIn(
            "module_param(w3_fwt_rxp_quiesce_probe_enable, int, 0400)",
            self.text,
        )
        self.assertIn(
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            self.text,
        )
        self.assertIn("w3_fwt_rxp_quiesce_probe_enable != 1", self.text)

    def test_single_exact_rxp_register_is_snapshot_zero_restored(self) -> None:
        self.assertIn("#define OMFWT_RXP_EMAC0_BASE\t0xe8000000U", self.text)
        self.assertIn("TOPAZ_EMAC_RXP_CTRL", self.text)
        self.assertIn("OMFWT_RXP_EXPECTED\t0x00000021U", self.text)
        snapshot = self.probe.index("before = qtn_mproc_sync_mem_read(OMFWT_RXP_CTRL_ADDR)")
        quiesce = self.probe.index("qtn_mproc_sync_mem_write_wmb(OMFWT_RXP_CTRL_ADDR, 0)")
        request = self.probe.index("__topaz_fwt_cpu_access_start_wait()")
        release = self.probe.index("__topaz_fwt_cpu_access_stop()")
        restore = self.probe.index("qtn_mproc_sync_mem_write_wmb(OMFWT_RXP_CTRL_ADDR, before)")
        readback = self.probe.index("restored = qtn_mproc_sync_mem_read(OMFWT_RXP_CTRL_ADDR)")
        self.assertLess(snapshot, quiesce)
        self.assertLess(quiesce, request)
        self.assertLess(request, release)
        self.assertLess(release, restore)
        self.assertLess(restore, readback)

    def test_probe_never_accesses_fwt_table_or_other_subsystems(self) -> None:
        for forbidden in (
            "TOPAZ_FWT_ENTRY",
            "topaz_fwt_get_hw_entry",
            "topaz_fwt_insert_entry",
            "topaz_tqe_cpuif_setup",
            "request_irq",
            "dma_",
            "vlan",
            "qdrv",
            "wlan",
        ):
            self.assertNotIn(forbidden, self.probe)

    def test_remote_is_detached_and_loads_only_board_probe(self) -> None:
        text = REMOTE.read_text(encoding="utf-8")
        self.assertIn("trap '' HUP", text)
        self.assertIn('exec sh "$0" --worker', text)
        self.assertIn("--worker", text)
        self.assertIn("w3_fwt_rxp_quiesce_probe_enable=1", text)
        provider = text.index('"$root/ram_insmod" "$root/qtn_platform_support.ko"')
        board = text.index('"$root/ram_insmod" "$root/board_compat.ko"')
        self.assertLess(provider, board)
        self.assertNotIn("load switch_tqe", text)
        self.assertNotIn("load fwt_ctrl", text)
        self.assertNotIn("load qdrv", text)
        self.assertNotIn("load wlan", text)
        self.assertIn("OMTQE stage=ring-programmed", text)

    def test_gates_are_split_and_one_variable_only(self) -> None:
        self.assertIn("W3_FWT_RXP_QUIESCE_PROBE_APPROVED=0", CLOSED.read_text(encoding="utf-8"))
        approved = APPROVED.read_text(encoding="utf-8")
        self.assertIn("W3_FWT_RXP_QUIESCE_PROBE_APPROVED=1", approved)
        self.assertIn("W3_HARDWARE_ACTIVE_APPROVED=0", approved)
        self.assertIn("W3_FWT_TABLE_ACCESS_ALLOWED=0", approved)
        self.assertIn("W3_EMAC0_RXP_WRITE_ALLOWED=1", approved)
        self.assertIn("W3_OTHER_MMIO_WRITES_ALLOWED=0", approved)

    def test_runner_is_watchdog_ram_only_detached_and_restores_product(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("linux510-product-watchdog-canary-v1-RAM-ONLY.bin", text)
        self.assertIn('LOGICAL_DATE = "20260818"', text)
        self.assertIn("wait_for_worker(args.host)", text)
        self.assertIn('support = module_root / "qtn_platform_support.ko"', text)
        self.assertIn("restore_product(args.host)", text)
        self.assertIn('"flash": False', text)
        self.assertNotIn("2026" + "0819", text)
        result = subprocess.run(
            ["python", str(RUNNER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("'approved': '0'", result.stdout)
        self.assertIn("W3_FWT_RXP_QUIESCE_PROBE_DRY_RUN_PASS=1", result.stdout)

    def test_signed_manifest_binds_all_modules_and_gates(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["generated_utc"], "2026-08-18T03:15:00+00:00")
        self.assertEqual(len(manifest["modules"]), 22)
        artifact = ROOT / manifest["artifact"]
        release = manifest["release"]
        rows = {row["path"]: row for row in manifest["modules"]}
        board = artifact / "rootfs/lib/modules" / release / "extra/quantenna/platform/ruby/board_compat.ko"
        support = artifact / "rootfs/lib/modules" / release / "extra/quantenna/platform/ruby/qtn_platform_support.ko"
        self.assertEqual(sha(board), rows["platform/ruby/board_compat.ko"]["sha256"])
        self.assertEqual(
            sha(support), rows["platform/ruby/qtn_platform_support.ko"]["sha256"]
        )
        digest = sha(MANIFEST)
        for gate in (CLOSED, APPROVED):
            text = gate.read_text(encoding="utf-8")
            self.assertIn(f"W3_MANIFEST_SHA256={digest}", text)
            self.assertIn(f"W3_BOARD_COMPAT_SHA256={sha(board)}", text)
            self.assertIn(f"W3_QTN_PLATFORM_SUPPORT_SHA256={sha(support)}", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
