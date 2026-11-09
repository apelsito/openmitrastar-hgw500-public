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
GATE = ROOT / "tools/qtn_w3_dfs_es_gate.py"
CURRENT = ROOT / "work/mission-state/w3-offline/W3_DFS_ES_80_CURRENT_EVIDENCE.json"
REGDB = ROOT / "work/hgw500-rootfs-live/squashfs-root/etc/qtn_regulatory_db.bin"

spec = importlib.util.spec_from_file_location("dfs_gate", GATE)
assert spec and spec.loader
dfs_gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dfs_gate)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DfsEsGateTests(unittest.TestCase):
    def evidence(self, root: Path) -> dict[str, object]:
        radar = root / "radar-native.ko"
        radar.write_bytes(b"ELF native radar linux510\0" + b"R" * 128)
        log = root / "uart.log"
        log.write_text("\n".join(dfs_gate.REQUIRED_RUNTIME_MARKERS) + "\n",
                       encoding="utf-8")
        return {
            "schema": "openmitrastar-w3-dfs-es-evidence-v1",
            "target": {
                "compatible": dfs_gate.TARGET_COMPATIBLE,
                "country": "ES", "region": "es", "primary_channel": 112,
                "center_channel": 106, "bandwidth_mhz": 80,
                "subchannels": [100, 104, 108, 112],
            },
            "regdb": {
                "path": str(REGDB), "sha256": digest(REGDB),
                "version_status": "PASS", "version_output": "regulatory DB: v1.0",
                "reg_is_eu": 1, "set_regulatory_region": "es",
                "option_802_11h": 1, "is_channel_dfs": 1,
                "is_weather_channel": 0, "radar_bw_mhz": 80,
                "min_cac_seconds": 70,
                "regulatory_channels": [36, 40, 44, 48, 100, 104, 108, 112],
                "dfs_channels_80mhz": [100, 104, 108, 112],
            },
            "radar": {
                "backend": "native-linux510", "module_path": str(radar),
                "module_sha256": digest(radar),
                "exported_symbols": sorted(dfs_gate.REQUIRED_RADAR_SYMBOLS),
                "module_loaded": True, "start_pass": True, "dfs_rqmt_code": 1,
                "callbacks_registered": 3, "channel": 112, "bandwidth_mhz": 80,
                "status_before_cac": True, "status_during_cac": True,
                "status_after_cac": True,
            },
            "cac": {
                "started_monotonic_ms": 1000, "completed_monotonic_ms": 71000,
                "channel": 112, "bandwidth_mhz": 80,
                "status_before": 0, "status_during": 1, "status_after": 0,
                "tx_blocked_during": True, "cac_done": True,
                "cac_in_progress": False, "radar_detected": False,
                "non_occupancy_clear": [100, 104, 108, 112],
                "radar_monitoring_after_cac": True,
                "ap_beaconing_after_cac": True,
            },
            "runtime_log_path": str(log), "runtime_log_sha256": digest(log),
        }

    def test_current_compat_state_fails_closed(self):
        evidence = json.loads(CURRENT.read_text(encoding="utf-8"))
        result = dfs_gate.evaluate(evidence)
        self.assertFalse(result["pass"])
        self.assertFalse(result["rf_allowed"])
        self.assertFalse(result["led_5ghz_allowed"])
        self.assertIn("RADAR_FAIL_CLOSED_COMPAT_STILL_LINKED", result["reasons"])

    def test_complete_evidence_passes(self):
        with tempfile.TemporaryDirectory() as temp:
            result = dfs_gate.evaluate(self.evidence(Path(temp)))
        self.assertTrue(result["pass"], result["reasons"])
        self.assertTrue(result["rf_allowed"])
        self.assertEqual(result["state"], "AP_TX_ENABLED")

    def test_each_safety_pillar_is_mandatory(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            baseline = self.evidence(root)
            mutations = (
                ("regdb", "reg_is_eu", 0, "REGDB_ES_NOT_EU"),
                ("radar", "status_during_cac", False,
                 "RADAR_NOT_CONTINUOUS_DURING_CAC"),
                ("cac", "tx_blocked_during", False,
                 "TRANSMIT_NOT_PROVEN_BLOCKED_DURING_CAC"),
                ("cac", "radar_detected", True,
                 "RADAR_DETECTED_CHANNEL_MUST_ENTER_NOP"),
            )
            for section, key, value, expected in mutations:
                with self.subTest(section=section, key=key):
                    candidate = json.loads(json.dumps(baseline))
                    candidate[section][key] = value
                    result = dfs_gate.evaluate(candidate)
                    self.assertFalse(result["pass"])
                    self.assertIn(expected, result["reasons"])

    def test_cac_must_run_for_oem_minimum(self):
        with tempfile.TemporaryDirectory() as temp:
            evidence = self.evidence(Path(temp))
            evidence["cac"]["completed_monotonic_ms"] = 70999
            result = dfs_gate.evaluate(evidence)
        self.assertIn("CAC_DURATION_BELOW_70_SECONDS", result["reasons"])

    def test_cli_current_state_is_machine_readable_fail_closed(self):
        run = subprocess.run(
            [sys.executable, str(GATE), "--allow-fail"], cwd=ROOT,
            capture_output=True, text=True,
        )
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertIn("W3_DFS_ES_80_GATE=FAIL", run.stdout)
        self.assertIn("W3_DFS_RF_ALLOWED=0", run.stdout)
        self.assertIn("W3_DFS_LED_5GHZ_ALLOWED=0", run.stdout)


if __name__ == "__main__":
    unittest.main()
