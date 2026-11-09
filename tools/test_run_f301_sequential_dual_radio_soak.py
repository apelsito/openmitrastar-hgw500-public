from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

import run_f301_sequential_dual_radio_soak as soak


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f301_sequential_dual_radio_soak.py"


def cycle(index: int, status: str = "PASS") -> dict[str, object]:
    return {
        "schema": "openmitrastar.f301-sequential-dual-radio-cycle/v1",
        "cycle": index,
        "status": status,
        "radio2": {"download_mbps": 28.0, "upload_mbps": 14.0, "rx_restarts": 0},
        "radio5": {"download_mbps": 31.0, "upload_mbps": 27.0, "disconnects": 0},
        "router": {"memavailable_kb": 22000, "fatal": 0},
    }


def args(**overrides: object) -> argparse.Namespace:
    values: dict[str, object] = {
        "execute": True,
        "router_host": "192.168.1.90",
        "oracle_host": "192.168.1.63",
        "oracle_user": "AELITA",
        "controller_url": "http://192.168.1.43:8008/speed.bin",
        "duration_hours": 6.0,
        "soak_seconds": 120,
        "cycle_pause_seconds": 30,
        "snapshot_attempts": 5,
        "snapshot_retry_seconds": 3.0,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def plan(namespace: argparse.Namespace | None = None) -> dict[str, object]:
    namespace = namespace or args()
    return soak.immutable_plan(namespace, Path("candidate.bin"), soak.EXPECTED_SHA256)


def write_resume_state(
    directory: Path,
    cycles: list[dict[str, object]],
    *,
    status: str = "PAUSED",
    active_elapsed: float = 300.0,
    namespace: argparse.Namespace | None = None,
) -> None:
    namespace = namespace or args()
    directory.mkdir(parents=True, exist_ok=True)
    soak.atomic_write_json(directory / "plan.json", plan(namespace))
    started = datetime(2026, 9, 4, 8, 0, tzinfo=timezone.utc)
    checkpoint = soak.checkpoint_payload(
        cycles, started, active_elapsed, namespace.duration_hours * 3600, status
    )
    soak.atomic_write_json(directory / "checkpoint.json", checkpoint)
    for item in cycles:
        cycle_dir = directory / f"cycle-{int(item['cycle']):03d}"
        soak.atomic_write_json(cycle_dir / "cycle.json", item)


def test_summary_pass_requires_elapsed_target_and_passed_cycle() -> None:
    started = datetime.now(timezone.utc)
    result = soak.summarize([cycle(1)], started, started + timedelta(hours=6), 21600, 21600)
    assert result["status"] == "PASS"
    assert result["duration_reached"] is True
    no_cycle = soak.summarize([], started, started + timedelta(hours=6), 21600, 21600)
    assert no_cycle["status"] == "FAIL"


def test_summary_is_paused_when_max_cycles_stops_before_duration() -> None:
    started = datetime.now(timezone.utc)
    result = soak.summarize([cycle(1)], started, started + timedelta(minutes=8), 480, 21600)
    assert result["status"] == "PAUSED"
    assert result["duration_reached"] is False
    assert result["all_cycles_passed"] is True


def test_summary_failure_has_precedence() -> None:
    started = datetime.now(timezone.utc)
    result = soak.summarize(
        [cycle(1), cycle(2, "FAIL")], started, started + timedelta(hours=6), 21600, 21600
    )
    assert result["status"] == "FAIL"


def test_atomic_write_replaces_complete_json_and_leaves_no_temporary(tmp_path: Path) -> None:
    target = tmp_path / "checkpoint.json"
    soak.atomic_write_json(target, {"value": 1})
    soak.atomic_write_json(target, {"value": 2})
    assert json.loads(target.read_text(encoding="ascii")) == {"value": 2}
    assert not list(tmp_path.glob(".*.tmp"))


def test_load_completed_cycles_requires_contiguous_passed_evidence(tmp_path: Path) -> None:
    for index in (1, 2):
        soak.atomic_write_json(tmp_path / f"cycle-{index:03d}" / "cycle.json", cycle(index))
    assert [item["cycle"] for item in soak.load_completed_cycles(tmp_path)] == [1, 2]
    (tmp_path / "cycle-002" / "cycle.json").unlink()
    with pytest.raises(RuntimeError, match="incomplete cycle 2"):
        soak.load_completed_cycles(tmp_path)


def test_load_completed_cycles_rejects_gaps_and_failures(tmp_path: Path) -> None:
    soak.atomic_write_json(tmp_path / "cycle-001" / "cycle.json", cycle(1))
    soak.atomic_write_json(tmp_path / "cycle-003" / "cycle.json", cycle(3))
    with pytest.raises(RuntimeError, match="not contiguous"):
        soak.load_completed_cycles(tmp_path)
    (tmp_path / "cycle-003").rename(tmp_path / "cycle-002")
    soak.atomic_write_json(tmp_path / "cycle-002" / "cycle.json", cycle(2, "FAIL"))
    with pytest.raises(RuntimeError, match="failed cycle 2"):
        soak.load_completed_cycles(tmp_path)


def test_snapshot_retry_succeeds_and_records_attempt() -> None:
    calls = 0
    sleeps: list[float] = []

    def flaky(_host: str) -> dict[str, object]:
        nonlocal calls
        calls += 1
        if calls < 3:
            raise RuntimeError("transient")
        return {"firmware": soak.EXPECTED_VERSION}

    result = soak.router_snapshot_with_retry(
        "router", attempts=5, delay_seconds=0.25, snapshot=flaky, sleeper=sleeps.append
    )
    assert result["snapshot_attempt"] == 3
    assert sleeps == [0.25, 0.25]


def test_snapshot_retry_preserves_all_errors_on_exhaustion() -> None:
    with pytest.raises(RuntimeError, match=r"attempt 1:.*attempt 2:"):
        soak.router_snapshot_with_retry(
            "router",
            attempts=2,
            delay_seconds=0,
            snapshot=lambda _host: (_ for _ in ()).throw(RuntimeError("offline")),
            sleeper=lambda _seconds: None,
        )


def test_resume_accepts_only_exact_paused_contract(tmp_path: Path) -> None:
    namespace = args()
    write_resume_state(tmp_path, [cycle(1)], namespace=namespace)
    checkpoint, cycles, started, elapsed = soak.validate_resume(tmp_path, plan(namespace))
    assert checkpoint["status"] == "PAUSED"
    assert len(cycles) == 1
    assert started.tzinfo is not None
    assert elapsed == 300.0


@pytest.mark.parametrize(
    "field,value",
    [
        ("required_firmware", "wrong"),
        ("candidate_sha256", "0" * 64),
        ("duration_hours", 7.0),
        ("soak_seconds_per_band", 180),
        ("radio5_profile", "f300"),
        ("known_hosts_file", "known_hosts.f300"),
    ],
)
def test_resume_rejects_contract_mismatch(tmp_path: Path, field: str, value: object) -> None:
    namespace = args()
    write_resume_state(tmp_path, [cycle(1)], namespace=namespace)
    changed = plan(namespace)
    changed[field] = value
    with pytest.raises(RuntimeError, match="resume plan mismatch"):
        soak.validate_resume(tmp_path, changed)


@pytest.mark.parametrize("status", ["PASS", "FAIL"])
def test_resume_rejects_terminal_checkpoint(tmp_path: Path, status: str) -> None:
    namespace = args()
    write_resume_state(tmp_path, [cycle(1)], status=status, namespace=namespace)
    with pytest.raises(RuntimeError, match="terminal checkpoint"):
        soak.validate_resume(tmp_path, plan(namespace))


def test_resume_rejects_terminal_evidence(tmp_path: Path) -> None:
    namespace = args()
    write_resume_state(tmp_path, [cycle(1)], namespace=namespace)
    soak.atomic_write_json(tmp_path / "result.json", {"status": "FAIL"})
    with pytest.raises(RuntimeError, match="terminal evidence"):
        soak.validate_resume(tmp_path, plan(namespace))


def test_resume_rejects_inconsistent_active_duration(tmp_path: Path) -> None:
    namespace = args()
    write_resume_state(tmp_path, [cycle(1)], active_elapsed=21600, namespace=namespace)
    with pytest.raises(RuntimeError, match="active duration"):
        soak.validate_resume(tmp_path, plan(namespace))


def test_commands_pin_f301_known_hosts_profile_and_ack(tmp_path: Path) -> None:
    namespace = args()
    command2 = soak.radio2_command(namespace, tmp_path / "radio2")
    command5 = soak.radio5_command(namespace, tmp_path / "radio5")
    assert str(soak.KNOWN_HOSTS) in command2
    assert "--profile" in command5 and command5[command5.index("--profile") + 1] == "f301"
    assert "--ack" in command5 and command5[command5.index("--ack") + 1] == soak.RADIO5_ACK


def test_failure_payload_preserves_phase_and_is_terminal() -> None:
    started = datetime.now(timezone.utc)
    result = soak.failure_payload(
        RuntimeError("radio failed"), "radio5", 3, [cycle(1), cycle(2)], started, 100, 21600
    )
    assert result["status"] == "FAIL"
    assert result["failure_phase"] == "radio5"
    assert result["failure_cycle"] == 3
    assert result["evidence_preserved"] is True


def test_runner_is_exactly_pinned_and_contains_no_persistent_write_tools() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        soak.ACK,
        soak.RADIO5_ACK,
        soak.EXPECTED_VERSION,
        soak.EXPECTED_SHA256,
        "known_hosts.f301",
        "run_aelita_2g_wpa2_speed_router_probe.py",
        "run_f293_5g_aelita_traffic.py",
        '"--profile", "f301"',
        "atomic_write_json",
        '"PAUSED"',
        "evidence_preserved",
        "args.soak_seconds + 900",
    ):
        assert marker in source
    for forbidden in ("flash_erase", "mtd_debug", "nandwrite", "fw_setenv", "/dev/mtd"):
        assert forbidden not in source
    radio5_source = (ROOT / "tools/run_f293_5g_aelita_traffic.py").read_text(encoding="utf-8")
    assert "read_runtime_psk_with_retry" in radio5_source
    assert "subprocess.TimeoutExpired" in radio5_source
    radio2_source = (ROOT / "tools/run_aelita_2g_wpa2_runtime_psk_once.py").read_text(encoding="utf-8")
    assert "_read_router_runtime_psk_once" in radio2_source
    assert "router runtime PSK read failed after" in radio2_source
    assert "subprocess.TimeoutExpired" in radio2_source


def test_real_dry_run_is_local_only_and_machine_readable(tmp_path: Path) -> None:
    output = tmp_path / "dry-run"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--duration-hours", "0.25",
            "--soak-seconds", "120",
            "--output-dir", str(output),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    result = json.loads(proc.stdout)
    persisted = json.loads((output / "plan.json").read_text(encoding="ascii"))
    assert result == persisted
    assert result["mode"] == "dry-run"
    assert result["required_firmware"] == soak.EXPECTED_VERSION
    assert result["candidate_sha256"] == soak.EXPECTED_SHA256
    assert result["local_preflight_pass"] is True
    assert result["hardware_preflight"] == "DEFERRED_TO_EXECUTE"
    assert result["hardware_actions_performed"] is False
    assert not (output / "checkpoint.json").exists()


def test_dry_run_refuses_to_overwrite_evidence(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    (output / "evidence.txt").write_text("keep", encoding="ascii")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--output-dir", str(output)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode != 0
    assert "refusing to overwrite" in proc.stderr
    assert (output / "evidence.txt").read_text(encoding="ascii") == "keep"


def install_fake_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    build = tmp_path / "build"
    build.mkdir()
    candidate = build / "f301.bin"
    candidate.write_bytes(b"offline-fixture")
    known_hosts = build / "known_hosts.f301"
    known_hosts.write_text("fixture\n", encoding="ascii")
    manifest = build / "manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "artifacts": {
                    "webformat": {
                        "file": candidate.name,
                        "sha256": soak.EXPECTED_SHA256,
                    }
                }
            }
        ),
        encoding="ascii",
    )
    monkeypatch.setattr(soak, "BUILD", build)
    monkeypatch.setattr(soak, "KNOWN_HOSTS", known_hosts)
    monkeypatch.setattr(soak, "MANIFEST", manifest)
    monkeypatch.setattr(soak, "sha256", lambda _path: soak.EXPECTED_SHA256)
    monkeypatch.setattr(soak, "tcp_open", lambda _host: True)
    monkeypatch.setattr(
        soak.hardware_lock,
        "acquire_physical_lock",
        lambda owner, evidence_dir: soak.hardware_lock.HardwareLock(
            owner, evidence_dir, tmp_path / "physical-radio.lock"
        ),
    )
    monkeypatch.setattr(soak.time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(
        soak,
        "router_snapshot_with_retry",
        lambda *_args, **_kwargs: {
            "firmware": soak.EXPECTED_VERSION,
            "memavailable_kb": 22000,
            "uptime_seconds": 1000.0,
            "fatal": 0,
            "radio2": {"lifecycle": "ap-ready"},
            "radio5": {"lifecycle": "traffic-ready"},
            "snapshot_attempt": 1,
        },
    )

    def fake_run_logged(command: list[str], log: Path, _timeout: int) -> int:
        output = Path(command[command.index("--output-dir") + 1])
        output.mkdir(parents=True, exist_ok=True)
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("fixture\n", encoding="ascii")
        if "run_aelita_2g_wpa2_speed_router_probe.py" in command[1]:
            (output / "summary.json").write_text(
                json.dumps(
                    {
                        "controller_download": {"pass": True, "speed_Bps": 3_500_000},
                        "controller_upload": {"pass": True, "speed_Bps": 1_800_000},
                        "router_health_gate": {"pass": True},
                        "execution_error": None,
                        "emac_stats_delta": {"rx_restart_total": 0},
                    }
                ),
                encoding="utf-8",
            )
        else:
            (output / "result-fixture.json").write_text(
                json.dumps(
                    {
                        "status": "PASS",
                        "download": {"pass": True, "mbps": 30.0},
                        "upload": {"pass": True, "mbps": 25.0},
                        "soak": {"disconnects": 0},
                        "router": {"status": "PASS"},
                    }
                ),
                encoding="utf-8",
            )
        return 0

    monkeypatch.setattr(soak, "run_logged", fake_run_logged)
    monkeypatch.setattr(
        soak.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0),
    )


def test_max_cycles_pauses_and_resume_continues_next_cycle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_fake_execution(monkeypatch, tmp_path)
    output = tmp_path / "campaign"
    common = [
        "--execute",
        "--ack", soak.ACK,
        "--duration-hours", "0.25",
        "--max-cycles", "1",
        "--output-dir", str(output),
    ]
    assert soak.main(common) == 0
    first = json.loads((output / "checkpoint.json").read_text(encoding="ascii"))
    assert first["status"] == "PAUSED"
    assert first["cycles_completed"] == 1
    assert first["duration_reached"] is False
    assert (output / "pause-001.json").is_file()
    assert not (output / "result.json").exists()

    assert soak.main(common + ["--resume"]) == 0
    second = json.loads((output / "checkpoint.json").read_text(encoding="ascii"))
    assert second["status"] == "PAUSED"
    assert second["cycles_completed"] == 2
    assert (output / "cycle-002" / "cycle.json").is_file()
    assert (output / "pause-002.json").is_file()


def test_execution_failure_keeps_logs_and_terminal_evidence(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    install_fake_execution(monkeypatch, tmp_path)
    monkeypatch.setattr(soak, "run_logged", lambda _command, log, _timeout: (log.parent.mkdir(parents=True, exist_ok=True), log.write_text("failed\n", encoding="ascii"), 9)[2])
    output = tmp_path / "failed-campaign"
    rc = soak.main(
        [
            "--execute",
            "--ack", soak.ACK,
            "--duration-hours", "0.25",
            "--max-cycles", "1",
            "--output-dir", str(output),
        ]
    )
    assert rc == 1
    failure = json.loads((output / "failure.json").read_text(encoding="ascii"))
    checkpoint = json.loads((output / "checkpoint.json").read_text(encoding="ascii"))
    assert failure["status"] == "FAIL"
    assert failure["failure_phase"] == "radio2"
    assert failure["evidence_preserved"] is True
    assert checkpoint["status"] == "FAIL"
    assert (output / "cycle-001" / "radio2.log").read_text(encoding="ascii") == "failed\n"
    assert (output / "cycle-001" / "failure.json").is_file()
