#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_qtn_5g_auc_muc_oob_v5.py"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(directory: str) -> Path:
    proc = subprocess.run(
        [sys.executable, str(BUILDER), "--output-dir", directory],
        cwd=ROOT, text=True, capture_output=True, timeout=60, check=False,
    )
    if proc.returncode:
        raise AssertionError(proc.stdout + proc.stderr)
    return Path(directory)


def load_evaluator(path: Path):
    spec = importlib.util.spec_from_file_location("qtn_v5_evaluator_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class Qtn5gAucMucOobV5Tests(unittest.TestCase):
    def test_package_is_reproducible_and_self_pinned(self) -> None:
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            pa, pb = build(a), build(b)
            ma = json.loads((pa / "manifest.json").read_text(encoding="utf-8"))
            mb = json.loads((pb / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(ma, mb)
            for name, meta in ma["artifacts"].items():
                self.assertEqual(meta["sha256"], sha256(pa / name))

    def test_one_shot_uses_only_package_runtime_and_overrides_stop(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = build(directory)
            text = (package / "run_qtn_5g_aelita_one_shot_v5.py").read_text(encoding="utf-8")
            self.assertIn("TRACE_DIR = PACKAGE_DIR", text)
            self.assertIn("qdrv-tqe-rxalign-whcopy-auctx-muc-v5.ko", text)
            self.assertIn("qtn_runner.SAFE_STOP = (TRACE_STOP, TRACE_STOP_SHA)", text)
            self.assertNotIn("quantenna-5g-tqe-rxalign-whcopy-runtime-v4-20260823", text)

    def test_exception_preserves_overlay_for_armed_outer_rollback(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = build(directory)
            text = (package / "run_qtn_5g_aelita_one_shot_v5.py").read_text(encoding="utf-8")
            start = text.index("    except Exception as original_error:")
            exception = text[start : text.index("    finally:", start)]
            self.assertIn("overlay_staged and rollback_armed", exception)
            self.assertIn("stop_radio5_exception_verified", exception)
            self.assertNotIn("cleanup_safe_overlay(args.router_host)", exception.split("elif overlay_staged:")[0])
            self.assertIn("elif overlay_staged:", exception)
            self.assertIn("cleanup_safe_overlay(args.router_host)", exception.split("elif overlay_staged:")[1])
            self.assertIn("outer rollback remains armed", exception)

    def test_verified_exception_stop_checks_v5_exit_status(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = build(directory)
            text = (package / "run_qtn_5g_aelita_one_shot_v5.py").read_text(encoding="utf-8")
            helper = text[text.index("def stop_radio5_exception_verified") : text.index("def verify_local")]
            self.assertIn('test -x "$stop"', helper)
            self.assertIn('stop_rc=$?', helper)
            self.assertIn("auc_tx_restore=proven", helper)
            self.assertIn("result.returncode == 0", helper)

    def test_coordinator_pins_local_one_shot_and_evaluator(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = build(directory)
            text = (package / "run_qtn_5g_aelita_uart_capture_v5.py").read_text(encoding="utf-8")
            self.assertIn('ONE_SHOT = PACKAGE_DIR / "run_qtn_5g_aelita_one_shot_v5.py"', text)
            self.assertIn('EVALUATOR = PACKAGE_DIR / "evaluate_qtn_5g_uart_txpath_v5.py"', text)
            self.assertIn("quantenna-5g-auc-muc-oob-v5-20260823", text)

    def test_evaluator_requires_auc_restore_zero(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = build(directory)
            evaluator = load_evaluator(package / "evaluate_qtn_5g_uart_txpath_v5.py")
            run_id = "v5-test"
            base = (
                f"OMQTN5G_RUN stage=begin run_id={run_id}\n"
                f"OMRADIO5_ROLLBACK_COMPLETE run_id={run_id} stop_rc=0 "
                "loglevel_restore_rc=0 eth0_2g=preserved\n"
            )
            post = {"management_ok": True, "recovery_clean": True, "loglevel_matches_original": True}
            events = [{"stage": "ready", "bytes": 0}]
            good = base + (
                "OMRADIO5_ROLLBACK_COMPLETE reason=timeout rf=closed wifi0=down "
                "eth0_2g=preserved auc_tx_restore_rc=0 secrets=redacted\n"
            )
            bad = base + (
                "OMRADIO5_ROLLBACK_COMPLETE reason=timeout rf=closed wifi0=down "
                "eth0_2g=preserved auc_tx_restore_rc=1 secrets=redacted\n"
            )
            self.assertEqual("FAIL_ROLLED_BACK", evaluator.evaluate(good, run_id, events, 1, post)["terminal_state"])
            self.assertEqual("FAIL_RECOVERY_UNPROVEN", evaluator.evaluate(bad, run_id, events, 1, post)["terminal_state"])
            self.assertEqual("FAIL_RECOVERY_UNPROVEN", evaluator.evaluate(base, run_id, events, 1, post)["terminal_state"])

    def test_outer_rollback_parser_accepts_appended_field(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = build(directory)
            evaluator = load_evaluator(package / "evaluate_qtn_5g_uart_txpath_v5.py")
            run_id = "v5-extra"
            text = (
                f"OMQTN5G_RUN stage=begin run_id={run_id}\n"
                f"OMRADIO5_ROLLBACK_COMPLETE run_id={run_id} stop_rc=0 "
                "loglevel_restore_rc=0 eth0_2g=preserved auc_tx_restore_rc=0\n"
                "OMRADIO5_ROLLBACK_COMPLETE reason=timeout rf=closed wifi0=down "
                "eth0_2g=preserved auc_tx_restore_rc=0 secrets=redacted\n"
            )
            post = {"management_ok": True, "recovery_clean": True, "loglevel_matches_original": True}
            result = evaluator.evaluate(text, run_id, [{"stage": "ready", "bytes": 0}], 1, post)
            self.assertTrue(result["rollback_codes_ok"])
            self.assertTrue(result["rollback_auc_tx_restore_ok"])

    def test_manifest_contains_exact_ram_only_command(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            package = build(directory)
            manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
            self.assertIn("run_qtn_5g_aelita_uart_capture_v5.py", manifest["exact_command"])
            self.assertFalse(manifest["flash"])
            self.assertFalse(manifest["mtd"])
            self.assertFalse(manifest["bootenv"])
            self.assertTrue(manifest["single_run"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
