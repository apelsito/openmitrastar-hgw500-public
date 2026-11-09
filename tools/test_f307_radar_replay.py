#!/usr/bin/env python3

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "tools" / "f307_radar_replay.py"
FIXTURES = ROOT / "outputs" / "kernel-port" / "f307-radar-replay-20260904" / "fixtures"


def load_module():
    spec = importlib.util.spec_from_file_location("f307_radar_replay", MODULE_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


REPLAY = load_module()


def read_fixture(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="ascii"))


def test_es_region_must_normalize_to_eu() -> None:
    session = read_fixture("synthetic-es-standard-cac-pass.json")
    session["regulatory"]["radar_region"] = "es"
    try:
        REPLAY.replay_session(session)
    except ValueError as exc:
        assert "normalized" in str(exc)
    else:
        raise AssertionError("ES region was accepted without EU normalization")


def test_standard_cac_fixture_passes_and_blocks_early_tx() -> None:
    result = REPLAY.replay_session(read_fixture("synthetic-es-standard-cac-pass.json"))
    assert result["status"] == "PASS"
    assert result["initial_channel_plan"]["cac_required_ms"] == 70_000
    probes = [event for event in result["timeline"] if event["type"] == "tx_probe"]
    assert probes[0]["details"]["actual_allowed"] is False
    assert probes[1]["details"]["actual_allowed"] is True
    assert result["physical_rf_detection_proven"] is False


def test_weather_block_requires_600_seconds() -> None:
    result = REPLAY.replay_session(read_fixture("synthetic-es-weather-cac-pass.json"))
    assert result["status"] == "PASS"
    plan = result["initial_channel_plan"]
    assert plan["occupied_20mhz_channels"] == [116, 120, 124, 128]
    assert plan["weather_radar_intersection"] is True
    assert plan["cac_required_ms"] == 600_000


def test_incomplete_132_80_block_fails_closed() -> None:
    session = read_fixture("synthetic-es-weather-cac-pass.json")
    session["regulatory"]["channel"] = 132
    try:
        REPLAY.replay_session(session)
    except ValueError as exc:
        assert "144" in str(exc)
    else:
        raise AssertionError("incomplete 132/136/140/144 block was accepted")


def test_oracle_callback_aborts_cac_registers_nop_and_requires_evacuation() -> None:
    result = REPLAY.replay_session(read_fixture("synthetic-es-radar-during-cac.json"))
    assert result["status"] == "PASS"
    assert result["observed"]["radar_callback_count"] == 1
    assert result["observed"]["radar_channels"] == [100]
    assert result["observed"]["nop_registered_channels"] == [100]
    poll = next(event for event in result["timeline"] if event["type"] == "poll")
    assert poll["details"]["vector_result"]["classification_algorithm"] == "NOT_IMPLEMENTED"
    assert poll["state"]["cac_active"] is False
    assert poll["state"]["evacuation_required"] is True
    assert poll["state"]["tx_allowed"] is False


def test_nop_is_active_until_exact_1800_second_boundary() -> None:
    result = REPLAY.replay_session(read_fixture("synthetic-es-radar-during-cac.json"))
    probes = [event for event in result["timeline"] if event["type"] == "nop_probe"]
    assert probes[0]["details"]["actual_active"] is True
    assert probes[1]["details"]["actual_active"] is False


def test_rejected_oracle_candidate_does_not_create_radar_event() -> None:
    session = read_fixture("synthetic-es-standard-cac-pass.json")
    poll = next(event for event in session["events"] if event["type"] == "poll")
    poll["vector"]["oracle"] = {
        "lsr_enabled": True,
        "lsr_hit": True,
        "post_filter_reject_input": True,
        "callback_registered": True,
    }
    poll["vector"]["expected"] = {
        "pulse_count": 1,
        "classes": ["lsr"],
        "mark_radar_callback_fired": False,
    }
    result = REPLAY.replay_session(session)
    assert result["status"] == "PASS"
    assert result["observed"]["radar_callback_count"] == 0


def test_cac_completion_one_millisecond_early_fails() -> None:
    session = read_fixture("synthetic-es-standard-cac-pass.json")
    complete = next(event for event in session["events"] if event["type"] == "cac_complete")
    complete["at_ms"] -= 1
    result = REPLAY.replay_session(session)
    assert result["status"] == "FAIL"
    assert "event[5]:cac-completed-too-early" in result["violations"]


def test_sensitive_fixture_fields_are_rejected() -> None:
    session = read_fixture("synthetic-es-standard-cac-pass.json")
    session["provenance"]["client_mac"] = "not-retained"
    try:
        REPLAY.replay_session(session)
    except ValueError as exc:
        assert "sensitive field" in str(exc)
    else:
        raise AssertionError("sensitive field was accepted")


def test_replay_is_byte_deterministic() -> None:
    session = read_fixture("synthetic-es-radar-during-cac.json")
    first = json.dumps(REPLAY.replay_session(copy.deepcopy(session)), sort_keys=True)
    second = json.dumps(REPLAY.replay_session(copy.deepcopy(session)), sort_keys=True)
    assert first == second


def test_cli_writes_result_without_hardware_references(tmp_path: Path) -> None:
    output = tmp_path / "result.json"
    proc = subprocess.run(
        [sys.executable, str(MODULE_PATH), str(FIXTURES / "synthetic-es-standard-cac-pass.json"), "--output", str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=60,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout
    result = json.loads(output.read_text(encoding="ascii"))
    assert result["status"] == "PASS"
    assert result["f302_module_or_hardware_executed"] is False
    source = MODULE_PATH.read_text(encoding="utf-8").lower()
    for forbidden in ("com3", "192.168.1.90", "spi_flash", "/dev/mtd", "paramiko", "subprocess.run(['ssh"):
        assert forbidden not in source
