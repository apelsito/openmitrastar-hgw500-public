from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import pytest

import run_f293_sequential_dual_radio_soak as soak


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f293_sequential_dual_radio_soak.py"


def cycle(index: int, status: str = "PASS") -> dict:
    return {
        "cycle": index,
        "status": status,
        "radio2": {"download_mbps": 28.0, "upload_mbps": 14.0, "rx_restarts": 0},
        "radio5": {"download_mbps": 31.0, "upload_mbps": 27.0, "disconnects": 0},
        "router": {"memavailable_kb": 22000, "fatal": 0},
    }


def test_summary_requires_every_cycle_to_pass() -> None:
    started = datetime.now(timezone.utc)
    passed = soak.summarize([cycle(1), cycle(2)], started, started + timedelta(hours=1))
    assert passed["status"] == "PASS"
    assert passed["cycles_completed"] == 2
    assert passed["median_mbps"]["radio2_down"] == 28.0
    failed = soak.summarize([cycle(1), cycle(2, "FAIL")], started, started + timedelta(hours=1))
    assert failed["status"] == "FAIL"


def test_runner_is_pinned_and_nonpersistent() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "OPENMITRASTAR_F293_SEQUENTIAL_DUAL_RADIO_SOAK",
        "lyoko-foundation-6.5.1-f293-emac-hw-rx-demand-device",
        "76f07b7d868fe878fe032bf302b2c75340498cd0186537bf75fc3ef9066ddc37",
        "run_aelita_2g_wpa2_speed_router_probe.py",
        "run_f293_5g_aelita_traffic.py",
        "checkpoint.json",
        "--resume",
        "load_completed_cycles",
        "refusing to overwrite existing soak evidence",
        "MOVISTAR-WIFI6-A348",
        '"simultaneous_dual_radio": False',
        '"mtd_writes": False',
    ):
        assert marker in source
    for forbidden in ("flash_erase", "mtd_debug", "nandwrite", "fw_setenv"):
        assert forbidden not in source


def test_dry_run_plan_is_machine_readable(tmp_path: Path) -> None:
    plan = {
        "schema": "openmitrastar.f293-sequential-dual-radio-soak-plan/v1",
        "mode": "dry-run",
        "duration_hours": 6.0,
        "simultaneous_dual_radio": False,
    }
    target = tmp_path / "plan.json"
    target.write_text(json.dumps(plan), encoding="ascii")
    assert json.loads(target.read_text(encoding="ascii"))["duration_hours"] == 6.0


def test_resume_accepts_only_contiguous_passed_cycles(tmp_path: Path) -> None:
    for index in (1, 2):
        directory = tmp_path / f"cycle-{index:03d}"
        directory.mkdir()
        (directory / "cycle.json").write_text(json.dumps(cycle(index)), encoding="ascii")
    loaded = soak.load_completed_cycles(tmp_path)
    assert [item["cycle"] for item in loaded] == [1, 2]

    (tmp_path / "cycle-002" / "cycle.json").write_text(json.dumps(cycle(2, "FAIL")), encoding="ascii")
    with pytest.raises(RuntimeError, match="failed cycle 2"):
        soak.load_completed_cycles(tmp_path)


def test_resume_started_at_requires_timezone(tmp_path: Path) -> None:
    (tmp_path / "checkpoint.json").write_text(
        json.dumps({"started_at": "2026-09-04T01:00:00+00:00"}), encoding="ascii"
    )
    assert soak.resume_started_at(tmp_path).tzinfo is not None
    (tmp_path / "checkpoint.json").write_text(
        json.dumps({"started_at": "2026-09-04T01:00:00"}), encoding="ascii"
    )
    with pytest.raises(RuntimeError, match="timezone"):
        soak.resume_started_at(tmp_path)
