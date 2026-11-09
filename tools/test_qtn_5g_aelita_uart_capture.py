#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_qtn_5g_aelita_uart_capture.py"
spec = importlib.util.spec_from_file_location("qtn_uart_capture", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class Qtn5gAelitaUartCaptureTests(unittest.TestCase):
    def test_marker_frontier_uses_uart_order(self) -> None:
        run_id = "test-run"
        parsed = module.txpath_evaluator.evaluate(
            f"OMQTN5G_RUN stage=begin run_id={run_id}\n"
            "OMQDRVTXPATH stage=enqueue seq=1 proto=0x800 len=64\n"
            "OMQDRVTXPATH stage=hardstart seq=1 proto=0x800 len=64\n"
            "OMQDRVTXPATH stage=desc-ready seq=1 proto=0x800 len=64 hd_pa=0x1\n"
            "OMQDRVTXPATH stage=mailbox-enter seq=1 proto=0x800 len=64 hd_pa=0x1\n"
            "OMQDRVTXPATH stage=mailbox-published seq=1 proto=0x800 len=64 hd_pa=0x1\n",
            run_id,
            [{"stage": "ready", "bytes": 0}],
            1,
        )
        self.assertEqual("enqueue", parsed["txpath"]["first_marker"])
        self.assertEqual("mailbox-published", parsed["txpath"]["last_marker"])
        self.assertEqual(5, parsed["txpath"]["event_count"])

    def test_empty_uart_is_honestly_unobserved(self) -> None:
        run_id = "test-run"
        parsed = module.txpath_evaluator.evaluate(
            f"OMQTN5G_RUN stage=begin run_id={run_id}\nmanagement lost before readback",
            run_id,
            [{"stage": "ready", "bytes": 0}],
            1,
        )
        self.assertEqual("UNOBSERVED", parsed["txpath"]["first_marker"])
        self.assertEqual("UNOBSERVED", parsed["txpath"]["last_marker"])

    def test_capture_precedes_one_shot_and_outlives_it(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertLess(source.index("capture = subprocess.Popen"), source.index("one_shot = subprocess.Popen"))
        self.assertGreater(source.index("deadline = time.monotonic() + args.post_seconds"), source.index("one_shot = subprocess.Popen"))
        self.assertIn("capture-status.json", source)
        self.assertIn("capture_snapshot = wait_capture_ready", source)
        self.assertIn('"--run-id", run_id', source)
        self.assertIn('"-ExpectedPnpDeviceId", EXPECTED_UART_PNP_ID', source)
        self.assertIn(r'FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000', source)
        self.assertIn("txpath_evaluator.evaluate", source)
        self.assertIn('"FAIL_RECOVERED_AFTER_REBOOT"', source)
        self.assertIn("if capture.poll() is not None", source)
        self.assertIn('"capture-dead"', source)
        self.assertIn('"capture-dead-post-run"', source)
        self.assertIn('evaluation["terminal_state"] = "CAPTURE_INVALID"', source)
        self.assertIn("required_capture_seconds = one_shot_max_seconds + args.post_seconds + 30", source)
        self.assertIn("probe_post_recovery(args.router_host)", source)
        self.assertIn("loglevel_original_present", source)
        self.assertIn("loglevel_matches_original", source)
        self.assertIn('"--v6-scheduler-diag"', source)
        self.assertIn("5b9ae80e5121c4b00965ce4716ad80285f1b599e29845e8efbf938a79600df35", source)
        self.assertNotIn('"--tx-path-trace",', source)

    def test_dry_run_is_hardware_free(self) -> None:
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)], cwd=ROOT,
            text=True, capture_output=True, timeout=30, check=False,
        )
        self.assertEqual(0, proc.returncode, proc.stdout + proc.stderr)
        marker = "OMQTN5G_TXPATH_OOB_DRY_RUN_PASS=1"
        self.assertIn(marker, proc.stdout)
        plan = json.loads(proc.stdout[:proc.stdout.index(marker)])
        self.assertTrue(plan["capture_starts_before_qdrv"])
        self.assertTrue(plan["capture_survives_management_loss"])
        self.assertGreaterEqual(plan["capture_seconds"], plan["required_capture_seconds"])
        self.assertEqual("v6-scheduler-diag", plan["one_shot_trace_profile"])
        self.assertEqual(
            "5b9ae80e5121c4b00965ce4716ad80285f1b599e29845e8efbf938a79600df35",
            plan["qdrv_sha256"],
        )
        self.assertEqual(
            r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000",
            plan["expected_pnp_device_id"],
        )
        self.assertFalse(plan["network_changed_now"])
        self.assertFalse(plan["flash"])
        self.assertFalse(plan["reboot_by_wrapper"])

    def test_no_persistent_write_primitives(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "nandwrite", "ubiformat"):
            self.assertNotIn(forbidden, source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
