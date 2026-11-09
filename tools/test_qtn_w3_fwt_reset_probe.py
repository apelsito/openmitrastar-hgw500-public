#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/linux510-radio-port/quantenna/platform/topaz/switch_tqe.c"
REMOTE = ROOT / "tools/qtn_w3_fwt_reset_probe_remote.sh"
RUNNER = ROOT / "tools/run_qtn_w3_fwt_reset_probe.py"
CLOSED = ROOT / "work/mission-state/w3-offline/W3_FWT_RESET_PROBE_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_FWT_RESET_PROBE_GATE.approved.env"
MANIFEST = ROOT / "work/mission-state/w3-offline/W3_V89_RADIOHW_FWT_RESETPROBE_SIGNED_ARTIFACT.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FwtResetProbeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.text = SOURCE.read_text(encoding="utf-8")
        start = cls.text.index("static void w3_fwt_reset_grant_probe")
        end = cls.text.index("\n}\n#endif", start) + 2
        cls.helper = cls.text[start:end]

    def test_exact_target_and_build_gate(self) -> None:
        self.assertIn("#ifdef OPENMITRASTAR_QDRV_V89_PAIR", self.text)
        self.assertIn("module_param(w3_fwt_reset_probe_enable, int, 0400)", self.text)
        self.assertIn("w3_fwt_reset_probe_enable != 1", self.helper)
        self.assertIn(
            'of_machine_is_compatible("mitrastar,hgw-500bna-qcv2")',
            self.helper,
        )

    def test_probe_records_raw_state_request_and_rc(self) -> None:
        for marker in (
            "cpu_vec_raw=%#x",
            "cpu_vec_mask_raw=%#x",
            "pre_raw=%#x",
            "pre_state=%u",
            "pre_req=%u",
            "rc=%d",
            "post_raw=%#x",
            "post_state=%u",
            "post_req=%u",
            "released_raw=%#x",
            "released_state=%u",
            "released_req=%u",
        ):
            self.assertIn(marker, self.helper)

    def test_sysctl_reset_state_is_read_only(self) -> None:
        self.assertIn("qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC)", self.helper)
        self.assertIn("qtn_mproc_sync_mem_read(RUBY_SYS_CTL_CPU_VEC_MASK)", self.helper)
        self.assertNotIn("qtn_mproc_sync_mem_write", self.helper)
        self.assertNotIn("writel(", self.helper)

    def test_request_is_always_released_after_attempt(self) -> None:
        request = self.helper.index("__topaz_fwt_cpu_access_start_wait()")
        release = self.helper.index("__topaz_fwt_cpu_access_stop()")
        self.assertLess(request, release)
        between = self.helper[request:release]
        self.assertNotIn("return", between)
        self.assertNotIn("if (rc", between)

    def test_probe_does_not_access_fwt_tables(self) -> None:
        for forbidden in (
            "TOPAZ_FWT_ENTRY",
            "__topaz_fwt_write",
            "__topaz_fwt_read",
            "topaz_fwt_sw_entry",
            "topaz_fwt_hash",
        ):
            self.assertNotIn(forbidden, self.helper)

    def test_pre_and_post_probes_bracket_cpui_reset(self) -> None:
        init = self.text.index("static struct net_device * __init tqe_netdev_init")
        pre = self.text.index('w3_fwt_reset_grant_probe("pre-reset")', init)
        asserted = self.text.index("topaz_tqe_cpuif_setup_reset(1)", pre)
        released = self.text.index("topaz_tqe_cpuif_setup_reset(0)", asserted)
        post = self.text.index('w3_fwt_reset_grant_probe("post-reset")', released)
        self.assertLess(pre, asserted)
        self.assertLess(asserted, released)
        self.assertLess(released, post)

    def test_only_two_runtime_probe_calls_exist(self) -> None:
        self.assertEqual(self.text.count("w3_fwt_reset_grant_probe("), 3)

    def test_remote_runner_loads_only_explicit_probe(self) -> None:
        text = REMOTE.read_text(encoding="utf-8")
        self.assertIn(
            "w3_switch_tqe_only_enable=1 w3_fwt_reset_probe_enable=1",
            text,
        )
        self.assertNotIn("load fwt_ctrl.ko", text)
        self.assertNotIn("load qdrv.ko", text)
        self.assertNotIn("load wlan.ko", text)
        self.assertIn("W3_FWT_TABLE_ACCESS_ALLOWED", text)
        self.assertIn("OMFWTRESET stage=pre-reset", text)
        self.assertIn("OMFWTRESET stage=post-reset", text)

    def test_closed_and_one_shot_gates_are_separate(self) -> None:
        self.assertIn("W3_FWT_RESET_PROBE_APPROVED=0", CLOSED.read_text(encoding="utf-8"))
        approved = APPROVED.read_text(encoding="utf-8")
        self.assertIn("W3_FWT_RESET_PROBE_APPROVED=1", approved)
        self.assertIn("W3_HARDWARE_ACTIVE_APPROVED=0", approved)
        self.assertIn("W3_FWT_TABLE_ACCESS_ALLOWED=0", approved)

    def test_runner_is_ram_only_watchdog_restored_and_date_pinned(self) -> None:
        text = RUNNER.read_text(encoding="utf-8")
        self.assertIn("linux510-product-watchdog-canary-v1-RAM-ONLY.bin", text)
        self.assertIn("08503e290dbe84ed", text)
        self.assertIn('LOGICAL_DATE = "20260818"', text)
        self.assertNotIn("2026" + "0819", text)
        self.assertIn("restore_product(args.host)", text)
        self.assertIn('"flash": False', text)
        result = subprocess.run(
            ["python", str(RUNNER)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("'approved': '0'", result.stdout)
        self.assertIn("W3_FWT_RESET_PROBE_DRY_RUN_PASS=1", result.stdout)

    def test_signed_manifest_binds_all_22_modules_and_gates(self) -> None:
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["generated_utc"], "2026-08-18T02:45:00+00:00")
        self.assertEqual(len(manifest["modules"]), 22)
        artifact = ROOT / manifest["artifact"]
        release = manifest["release"]
        rows = {row["path"]: row for row in manifest["modules"]}
        switch = artifact / "rootfs/lib/modules" / release / "extra/quantenna/platform/topaz/switch_tqe.ko"
        self.assertEqual(sha(switch), rows["platform/topaz/switch_tqe.ko"]["sha256"])
        self.assertEqual(
            manifest["qdrv_sha256"],
            "2f322054c741a1e77182ac09972d35303ced59cfec28e3602a9433830f2c360d",
        )
        digest = sha(MANIFEST)
        for gate in (CLOSED, APPROVED):
            text = gate.read_text(encoding="utf-8")
            self.assertIn(f"W3_MANIFEST_SHA256={digest}", text)
            self.assertIn(f"W3_SWITCH_TQE_SHA256={sha(switch)}", text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
