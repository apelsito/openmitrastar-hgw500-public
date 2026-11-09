#!/usr/bin/env python3
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOOT = ROOT / "tools/run_w2_tx12_ram_boot.ps1"
COLLECT_PS1 = ROOT / "tools/collect_w2_tx12_mgmt_trace.ps1"
COLLECT_PY = ROOT / "tools/collect_w2_tx12_mgmt_trace.py"


def raw_trace(
    after_lines: list[str],
    before_lines: list[str] | None = None,
    hostapd_after: list[str] | None = None,
    iw_after: list[str] | None = None,
) -> str:
    before = "\n".join(before_lines or [])
    after = "\n".join(after_lines)
    return "\n".join(
        [
            "OM_UNAME_BEGIN",
            "Linux openmitrastar-ramssh 5.10.260-openmitrastar-radiohw",
            "OM_UNAME_END",
            "OM_BOOT_STATE_BEGIN",
            "ready",
            "OM_BOOT_STATE_END",
            "OM_RADIO_STATE_BEGIN",
            "ready",
            "OM_RADIO_STATE_END",
            "OM_HOSTAPD_STATUS_BEGIN",
            "state=ENABLED",
            "ssid[0]=OpenMitraStar-2G-DIAG",
            "num_sta[0]=0",
            "freq=2412",
            "channel=1",
            "OM_HOSTAPD_STATUS_END",
            "OM_HOSTAPD_ALL_STA_BEGIN",
            "OM_HOSTAPD_ALL_STA_END",
            "OM_IW_INFO_BEGIN",
            "Interface wlan0",
            "OM_IW_INFO_END",
            "OM_IW_STATION_BEGIN",
            "OM_IW_STATION_END",
            "OM_TRACE_BEFORE_BEGIN",
            before,
            "OM_TRACE_BEFORE_END",
            "OM_TRACE_AFTER_BEGIN",
            after,
            "OM_TRACE_AFTER_END",
            "OM_HOSTAPD_STATUS_AFTER_BEGIN",
            *(hostapd_after or []),
            "OM_HOSTAPD_STATUS_AFTER_END",
            "OM_HOSTAPD_ALL_STA_AFTER_BEGIN",
            "OM_HOSTAPD_ALL_STA_AFTER_END",
            "OM_IW_STATION_AFTER_BEGIN",
            *(iw_after or []),
            "OM_IW_STATION_AFTER_END",
            "OM_DMESG_SAFETY_BEGIN",
            "OM_DMESG_SAFETY_END",
            "",
        ]
    )


def collect_from_raw(raw: str) -> dict[str, object]:
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        raw_path = tmp_path / "tx12.raw.txt"
        out_path = tmp_path / "tx12.json"
        raw_path.write_text(raw, encoding="utf-8", newline="\n")
        proc = subprocess.run(
            [
                sys.executable,
                str(COLLECT_PY),
                "--input-raw",
                str(raw_path),
                "--seconds",
                "0",
                "--timeout",
                "10",
                "--output",
                str(out_path),
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    return json.loads(proc.stdout)


class Tx12MgmtTraceTests(unittest.TestCase):
    def test_ram_boot_wrapper_defaults_to_locked_plan_only(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BOOT)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMTX12_RAM_BOOT_PREFLIGHT_PASS=1 execute=0 flash=0", proc.stdout)
        self.assertIn("RAM-ONLY-W2-2G-PARITY-TX12-MGMT-TRACE-NO-FLASH", proc.stdout)
        self.assertIn("OPENMITRASTAR_TX12_RAM_BOOT_ONLY_NO_FLASH", proc.stdout)
        self.assertNotIn("OMTX12_RAM_BOOT_PASS=1", proc.stdout)

    def test_collector_wrapper_defaults_to_locked_plan_only(self) -> None:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(COLLECT_PS1)],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("OMTX12_MGMT_TRACE_COLLECTION_PLAN_PASS=1", proc.stdout)
        self.assertIn("OMTX12_MGMT_TRACE_COLLECTION_LOCKED_UNTIL_ACK=1", proc.stdout)
        self.assertIn("OPENMITRASTAR_COLLECT_TX12_MGMT_TRACE_READONLY", proc.stdout)
        self.assertNotIn("OMTX12_MGMT_TRACE_COLLECTED=1", proc.stdout)

    def test_execute_paths_require_exact_acks(self) -> None:
        boot_proc = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(BOOT), "-Execute"],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertNotEqual(boot_proc.returncode, 0)
        self.assertIn("requires exact -AckRamOnly", boot_proc.stdout + boot_proc.stderr)
        self.assertNotIn("OMTX12_RAM_BOOT_PASS=1", boot_proc.stdout)

        collect_proc = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(COLLECT_PS1),
                "-ExecuteCollection",
            ],
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=60,
            check=False,
        )
        self.assertNotEqual(collect_proc.returncode, 0)
        self.assertIn("requires exact -AckReadOnly", collect_proc.stdout + collect_proc.stderr)
        self.assertNotIn("OMTX12_MGMT_TRACE_COLLECTED=1", collect_proc.stdout)

    def test_parser_classifies_auth_only_without_assoc_request(self) -> None:
        report = collect_from_raw(
            raw_trace(
                [
                    "OMRTLMGMT stage=rx type=auth fc=00b0 len=30 da=ff sa=aa bssid=bb",
                    "OMRTLMGMT stage=tx type=auth fc=00b0 len=30 q=6 qsel=12 da=aa sa=bb bssid=bb",
                ]
            )
        )
        self.assertEqual(report["summary"]["decision"], "AUTH_RX_AND_TX_NO_ASSOC_REQ")
        self.assertEqual(report["summary"]["counts"]["rx:auth"], 1)
        self.assertEqual(report["summary"]["counts"]["tx:auth"], 1)
        self.assertFalse(report["flash"])
        self.assertFalse(report["mutations"])

    def test_parser_classifies_rx_auth_without_tx_response(self) -> None:
        report = collect_from_raw(
            raw_trace(
                ["OMRTLMGMT stage=rx type=auth fc=00b0 len=30 da=ff sa=aa bssid=bb"]
            )
        )
        self.assertEqual(report["summary"]["decision"], "AUTH_RX_NO_AUTH_TX")

    def test_parser_classifies_assoc_request_without_assoc_response(self) -> None:
        report = collect_from_raw(
            raw_trace(
                [
                    "OMRTLMGMT stage=rx type=auth fc=00b0 len=30 da=ff sa=aa bssid=bb",
                    "OMRTLMGMT stage=tx type=auth fc=00b0 len=30 q=6 qsel=12 da=aa sa=bb bssid=bb",
                    "OMRTLMGMT stage=rx type=assoc_req fc=0000 len=120 da=bb sa=aa bssid=bb",
                ]
            )
        )
        self.assertEqual(report["summary"]["decision"], "ASSOC_REQ_RX_NO_ASSOC_RESP_TX")
        self.assertEqual(report["summary"]["counts"]["rx:assoc_req"], 1)

    def test_parser_classifies_assoc_request_and_response(self) -> None:
        report = collect_from_raw(
            raw_trace(
                [
                    "OMRTLMGMT stage=rx type=assoc_req fc=0000 len=120 da=bb sa=aa bssid=bb",
                    "OMRTLMGMT stage=tx type=assoc_resp fc=0010 len=80 q=6 qsel=12 da=aa sa=bb bssid=bb",
                ]
            )
        )
        self.assertEqual(report["summary"]["decision"], "ASSOC_REQ_AND_RESP_OBSERVED")
        self.assertEqual(report["summary"]["counts"]["rx:assoc_req"], 1)
        self.assertEqual(report["summary"]["counts"]["tx:assoc_resp"], 1)

    def test_trace_delta_preserves_identical_appended_frames(self) -> None:
        line = "OMRTLMGMT stage=rx type=auth fc=00b0 len=30 da=ff sa=aa bssid=bb"
        report = collect_from_raw(raw_trace([line, line, line], [line, line]))
        self.assertEqual(report["trace_window"]["delta_mode"], "FULL_PREFIX")
        self.assertEqual(report["trace_window"]["new_events"], 1)
        self.assertEqual(report["summary"]["counts"]["rx:auth"], 1)

    def test_trace_delta_does_not_reuse_stale_events_when_nothing_changed(self) -> None:
        line = "OMRTLMGMT stage=rx type=auth fc=00b0 len=30 da=ff sa=aa bssid=bb"
        report = collect_from_raw(raw_trace([line], [line]))
        self.assertEqual(report["trace_window"]["new_events"], 0)
        self.assertEqual(report["summary"]["decision"], "NO_OMRTLMGMT_EVENTS")

    def test_report_uses_post_window_station_state(self) -> None:
        report = collect_from_raw(
            raw_trace(
                [],
                hostapd_after=[
                    "state=ENABLED",
                    "ssid[0]=OpenMitraStar-2G-DIAG",
                    "num_sta[0]=1",
                ],
                iw_after=[
                    "Station aa:bb:cc:dd:ee:ff (on wlan0)",
                    "\tauthorized:\tyes",
                    "\tauthenticated:\tyes",
                    "\tassociated:\tyes",
                ],
            )
        )
        self.assertEqual(report["hostapd"]["num_sta"], 1)
        self.assertTrue(report["station_state_after"]["kernel_authenticated"])
        self.assertTrue(report["station_state_after"]["kernel_associated"])
        self.assertTrue(report["station_state_after"]["kernel_authorized"])

    def test_crc_failed_false_subtypes_do_not_drive_decision(self) -> None:
        report = collect_from_raw(
            raw_trace(
                [
                    "OMRTLMGMT stage=rx type=assoc_req fc=bb00 len=912 crc=1 icv=0 da=aa sa=bb bssid=cc",
                    "OMRTLMGMT stage=rx type=probe_req fc=0040 len=168 crc=0 icv=0 da=ff sa=bb bssid=ff",
                    "OMRTLMGMT stage=tx type=probe_resp fc=0050 len=177 da=bb sa=cc bssid=cc",
                ]
            )
        )
        self.assertEqual(report["summary"]["decision"], "PROBE_EXCHANGE_NO_AUTH")
        self.assertEqual(report["trace_window"]["rejected_rx_error_events"], 1)
        self.assertNotIn("rx:assoc_req", report["summary"]["counts"])

    def test_invalid_80211_protocol_version_does_not_fake_assoc(self) -> None:
        report = collect_from_raw(
            raw_trace(
                [
                    "OMRTLMGMT stage=rx type=assoc_req fc=1002 len=292 crc=0 icv=0 da=aa sa=bb bssid=cc",
                    "OMRTLMGMT stage=rx type=probe_req fc=0040 len=168 crc=0 icv=0 da=ff sa=bb bssid=ff",
                    "OMRTLMGMT stage=tx type=probe_resp fc=0050 len=177 da=bb sa=cc bssid=cc",
                ]
            )
        )
        self.assertEqual(report["summary"]["decision"], "PROBE_EXCHANGE_NO_AUTH")
        self.assertEqual(report["trace_window"]["rejected_rx_error_events"], 1)

    def test_sources_have_no_flash_or_persistent_write_commands(self) -> None:
        combined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (BOOT, COLLECT_PS1, COLLECT_PY)
        ).lower()
        for forbidden in (
            "flash_erase",
            "mtd_debug",
            "nandwrite",
            "fw_setenv",
            "qtnboot",
            "bootm ",
            "/dev/mtd",
            "mtdblock",
        ):
            self.assertNotIn(forbidden, combined)


if __name__ == "__main__":
    unittest.main()
