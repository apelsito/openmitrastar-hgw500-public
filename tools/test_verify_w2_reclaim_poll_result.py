#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/verify_w2_reclaim_poll_result.py"


PASS_LOG = """\
rtl_pci: OMRTLTXBD stage=final-readback-active target=hgw500 q=1
rtl_pci: OMRTLQGUARD stage=stop event=1 q=1 queued=16 high=16 rp=121 wp=137
rtl_pci: OMRTLQGUARD stage=reclaim-arm q=1 queued=16 scheduled=1
rtl_pci: OMRTLQGUARD stage=reclaim-poll event=1 q=1 queued=16->11 stopped=1 rp=126 wp=137
rtl_pci: OMRTLQGUARD stage=wake event=1 q=1 queued=8 low=8 rp=129 wp=137
rtl_pci: OMRTLQGUARD stage=reclaim-poll event=2 q=1 queued=11->8 stopped=0 rp=129 wp=137
"""


def write_inputs(tmp_path: Path, guard: str = PASS_LOG, oracle_ok: bool = True) -> list[Path]:
    guard_path = tmp_path / "guard.log"
    client_path = tmp_path / "client.json"
    traffic_path = tmp_path / "traffic.json"
    oracle_path = tmp_path / "oracle.json"
    guard_path.write_text(guard, encoding="utf-8")
    client_path.write_text(
        json.dumps(
            {
                "schema": "openmitrastar.w2-2g-client-wait/v1",
                "association_observed": True,
                "authorization_observed": True,
                "last_sample": {"kernel_associated": 1, "kernel_authorized": 1},
            }
        ),
        encoding="utf-8",
    )
    traffic_path.write_text(
        json.dumps(
            {
                "schema": "openmitrastar.2g-live-traffic/v1",
                "association_observed": True,
                "authorization_observed": True,
                "wifi_tx_bytes_delta": 800_000,
                "wifi_rx_bytes_delta": 700_000,
                "fatal_markers_during_run": 0,
                "ssh_alive_all_samples": True,
            }
        ),
        encoding="utf-8",
    )
    oracle_path.write_text(
        json.dumps(
            {
                "schema": "openmitrastar.windows-wifi-oracle-roundtrip/v1",
                "connected": True,
                "wifi_ipv4": "192.168.1.63",
                "ping_pass": oracle_ok,
                "curl_output": (
                    "http=200;bytes=4194304;speed_Bps=900000;seconds=4.6"
                    if oracle_ok
                    else "http=000;bytes=0;speed_Bps=0;seconds=90"
                ),
                "error": None if oracle_ok else "timeout",
            }
        ),
        encoding="utf-8",
    )
    return [guard_path, client_path, traffic_path, oracle_path]


def run_verifier(paths: list[Path]) -> subprocess.CompletedProcess[str]:
    guard, client, traffic, oracle = paths
    return subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--guard-log",
            str(guard),
            "--client-json",
            str(client),
            "--traffic-json",
            str(traffic),
            "--oracle-json",
            str(oracle),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def test_complete_cycle_and_oracle_pass(tmp_path: Path) -> None:
    proc = run_verifier(write_inputs(tmp_path))
    assert proc.returncode == 0, proc.stdout + proc.stderr
    result = json.loads(proc.stdout)
    assert result["status"] == "PASS"
    assert result["candidate"]["pass"] is True
    assert result["guard"]["cycles"][0]["rp_progress"] is True
    assert result["guard"]["cycles"][0]["wake_at_or_below_low"] is True
    assert result["laptop_oracle"]["traffic_pass"] is True


def test_missing_wake_is_incomplete(tmp_path: Path) -> None:
    guard = PASS_LOG.replace(
        "rtl_pci: OMRTLQGUARD stage=wake event=1 q=1 queued=8 low=8 rp=129 wp=137\n",
        "",
    ).replace("stopped=0", "stopped=1")
    proc = run_verifier(write_inputs(tmp_path, guard=guard))
    assert proc.returncode == 2
    result = json.loads(proc.stdout)
    assert result["status"] == "INCOMPLETE"
    assert "cycle_1.wake_missing" in result["incomplete"]


def test_oracle_failure_rejects_driver_only_success(tmp_path: Path) -> None:
    proc = run_verifier(write_inputs(tmp_path, oracle_ok=False))
    assert proc.returncode == 1
    result = json.loads(proc.stdout)
    assert result["status"] == "FAIL"
    assert "laptop_oracle_traffic_failed" in result["failures"]


def test_missing_required_input_is_incomplete(tmp_path: Path) -> None:
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--guard-log",
            str(tmp_path / "missing.log"),
            "--oracle-json",
            str(tmp_path / "missing.json"),
        ],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert proc.returncode == 2
    assert json.loads(proc.stdout)["status"] == "INCOMPLETE"

