from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

import pytest

import consolidate_f301_soak_chain as consolidate


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/consolidate_f301_soak_chain.py"
FIRMWARE = "lyoko-foundation-6.6.1-f301-f300-capability-truth-device"
SHA256 = "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262"


def write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def plan() -> dict[str, object]:
    return {
        "schema": consolidate.PLAN_SCHEMA,
        "mode": "execute",
        "required_firmware": FIRMWARE,
        "candidate_file": "f301.bin",
        "candidate_sha256": SHA256,
        "target_duration_seconds": 21600.0,
        "soak_seconds_per_band": 120,
        "cycle_pause_seconds": 30,
    }


def cycle(index: int, down: float | None = None) -> dict[str, object]:
    return {
        "schema": consolidate.CYCLE_SCHEMA,
        "cycle": index,
        "status": "PASS",
        "radio2": {
            "download_mbps": down if down is not None else 20.0 + index,
            "upload_mbps": 14.0,
            "rx_restarts": 1 if index == 3 else 0,
        },
        "radio5": {"download_mbps": 32.0, "upload_mbps": 25.0, "disconnects": 0},
        "router": {"memavailable_kb": 22000 - index, "fatal": 0},
    }


def state(status: str, cycles: int, elapsed: float, **extra: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema": consolidate.CHECKPOINT_SCHEMA,
        "status": status,
        "cycles_completed": cycles,
        "active_elapsed_seconds": elapsed,
        "target_duration_seconds": 21600.0,
        "started_at": "2026-09-04T12:00:00+00:00",
    }
    payload.update(extra)
    return payload


def result(status: str, cycles: int, elapsed: float, **extra: object) -> dict[str, object]:
    payload = state(status, cycles, elapsed, **extra)
    payload["schema"] = "openmitrastar.f301-sequential-dual-radio-soak/v1"
    return payload


def write_source(
    directory: Path,
    cycle_count: int,
    elapsed: float,
    *,
    terminal_failure: tuple[int, str, str] | None = None,
    checkpoint_status: str = "IN_PROGRESS",
    seed: dict[str, object] | None = None,
) -> None:
    write_json(directory / "plan.json", plan())
    for index in range(1, cycle_count + 1):
        write_json(directory / f"cycle-{index:03d}" / "cycle.json", cycle(index))
    if terminal_failure:
        failed_cycle, phase, error = terminal_failure
        failure = result(
            "FAIL",
            cycle_count,
            elapsed,
            error=error,
            error_type="CampaignFailure",
            failure_cycle=failed_cycle,
            failure_phase=phase,
        )
        write_json(directory / "result.json", failure)
        write_json(directory / "failure.json", failure)
        write_json(directory / "checkpoint.json", state("FAIL", cycle_count, elapsed))
        write_json(
            directory / f"cycle-{failed_cycle:03d}" / "failure.json",
            {"status": "FAIL", "cycle": failed_cycle, "phase": phase, "error": error},
        )
    else:
        write_json(directory / "checkpoint.json", state(checkpoint_status, cycle_count, elapsed))
    if seed is not None:
        write_json(directory / "seed.json", seed)


def seed(source: Path, cycles: int, elapsed: float, error: str, reason: str) -> dict[str, object]:
    return {
        "schema": consolidate.SEED_SCHEMA,
        "source": str(source.resolve()),
        "source_status": "FAIL",
        "source_error": error,
        "imported_cycles": cycles,
        "imported_active_elapsed_seconds": elapsed,
        "reason": reason,
    }


def chain(tmp_path: Path) -> tuple[Path, Path, Path]:
    original = tmp_path / "original"
    resume1 = tmp_path / "resume1"
    resume2 = tmp_path / "resume2"
    error1 = "cycle 5 5 GHz failed with rc=1"
    error2 = "cycle 8 2.4 GHz failed with rc=124"
    write_source(original, 4, 2714.453, terminal_failure=(5, "radio5", error1))
    write_source(
        resume1,
        7,
        5045.953,
        terminal_failure=(8, "radio2", error2),
        seed=seed(original, 4, 2714.453, error1, "transient SSH timeout; retry logic added"),
    )
    write_source(
        resume2,
        8,
        5649.063,
        seed=seed(resume1, 7, 5045.953, error2, "outer collector timeout expanded"),
    )
    return original, resume1, resume2


def test_consolidates_real_shape_without_double_counting(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    summary = consolidate.build_summary(list(sources))
    assert summary["status"] == "IN_PROGRESS"
    assert summary["cycles_completed"] == 8
    assert summary["active_elapsed_seconds"] == 5649.063
    assert [item["segment_elapsed_seconds"] for item in summary["elapsed_segments"]] == [
        2714.453,
        2331.5,
        603.11,
    ]
    assert len(summary["failures"]["harness"]) == 2
    assert summary["failures"]["hardware"] == []
    assert summary["failures"]["unclassified"] == []
    assert [item["cycle"] for item in summary["cycles"]] == list(range(1, 9))
    assert summary["cycles_deduplicated"] == 11


def test_rejects_plan_mismatch(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    changed = plan()
    changed["soak_seconds_per_band"] = 180
    write_json(sources[2] / "plan.json", changed)
    with pytest.raises(consolidate.ConsolidationError, match="plan mismatch"):
        consolidate.build_summary(list(sources))


def test_rejects_broken_seed_source(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    broken = json.loads((sources[1] / "seed.json").read_text(encoding="utf-8"))
    broken["source"] = str(sources[2].resolve())
    write_json(sources[1] / "seed.json", broken)
    with pytest.raises(consolidate.ConsolidationError, match="seed does not reference"):
        consolidate.build_summary(list(sources))


def test_rejects_divergent_duplicate_cycle(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    write_json(sources[2] / "cycle-003" / "cycle.json", cycle(3, down=99.0))
    with pytest.raises(consolidate.ConsolidationError, match="inherited cycle 3 differs"):
        consolidate.build_summary(list(sources))


def test_rejects_non_contiguous_pass_cycles(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    (sources[2] / "cycle-006" / "cycle.json").unlink()
    with pytest.raises(consolidate.ConsolidationError, match="not contiguous"):
        consolidate.build_summary(list(sources))


def test_rejects_imported_elapsed_mismatch(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    broken = json.loads((sources[2] / "seed.json").read_text(encoding="utf-8"))
    broken["imported_active_elapsed_seconds"] = 9999
    write_json(sources[2] / "seed.json", broken)
    with pytest.raises(consolidate.ConsolidationError, match="imported elapsed mismatch"):
        consolidate.build_summary(list(sources))


def test_requires_original_and_resume1_to_be_failed(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    (sources[0] / "result.json").unlink()
    (sources[0] / "failure.json").unlink()
    write_json(sources[0] / "checkpoint.json", state("PAUSED", 4, 2714.453))
    with pytest.raises(consolidate.ConsolidationError, match="every source before the final segment"):
        consolidate.build_summary(list(sources))


def test_records_hardware_failure_separately(tmp_path: Path) -> None:
    original, resume1, resume2 = chain(tmp_path)
    error = "router fatal markers increased during cycle 9"
    write_source(
        resume2,
        8,
        6200.0,
        terminal_failure=(9, "router", error),
        seed=seed(resume1, 7, 5045.953, "cycle 8 2.4 GHz failed with rc=124", "outer collector timeout expanded"),
    )
    summary = consolidate.build_summary([original, resume1, resume2])
    assert summary["status"] == "FAIL"
    assert len(summary["failures"]["harness"]) == 2
    assert len(summary["failures"]["hardware"]) == 1


def test_final_pass_chain_is_pass_only_after_target(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    final = result("PASS", 8, 21600.0)
    write_json(sources[2] / "result.json", final)
    write_json(sources[2] / "checkpoint.json", state("PASS", 8, 21600.0))
    summary = consolidate.build_summary(list(sources))
    assert summary["status"] == "PASS"
    assert summary["duration_reached"] is True


def test_accepts_arbitrary_resume_chain_and_classifies_three_harness_failures(tmp_path: Path) -> None:
    original, resume1, resume2 = chain(tmp_path)
    error3 = "cycle 9 2.4 GHz failed because router runtime PSK SSH read timed out"
    write_source(
        resume2,
        8,
        6000.0,
        terminal_failure=(9, "radio2", error3),
        seed=seed(resume1, 7, 5045.953, "cycle 8 2.4 GHz failed with rc=124", "outer collector timeout expanded"),
    )
    resume3 = tmp_path / "resume3"
    write_source(
        resume3,
        9,
        21600.0,
        seed=seed(resume2, 8, 6000.0, error3, "runtime PSK SSH retry added"),
    )
    write_json(resume3 / "result.json", result("PASS", 9, 21600.0))
    write_json(resume3 / "checkpoint.json", state("PASS", 9, 21600.0))

    summary = consolidate.build_summary([original, resume1, resume2, resume3])
    assert summary["status"] == "PASS"
    assert summary["cycles_completed"] == 9
    assert summary["duration_reached"] is True
    assert len(summary["source_chain"]) == 4
    assert len(summary["failures"]["harness"]) == 3
    assert summary["failures"]["hardware"] == []


def test_cli_writes_atomic_json_and_markdown_without_touching_sources(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    before = {
        str(path): path.read_bytes()
        for source in sources
        for path in source.rglob("*.json")
    }
    output = tmp_path / "consolidated"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--original-dir",
            str(sources[0]),
            "--resume1-dir",
            str(sources[1]),
            "--resume2-dir",
            str(sources[2]),
            "--output-dir",
            str(output),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 0, proc.stderr
    persisted = json.loads((output / "summary.json").read_text(encoding="ascii"))
    assert persisted["status"] == "IN_PROGRESS"
    assert "Harness failures: 2" in (output / "summary.md").read_text(encoding="ascii")
    assert not list(output.glob(".*.tmp"))
    assert all(Path(path).read_bytes() == data for path, data in before.items())


def test_cli_rejects_output_inside_source(tmp_path: Path) -> None:
    sources = chain(tmp_path)
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--original-dir",
            str(sources[0]),
            "--resume1-dir",
            str(sources[1]),
            "--resume2-dir",
            str(sources[2]),
            "--output-dir",
            str(sources[2] / "derived"),
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    assert proc.returncode == 1
    assert "must not be inside" in proc.stderr
    assert not (sources[2] / "derived").exists()


def test_tool_has_no_hardware_or_mutation_path() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in (
        "subprocess",
        "socket",
        "paramiko",
        "COM3",
        "tftp",
        "flash_erase",
        "mtd_debug",
        "/dev/mtd",
    ):
        assert forbidden not in source
