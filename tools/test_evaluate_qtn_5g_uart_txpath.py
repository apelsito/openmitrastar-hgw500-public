#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/evaluate_qtn_5g_uart_txpath.py"
spec = importlib.util.spec_from_file_location("txpath_eval", SCRIPT)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
RUN = "run-123"
READY = [{"stage": "ready", "bytes": 0}]
MANAGEMENT = {
    "management_ok": True,
    "recovery_clean": True,
    "loglevel_matches_original": True,
}


def chain(last: str = "txdone", seq: int = 7, hd: str = "0x1234") -> str:
    lines = []
    for stage in module.STAGES:
        fields = f"seq={seq} proto=0x800 len=64"
        if stage in {"desc-ready", "mailbox-enter", "mailbox-published", "txdone"}:
            fields += f" hd_pa={hd}"
        lines.append(f"OMQDRVTXPATH stage={stage} {fields}")
        if stage == last:
            break
    return "\n".join(lines)


def window(body: str, tail: str = "") -> str:
    return f"noise\nOMQTN5G_RUN stage=begin run_id={RUN}\n{body}\n{tail}\n"


class TxPathUartEvaluatorTests(unittest.TestCase):
    def test_full_chain_committed_passes(self) -> None:
        result = module.evaluate(
            window(chain(), f"OMQTN5G_RUN stage=commit run_id={RUN}"), RUN, READY, 0,
            MANAGEMENT,
        )
        self.assertEqual("PASS_COMMITTED", result["terminal_state"])
        self.assertEqual("enqueue", result["txpath"]["first_marker"])
        self.assertEqual("txdone", result["txpath"]["last_marker"])

    def test_each_partial_frontier_is_preserved(self) -> None:
        for stage in module.STAGES:
            result = module.evaluate(window(chain(stage)), RUN, READY, 1)
            self.assertEqual(stage, result["txpath"]["best_packet"]["frontier"])

    def test_dequeue_enter_is_partial_tx_evidence(self) -> None:
        result = module.evaluate(
            window("OMQDRVTXPATH stage=dequeue-enter seq=1 root_qlen=1 stopped=0 queue_enabled=0 data_desc=511 mgmt_desc=255"),
            RUN, READY, 1,
        )
        self.assertEqual("dequeue-enter", result["txpath"]["first_marker"])
        self.assertEqual("dequeue-enter", result["txpath"]["best_packet"]["frontier"])
        self.assertEqual(1, result["txpath"]["event_count"])

    def test_stale_markers_before_run_are_ignored(self) -> None:
        text = chain() + "\n" + window(chain("hardstart"))
        result = module.evaluate(text, RUN, READY, 1)
        self.assertEqual("hardstart", result["txpath"]["last_marker"])

    def test_packet_identity_mismatch_stops_chain(self) -> None:
        text = window(
            "OMQDRVTXPATH stage=enqueue seq=1 proto=0x800 len=64\n"
            "OMQDRVTXPATH stage=hardstart seq=1 proto=0x800 len=64\n"
            "OMQDRVTXPATH stage=desc-ready seq=1 proto=0x800 len=64 hd_pa=0x1\n"
            "OMQDRVTXPATH stage=mailbox-enter seq=1 proto=0x800 len=64 hd_pa=0x2"
        )
        result = module.evaluate(text, RUN, READY, 1)
        self.assertEqual("desc-ready", result["txpath"]["best_packet"]["frontier"])
        self.assertTrue(result["txpath"]["best_packet"]["identity_mismatch"])

    def test_capture_gap_inside_window_is_invalid(self) -> None:
        text = window(chain("enqueue"))
        begin = text.index("OMQTN5G_RUN")
        events = [{"stage": "ready", "bytes": 0}, {"stage": "port-lost", "bytes": begin + 5}]
        result = module.evaluate(text, RUN, events, 1)
        self.assertEqual("CAPTURE_INVALID", result["terminal_state"])

    def test_rollback_is_terminal(self) -> None:
        result = module.evaluate(
            window(chain("hardstart"), f"OMRADIO5_ROLLBACK_COMPLETE run_id={RUN} stop_rc=0 loglevel_restore_rc=0 eth0_2g=preserved"),
            RUN, READY, 1, MANAGEMENT,
        )
        self.assertEqual("FAIL_ROLLED_BACK", result["terminal_state"])

    def test_reboot_and_recovery_are_terminal(self) -> None:
        result = module.evaluate(
            window(chain("mailbox-published"), "reboot: Restarting system\nBoot reached stage 13\nOMSSH_READY port=22"),
            RUN, READY, 1, MANAGEMENT,
        )
        self.assertEqual("FAIL_RECOVERED_AFTER_REBOOT", result["terminal_state"])

    def test_rollback_marker_without_external_recovery_is_unproven(self) -> None:
        result = module.evaluate(
            window(chain("hardstart"), f"OMRADIO5_ROLLBACK_COMPLETE run_id={RUN} stop_rc=0 loglevel_restore_rc=0 eth0_2g=preserved"),
            RUN, READY, 1,
        )
        self.assertEqual("FAIL_RECOVERY_UNPROVEN", result["terminal_state"])

    def test_rollback_stop_failure_is_unproven(self) -> None:
        result = module.evaluate(
            window(chain("hardstart"), f"OMRADIO5_ROLLBACK_COMPLETE run_id={RUN} stop_rc=1 loglevel_restore_rc=0 eth0_2g=preserved"),
            RUN, READY, 1, MANAGEMENT,
        )
        self.assertEqual("FAIL_RECOVERY_UNPROVEN", result["terminal_state"])
        self.assertFalse(result["rollback_codes_ok"])

    def test_rollback_loglevel_restore_failure_is_unproven(self) -> None:
        result = module.evaluate(
            window(chain("hardstart"), f"OMRADIO5_ROLLBACK_COMPLETE run_id={RUN} stop_rc=0 loglevel_restore_rc=1 eth0_2g=preserved"),
            RUN, READY, 1, MANAGEMENT,
        )
        self.assertEqual("FAIL_RECOVERY_UNPROVEN", result["terminal_state"])
        self.assertFalse(result["rollback_codes_ok"])

    def test_rollback_without_external_loglevel_match_is_unproven(self) -> None:
        result = module.evaluate(
            window(chain("hardstart"), f"OMRADIO5_ROLLBACK_COMPLETE run_id={RUN} stop_rc=0 loglevel_restore_rc=0 eth0_2g=preserved"),
            RUN, READY, 1,
            {"management_ok": True, "recovery_clean": True, "loglevel_matches_original": False},
        )
        self.assertEqual("FAIL_RECOVERY_UNPROVEN", result["terminal_state"])

    def test_clean_rollback_without_management_is_unproven(self) -> None:
        result = module.evaluate(
            window(chain("hardstart"), f"OMRADIO5_ROLLBACK_COMPLETE run_id={RUN} rc=0"),
            RUN, READY, 1, {"management_ok": False, "recovery_clean": True},
        )
        self.assertEqual("FAIL_RECOVERY_UNPROVEN", result["terminal_state"])

    def test_reboot_marker_without_external_recovery_is_unproven(self) -> None:
        result = module.evaluate(
            window(chain("mailbox-enter"), "reboot: Restarting system\nOMSSH_READY port=22"),
            RUN, READY, 1,
        )
        self.assertEqual("FAIL_RECOVERY_UNPROVEN", result["terminal_state"])

    def test_clean_reboot_without_management_is_unproven(self) -> None:
        result = module.evaluate(
            window(chain("mailbox-enter"), "reboot: Restarting system\nOMSSH_READY port=22"),
            RUN, READY, 1, {"management_ok": False, "recovery_clean": True},
        )
        self.assertEqual("FAIL_RECOVERY_UNPROVEN", result["terminal_state"])

    def test_no_tx_and_no_recovery_is_unproven(self) -> None:
        result = module.evaluate(window("no packet"), RUN, READY, 1)
        self.assertEqual("FAIL_RECOVERY_UNPROVEN", result["terminal_state"])
        self.assertEqual("UNOBSERVED", result["txpath"]["first_marker"])

    def test_fatal_never_commits(self) -> None:
        result = module.evaluate(
            window(chain(), f"Kernel panic\nOMQTN5G_RUN stage=commit run_id={RUN}"), RUN, READY, 0
        )
        self.assertEqual("FAIL_RECOVERY_UNPROVEN", result["terminal_state"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
