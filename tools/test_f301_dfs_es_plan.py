#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/f301_dfs_es_plan.py"
EXTRACTED_ROOTFS = ROOT / ".codex_tmp/f301-dfs-audit/rootfs"

spec = importlib.util.spec_from_file_location("f301_dfs_es_plan", SCRIPT)
assert spec and spec.loader
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


def test_immediate_80mhz_block_is_non_dfs() -> None:
    result = plan.classify_channel(44, 80)
    assert result["valid"] is True
    assert result["occupied_20mhz_channels"] == [36, 40, 44, 48]
    assert result["channel_class"] == "immediate-non-dfs"
    assert result["cac_seconds_minimum"] == 0


def test_standard_dfs_80mhz_block_uses_oem_70_second_minimum() -> None:
    result = plan.classify_channel(100, 80)
    assert result["occupied_20mhz_channels"] == [100, 104, 108, 112]
    assert result["channel_class"] == "dfs-standard"
    assert result["cac_seconds_minimum"] == 70
    assert result["non_occupancy_seconds"] == 1800


def test_weather_classification_uses_complete_occupied_block() -> None:
    result = plan.classify_channel(116, 80)
    assert result["occupied_20mhz_channels"] == [116, 120, 124, 128]
    assert result["weather_radar_intersection"] is True
    assert result["channel_class"] == "dfs-weather-radar"
    assert result["cac_seconds_minimum"] == 600


def test_40mhz_weather_pair_requires_secondary_readback() -> None:
    result = plan.classify_channel(116, 40)
    assert result["occupied_20mhz_channels"] == [116, 120]
    assert result["secondary_channel_readback_required"] is True
    assert result["cac_seconds_minimum"] == 600


def test_incomplete_high_80mhz_block_fails_closed() -> None:
    result = plan.classify_channel(136, 80)
    assert result["valid"] is False
    assert result["channel_class"] == "invalid"
    assert "INCOMPLETE_80MHZ_BLOCK_REQUIRES_CHANNEL_144" in result["reasons"]


def test_channel_140_at_40mhz_fails_closed() -> None:
    result = plan.classify_channel(140, 40)
    assert result["valid"] is False
    assert "INCOMPLETE_40MHZ_BLOCK_OR_SECONDARY_UNKNOWN" in result["reasons"]


def test_exact_f301_local_audit_passes_and_dfs_remains_blocked() -> None:
    assert EXTRACTED_ROOTFS.is_dir(), "run local F301 rootfs extraction before this integration test"
    result = plan.build_result(EXTRACTED_ROOTFS, 100, 20)
    assert result["audit"]["status"] == "PASS", result["audit"]["failed_checks"]
    assert result["audit"]["support_classification"]["dfs_cac_radar_nop"].startswith("BLOCKED")
    assert result["selected_gate"]["eligibility"] == "BLOCKED_DFS_RADAR_BACKEND_UNAVAILABLE"
    assert result["selected_gate"]["dfs_gate"]["status"] == "BLOCKED"
    assert result["audit"]["checks"]["qdrv_contains_fail_closed_marker"] is True
    assert result["audit"]["checks"]["physical_driver_dfs_region_not_ready"] is True
    assert len(result["audit"]["known_contract_gaps"]) == 5
    assert all(value in (False, 0) for value in result["hardware_actions"].values())


def test_non_dfs_gate_is_implementable_but_not_executed() -> None:
    audit = {
        "status": "PASS",
        "support_classification": {"dfs_cac_radar_nop": "BLOCKED_NATIVE_RADAR_BACKEND_ABSENT"},
    }
    result = plan.physical_gate_plan(44, 80, audit)
    assert result["eligibility"] == "READY_FOR_CONTROLLED_NON_DFS_PHYSICAL_GATE"
    assert result["hardware_execution_in_this_tool"] is False
    assert result["immediate_non_dfs_gate"]["status"] == "IMPLEMENTABLE_WITH_EXISTING_F301_BACKEND"


def test_cli_writes_machine_readable_plan_without_hardware() -> None:
    assert EXTRACTED_ROOTFS.is_dir()
    with tempfile.TemporaryDirectory() as temp:
        output = Path(temp) / "plan.json"
        run = subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--rootfs-tree", str(EXTRACTED_ROOTFS),
                "--channel", "116",
                "--bandwidth", "80",
                "--output", str(output),
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        assert run.returncode == 0, run.stderr
        result = json.loads(output.read_text(encoding="utf-8"))
        assert result["mode"] == "LOCAL_READ_ONLY_PLAN"
        assert result["selected_gate"]["target"]["cac_seconds_minimum"] == 600
        assert result["hardware_actions"]["mtd_writes"] == 0


def test_require_dfs_ready_returns_blocked_exit_code() -> None:
    run = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--rootfs-tree", str(EXTRACTED_ROOTFS),
            "--channel", "100",
            "--bandwidth", "20",
            "--require-dfs-ready",
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert run.returncode == 3, run.stderr
