from __future__ import annotations

import argparse
import base64
from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/f306_soak_runner.py"


def load_runner():
    spec = importlib.util.spec_from_file_location("f306_soak_runner_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def namespace(tmp_path: Path, **overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "execute": False,
        "ack": "",
        "router_host": "192.168.1.90",
        "oracle_host": "192.168.1.63",
        "oracle_user": "AELITA",
        "controller_url": "http://192.168.1.43:8008/speed.bin",
        "duration_hours": 6.0,
        "soak_seconds": 120,
        "cycle_pause_seconds": 30,
        "max_cycles": 0,
        "snapshot_attempts": 5,
        "snapshot_retry_seconds": 3.0,
        "resume": False,
        "output_dir": tmp_path / "output",
        "seed_from": None,
        "seed_reason": "test continuation",
        "aelita_known_hosts": tmp_path / "known_hosts",
        "aelita_host_key_mode": "pinned",
        "aelita_host_key_sha256": "",
        "aelita_ssh_connect_timeout": 8,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def cycle(runner, index: int = 1) -> dict[str, object]:
    return {
        "schema": runner.CYCLE_SCHEMA,
        "cycle": index,
        "status": "PASS",
        "started_at": "2026-09-04T00:00:00+00:00",
        "finished_at": "2026-09-04T00:10:00+00:00",
        "elapsed_seconds": 600.0,
        "radio2": {"download_mbps": 30.0, "upload_mbps": 15.0, "router_health": True, "rx_restarts": 0},
        "radio5": {"download_mbps": 35.0, "upload_mbps": 25.0, "disconnects": 0},
        "router": {"memavailable_kb": 22000, "uptime_seconds": 1000.0, "fatal": 0, "snapshot_attempt": 1},
    }


def write_source(runner, path: Path, *, duration_hours: float, elapsed: float, status: str) -> None:
    path.mkdir(parents=True)
    args = namespace(path, duration_hours=duration_hours, execute=True, output_dir=path)
    plan = runner.immutable_plan(args, Path("candidate.bin"), runner.EXPECTED_SHA256)
    runner.base.atomic_write_json(path / "plan.json", plan)
    item = cycle(runner)
    (path / "cycle-001").mkdir()
    runner.base.atomic_write_json(path / "cycle-001/cycle.json", item)
    started = datetime(2026, 9, 4, tzinfo=timezone.utc)
    checkpoint = runner.checkpoint_payload(
        [item], started, elapsed, duration_hours * 3600, status
    )
    runner.base.atomic_write_json(path / "checkpoint.json", checkpoint)
    if status in {"PASS", "FAIL"}:
        result = runner.summarize(
            [item], started, started, elapsed, duration_hours * 3600, status
        )
        runner.base.atomic_write_json(path / "result.json", result)


def test_contract_and_commands_pin_exact_f306(tmp_path: Path) -> None:
    runner = load_runner()
    args = namespace(tmp_path)
    plan = runner.immutable_plan(args, Path("candidate.bin"), runner.EXPECTED_SHA256)
    command2 = runner.radio2_command(args, tmp_path / "radio2")
    command5 = runner.radio5_command(args, tmp_path / "radio5")
    assert plan["required_firmware"] == runner.EXPECTED_VERSION
    assert plan["candidate_sha256"] == runner.EXPECTED_SHA256
    assert plan["schema"] == runner.PLAN_SCHEMA
    assert command2[1].endswith("run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py")
    assert command5[1].endswith("run_f293_5g_aelita_traffic_ssh_v2.py")
    assert command5[command5.index("--profile") + 1] == "f306"
    assert command5[command5.index("--ack") + 1] == runner.RADIO5_ACK


def test_duration_is_limited_to_six_or_twenty_four_hours() -> None:
    runner = load_runner()
    assert runner.parser().parse_args(["--duration-hours", "6"]).duration_hours == 6.0
    assert runner.parser().parse_args(["--duration-hours", "24"]).duration_hours == 24.0
    with pytest.raises(SystemExit):
        runner.parser().parse_args(["--duration-hours", "1"])


def test_summary_never_passes_before_target() -> None:
    runner = load_runner()
    item = cycle(runner)
    started = datetime(2026, 9, 4, tzinfo=timezone.utc)
    early = runner.summarize([item], started, started, 21599.0, 21600.0)
    complete = runner.summarize([item], started, started, 21600.0, 21600.0)
    assert early["status"] == "PAUSED"
    assert early["duration_reached"] is False
    assert complete["status"] == "PASS"
    assert complete["duration_reached"] is True


def test_seed_promotes_completed_six_hour_lineage_into_twenty_four_hour_run(tmp_path: Path) -> None:
    runner = load_runner()
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    write_source(runner, source, duration_hours=6.0, elapsed=21600.0, status="PASS")
    args = namespace(
        tmp_path,
        execute=True,
        duration_hours=24.0,
        output_dir=destination,
        seed_from=source,
        aelita_known_hosts=source / "known_hosts",
    )
    plan = runner.immutable_plan(args, Path("candidate.bin"), runner.EXPECTED_SHA256)
    seed = runner.prepare_seed(destination, source, plan, "extend 6 h evidence to 24 h")
    checkpoint = json.loads((destination / "checkpoint.json").read_text(encoding="ascii"))
    assert seed["imported_cycles"] == 1
    assert seed["imported_active_elapsed_seconds"] == 21600.0
    assert checkpoint["status"] == "PAUSED"
    assert checkpoint["active_elapsed_seconds"] == 21600.0
    assert checkpoint["target_duration_seconds"] == 86400.0
    assert (destination / "cycle-001/cycle.json").is_file()
    assert not (destination / "result.json").exists()


def test_seed_ignores_incomplete_tail_but_rejects_later_pass(tmp_path: Path) -> None:
    runner = load_runner()
    source = tmp_path / "source"
    write_source(runner, source, duration_hours=6.0, elapsed=1200.0, status="PAUSED")
    (source / "cycle-002").mkdir()
    runner.base.atomic_write_json(source / "cycle-002/state.json", {"status": "IN_PROGRESS"})
    assert len(runner.load_seed_cycles(source)) == 1
    (source / "cycle-003").mkdir()
    runner.base.atomic_write_json(source / "cycle-003/cycle.json", cycle(runner, 3))
    with pytest.raises(RuntimeError, match="after an incomplete cycle"):
        runner.load_seed_cycles(source)


def test_dry_run_is_local_only_and_preserves_known_host(tmp_path: Path) -> None:
    known_hosts = tmp_path / "known_hosts"
    encoded = base64.b64encode(b"offline-aelita-host-key").decode("ascii")
    original = f"192.168.1.63 ssh-ed25519 {encoded}\n"
    known_hosts.write_text(original, encoding="ascii")
    output = tmp_path / "dry-run"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--duration-hours", "6",
            "--soak-seconds", "120",
            "--aelita-host-key-mode", "pinned",
            "--aelita-known-hosts", str(known_hosts),
            "--output-dir", str(output),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    plan = json.loads(proc.stdout)
    assert plan["mode"] == "dry-run"
    assert plan["local_preflight_pass"] is True
    assert plan["hardware_actions_performed"] is False
    assert plan["flash"] is False
    assert plan["mtd_writes"] is False
    assert known_hosts.read_text(encoding="ascii") == original


def test_source_has_no_flash_or_mtd_primitives() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "nandwrite", "fw_setenv", "/dev/mtd"):
        assert forbidden not in source
