from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/f310_soak_consolidate.py"


def load_module():
    spec = importlib.util.spec_from_file_location("f310_soak_consolidate_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def cycle(module, index: int) -> dict[str, object]:
    return {
        "schema": module.CYCLE_SCHEMA,
        "cycle": index,
        "status": "PASS",
        "radio2": {"download_mbps": 28.0 + index, "upload_mbps": 15.0, "rx_restarts": 0},
        "radio5": {"download_mbps": 33.0, "upload_mbps": 25.0, "disconnects": 0},
        "router": {"memavailable_kb": 22000, "fatal": 0},
    }


def plan(module, target: float, seed_source: str | None = None) -> dict[str, object]:
    return {
        "schema": module.PLAN_SCHEMA,
        "mode": "execute",
        "required_firmware": module.EXPECTED_VERSION,
        "candidate_file": "f310.bin",
        "candidate_sha256": module.EXPECTED_SHA256,
        "router_host": "192.168.1.90",
        "oracle_host": "192.168.1.63",
        "oracle_user": "AELITA",
        "controller_url": "http://192.168.1.43:8008/speed.bin",
        "duration_hours": target / 3600,
        "target_duration_seconds": target,
        "soak_seconds_per_band": 120,
        "cycle_pause_seconds": 30,
        "snapshot_attempts": 5,
        "snapshot_retry_seconds": 3.0,
        "radio2_runner": "tools/run_aelita_2g_wpa2_speed_router_probe_ssh_v2.py",
        "radio5_runner": "tools/run_f293_5g_aelita_traffic_ssh_v2.py",
        "radio5_profile": "f310",
        "radio5_ack": "OPENMITRASTAR_F310_5G_AELITA_TRAFFIC",
        "restore_ssid": "MOVISTAR-WIFI6-A348",
        "aelita_known_hosts_file": "known_hosts",
        "aelita_host_key_mode": "pinned",
        "aelita_fingerprint_enforced": False,
        "aelita_ssh_connect_timeout": 8,
        "seed_source": seed_source,
    }


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="ascii")


def write_source(
    module,
    path: Path,
    *,
    target: float,
    elapsed: float,
    status: str,
    cycles: list[dict[str, object]],
    seed: dict[str, object] | None = None,
) -> None:
    path.mkdir(parents=True)
    write_json(path / "plan.json", plan(module, target, str(seed.get("source")) if seed else None))
    state = {
        "schema": module.CHECKPOINT_SCHEMA,
        "status": status,
        "started_at": "2026-09-04T00:00:00+00:00",
        "active_elapsed_seconds": elapsed,
        "target_duration_seconds": target,
        "duration_reached": elapsed >= target,
        "cycles_completed": len(cycles),
    }
    write_json(path / "checkpoint.json", state)
    if status in {"PASS", "FAIL"}:
        write_json(path / "result.json", state)
    if seed:
        write_json(path / "seed.json", seed)
    for item in cycles:
        write_json(path / f"cycle-{int(item['cycle']):03d}/cycle.json", item)


def seed(module, source: Path, *, status: str, cycles: int, elapsed: float) -> dict[str, object]:
    return {
        "schema": module.SEED_SCHEMA,
        "source": str(source.resolve()),
        "source_status": status,
        "source_error": None,
        "imported_cycles": cycles,
        "imported_active_elapsed_seconds": elapsed,
        "reason": "continue certification",
    }


def test_single_paused_source_never_becomes_pass(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "source"
    write_source(
        module,
        source,
        target=86400.0,
        elapsed=86399.0,
        status="PAUSED",
        cycles=[cycle(module, 1)],
    )
    summary = module.build_summary([source])
    assert summary["status"] == "PAUSED"
    assert summary["duration_reached"] is False


def test_seed_chain_deduplicates_prefix_within_24h_target(tmp_path: Path) -> None:
    module = load_module()
    first = tmp_path / "first"
    second = tmp_path / "second"
    one = cycle(module, 1)
    two = cycle(module, 2)
    write_source(module, first, target=86400.0, elapsed=21600.0, status="PAUSED", cycles=[one])
    write_source(
        module,
        second,
        target=86400.0,
        elapsed=30000.0,
        status="PAUSED",
        cycles=[one, two],
        seed=seed(module, first, status="PAUSED", cycles=1, elapsed=21600.0),
    )
    summary = module.build_summary([first, second])
    assert summary["status"] == "PAUSED"
    assert summary["cycles_completed"] == 2
    assert summary["cycles_deduplicated"] == 1
    assert summary["active_elapsed_seconds"] == 30000.0
    assert summary["target_duration_seconds"] == 86400.0
    assert summary["integrity"]["seed_lineage"] is True


def test_pass_requires_duration_and_exact_terminal_pass(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "source"
    write_source(
        module,
        source,
        target=86400.0,
        elapsed=86400.0,
        status="PASS",
        cycles=[cycle(module, 1)],
    )
    assert module.build_summary([source])["status"] == "PASS"


def test_forged_early_pass_is_invalid(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "source"
    write_source(
        module,
        source,
        target=86400.0,
        elapsed=1000.0,
        status="PASS",
        cycles=[cycle(module, 1)],
    )
    assert module.build_summary([source])["status"] == "INVALID_FINAL"


def test_divergent_duplicate_cycle_is_rejected(tmp_path: Path) -> None:
    module = load_module()
    first = tmp_path / "first"
    second = tmp_path / "second"
    one = cycle(module, 1)
    changed = cycle(module, 1)
    changed["radio2"]["download_mbps"] = 1.0
    write_source(module, first, target=86400.0, elapsed=1000.0, status="PAUSED", cycles=[one])
    write_source(
        module,
        second,
        target=86400.0,
        elapsed=2000.0,
        status="PAUSED",
        cycles=[changed],
        seed=seed(module, first, status="PAUSED", cycles=1, elapsed=1000.0),
    )
    with pytest.raises(module.ConsolidationError, match="changed inherited cycle"):
        module.build_summary([first, second])


def test_output_is_atomic_and_contains_no_hardware_claim(tmp_path: Path) -> None:
    module = load_module()
    source = tmp_path / "source"
    output = tmp_path / "summary"
    write_source(module, source, target=86400.0, elapsed=1000.0, status="PAUSED", cycles=[cycle(module, 1)])
    assert module.main(["--source-dir", str(source), "--output-dir", str(output)]) == 0
    summary = json.loads((output / "summary.json").read_text(encoding="ascii"))
    assert summary["hardware_actions_performed"] is False
    assert summary["persistent_writes"] is False
    assert summary["flash"] is False
    assert summary["mtd_writes"] is False
    assert not list(output.glob("*.tmp"))


def test_source_has_no_flash_or_remote_execution_primitives() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for forbidden in ("subprocess", "flash_erase", "mtd_debug", "nandwrite", "/dev/mtd"):
        assert forbidden not in source
