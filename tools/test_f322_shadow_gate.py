"""No-network fixtures for F322 baseline, temporal evidence and refusal paths."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

import f322_shadow_gate as gate
import run_f322_shadow_acquisition_gate as runner


FILES = {"/synthetic/file" + str(i): str(i) * 64 for i in range(9)}
BOOT_ID = "11111111-2222-3333-4444-555555555555"


def sample(elapsed=0, polls=0, armed=False):
    status = {**gate.STATUS_FIXED, **{key: 0 for key in gate.STATUS_VARIABLE}}
    status["callback_refusals"] = 2
    if armed:
        status.update(shadow_arm=1, configured=1, polling=1, poll_runs=polls, poll_empty=polls,
                      config_attempts=1, mmio_writes=1500)
    return {"elapsed_seconds": elapsed, "boot_id": BOOT_ID, "version": gate.VERSION,
        "status_before": deepcopy(status), "status_after": deepcopy(status),
        "snapshot": {**gate.SNAPSHOT_FIXED, "sequence": polls, "registers_stable": int(armed),
                     "raw_count": 0, "processed_count": 0, "zc_count": 0},
        "runtime": {"channel": 36, "bandwidth": 80, "region": "ES", "doth": True,
                    "uptime_seconds": 1000 + int(elapsed), "backend_ready": False, "dfs_tx_authorized": None,
                    "cac_state": "not-required", "availability": 2},
        "fatal_count": 0, "management_ready": True, "installed_file_hashes": FILES.copy()}


def temporal():
    rows = [sample(i * 2, i * 40 + 1, True) for i in range(31)]
    cleanup = [deepcopy(rows[-1]), deepcopy(rows[-1])]
    for i, row in enumerate(cleanup):
        row["elapsed_seconds"] = 61 + i
        for status in (row["status_before"], row["status_after"]):
            status["shadow_arm"] = status["polling"] = 0
    return rows, cleanup


def text_observation(row):
    runtime = {"ok": True, "available": True, "observation_only": True,
        "schema": "lyoko.radio.dfs-observation/v1", "mode": "shadow", "current_channel": 36, "channel": 36,
        "bandwidth_mhz": 80, "region": "ES", "current_channel_dfs": False, "backend_ready": False,
        "dfs_tx_authorized": None, "tx": {"authorized": None}, "detector": {"running": False},
        "controls": {"apply": False, "bypass": False}, "doth": True,
        "cac": {"state": "not-required"}, "channel_availability": {"code": 2}, "observed_at_uptime_seconds": 1000}
    values = {
        "IDENTITY": {"version": gate.VERSION, "build": gate.BUILD_ID, "kernel": gate.KERNEL,
                     "boot_id": BOOT_ID, "fatal_count": 0, "boot_ready": 1, "radio2_ready": 1,
                     "radio5_ready": 1, "bridge_ready": 1},
        "FILES": "".join(f"{sha}  {path}\n" for path, sha in FILES.items()),
        "STATUS_BEFORE": row["status_before"], "SNAPSHOT": row["snapshot"],
        "RUNTIME": json.dumps(runtime) + "\n", "STATUS_AFTER": row["status_after"],
    }
    output = ""
    for name, value in values.items():
        content = "".join(f"{key}={item}\n" for key, item in value.items()) if isinstance(value, dict) else value
        output += f"OMF322_{name}_BEGIN\n" + content + f"OMF322_{name}_END\n"
    return output


def test_exact_unarmed_two_sample_baseline():
    result = gate.validate_baseline([sample(), sample(1)])
    assert result["status"] == "PASS_F322_BASELINE_UNARMED"
    assert result["temporal_acquisition"] == gate.BLOCKER
    assert not result["hardware_capture_restoration_proven"]


@pytest.mark.parametrize("field,value", [("shadow_arm", 1), ("configured", 1), ("polling", 1),
    ("poll_runs", 1), ("mmio_writes", 1), ("config_attempts", 1), ("callback_invocations", 1),
    ("backend_ready", 1), ("dfs_enable", 1), ("mmio_write_refusals", 1), ("map_failures", 1)])
def test_baseline_refuses_partial_arm_authority_or_prior_side_effects(field, value):
    rows = [sample(), sample(1)]
    rows[-1]["status_after"][field] = value
    with pytest.raises(ValueError):
        gate.validate_baseline(rows)


def test_framed_parser_retains_only_sanitized_typed_fields():
    row = gate.parse_observation(text_observation(sample()), FILES, 0)
    assert row["status_before"]["poll_runs"] == 0
    assert row["runtime"]["dfs_tx_authorized"] is None
    assert "pulse=" not in json.dumps(row)


@pytest.mark.parametrize("old,new", [
    ("poll_runs=0\n", "poll_runs=0\npoll_runs=1\n"),
    ("mmio_writes=0\n", ""),
    ("backend_ready=0", "backend_ready=true"),
    ("sequence=0", "sequence=-1"),
    ("OMF322_FILES_END", "unknown=secret\nOMF322_FILES_END"),
    ("OMF322_SNAPSHOT_END", "pulse=0 start=123 power_code=999\nOMF322_SNAPSHOT_END"),
    ('"region": "ES"', '"region": "US"'),
    ('"channel": 36', '"channel": 52'),
    ('"doth": true', '"doth": null'),
])
def test_incomplete_duplicate_or_unsafe_observations_fail_closed(old, new):
    text = text_observation(sample())
    assert old in text
    with pytest.raises(ValueError):
        gate.parse_observation(text.replace(old, new), FILES, 0)


def test_unframed_secret_is_rejected_without_reproducing_it():
    with pytest.raises(ValueError) as caught:
        gate.parse_observation(text_observation(sample()) + "private-synthetic-secret\n", FILES, 0)
    assert "private-synthetic-secret" not in str(caught.value)


def test_duplicate_json_authority_field_is_rejected():
    text = text_observation(sample()).replace('"backend_ready": false', '"backend_ready": true, "backend_ready": false')
    with pytest.raises(ValueError, match="duplicate-json-key"):
        gate.parse_observation(text, FILES, 0)


def test_nonatomic_single_publication_lag_is_valid():
    row = sample(0, 101, True)
    row["snapshot"]["sequence"] = 100
    row["status_after"]["poll_runs"] = 102
    gate.validate_observation(row)


@pytest.mark.parametrize("sequence", [99, 103])
def test_snapshot_outside_bracketing_counters_is_rejected(sequence):
    row = sample(0, 101, True)
    row["snapshot"]["sequence"] = sequence
    row["status_after"]["poll_runs"] = 102
    with pytest.raises(ValueError, match="snapshot-outside-status-bracket"):
        gate.validate_observation(row)


def test_60_seconds_of_empty_polls_does_not_prove_rf_or_restoration():
    result = gate.temporal_fixture(*temporal())
    assert result["status"] == "PASS_SIMULATED_TEMPORAL_POLLING_ONLY"
    assert result["simulation"] and result["software_polling_stopped"]
    assert not result["hardware_restoration_proven"] and not result["physical_rf_detection_proven"]
    assert result["physical_arming"] == gate.BLOCKER


@pytest.mark.parametrize("mutation", ["stalled", "short", "gap", "reset", "fatal", "network", "channel", "width",
    "country", "authority", "callback", "mmio", "configuration", "unstable", "raw-limit", "reboot"])
def test_temporal_fixture_does_not_turn_partial_or_regressed_evidence_green(mutation):
    rows, cleanup = temporal()
    row = rows[15]
    if mutation == "stalled":
        row["status_before"]["poll_runs"] = row["status_after"]["poll_runs"] = rows[14]["status_after"]["poll_runs"]
        row["snapshot"]["sequence"] = rows[14]["snapshot"]["sequence"]
    elif mutation == "short": rows = rows[:-1]
    elif mutation == "gap": row["elapsed_seconds"] += 1.5
    elif mutation == "reset": row["status_after"]["poll_empty"] = 0
    elif mutation == "fatal": row["fatal_count"] = 1
    elif mutation == "network": row["management_ready"] = False
    elif mutation == "channel": row["runtime"]["channel"] = 52
    elif mutation == "width": row["runtime"]["bandwidth"] = 40
    elif mutation == "country": row["runtime"]["region"] = "US"
    elif mutation == "authority": row["status_after"]["backend_ready"] = 1
    elif mutation == "callback": row["status_after"]["callback_invocations"] = 1
    elif mutation == "mmio": row["status_after"]["mmio_writes"] += 1
    elif mutation == "configuration": row["status_after"]["config_attempts"] = 2
    elif mutation == "unstable": row["snapshot"]["registers_stable"] = 0
    elif mutation == "raw-limit": row["snapshot"]["raw_count"] = 19
    elif mutation == "reboot": row["boot_id"] = "99999999-2222-3333-4444-555555555555"
    with pytest.raises(ValueError): gate.temporal_fixture(rows, cleanup)


@pytest.mark.parametrize("mutation", ["missing", "still-armed", "still-polling", "counts-move", "fake-restored", "wrong-order", "reset"])
def test_cleanup_must_be_complete_and_cannot_claim_register_restoration(mutation):
    rows, cleanup = temporal()
    if mutation == "missing": cleanup.pop()
    elif mutation == "still-armed": cleanup[-1]["status_after"]["shadow_arm"] = 1
    elif mutation == "still-polling": cleanup[-1]["status_after"]["polling"] = 1
    elif mutation == "counts-move": cleanup[-1]["status_after"]["poll_runs"] += 1
    elif mutation == "fake-restored": cleanup[-1]["status_after"]["configured"] = 0
    elif mutation == "wrong-order": cleanup[0]["elapsed_seconds"] = 59
    elif mutation == "reset":
        for row in cleanup:
            row["status_before"]["poll_runs"] = row["status_after"]["poll_runs"] = row["snapshot"]["sequence"] = 1
    with pytest.raises(ValueError): gate.temporal_fixture(rows, cleanup)


def test_dry_run_has_no_network_or_baseline(monkeypatch, capsys):
    monkeypatch.setattr(gate, "sealed_inputs", lambda: FILES)
    monkeypatch.setattr(runner, "baseline", lambda *_: pytest.fail("network attempted"))
    assert runner.main([]) == 0
    assert json.loads(capsys.readouterr().out)["hardware_actions_performed"] is False


def test_every_execute_arm_path_refuses_before_network_even_with_exact_ack(monkeypatch, capsys):
    monkeypatch.setattr(gate, "sealed_inputs", lambda: FILES)
    monkeypatch.setattr(runner, "baseline", lambda *_: pytest.fail("network attempted"))
    assert runner.main(["--execute", "--ack", gate.ACK, "--installation-result", "synthetic.json",
                        "--installation-result-sha256", "a" * 64]) == 2
    report = json.loads(capsys.readouterr().out)
    assert report["status"] == gate.BLOCKER and report["shadow_arm_writes"] == 0


def test_observation_script_has_no_mutation_or_raw_pulse_output():
    script = runner.observation_script(FILES).decode("ascii")
    for forbidden in ("shadow_arm", "set_mode", "set_region", "set_chan", "init_txpower", "insmod", "rmmod", "reboot", "/dev/mtd"):
        assert forbidden not in script
    assert "pulse" not in script
    assert "\r" not in script and not script.encode().startswith(b"\xef\xbb\xbf")


def test_ssh_is_pinned_bounded_and_does_not_print_failed_private_output(monkeypatch):
    monkeypatch.setattr(gate, "pinned", lambda *_: b"synthetic host pin")
    calls = []
    def execute(argv, **kw):
        calls.append((argv, kw))
        return subprocess.CompletedProcess(argv, 1, b"private-synthetic-secret", b"other-private-synthetic")
    with pytest.raises(ValueError) as caught:
        runner.ssh_observation(FILES, 0, runner=execute, monotonic=lambda: 1)
    assert "private" not in str(caught.value)
    argv, options = calls[0]
    assert "StrictHostKeyChecking=yes" in argv and "BatchMode=yes" in argv
    assert options["timeout"] == 25 and type(options["input"]) is bytes


def test_baseline_failure_never_attempts_arm_cleanup_or_second_read():
    calls = []
    def observe(*_):
        calls.append("read")
        row = sample(0, 1, True)
        return row
    with pytest.raises(ValueError): runner.baseline(FILES, observe=observe, monotonic=lambda: 0, sleep=lambda _: None)
    assert calls == ["read"]


def test_exact_offline_candidate_remains_unmodified():
    before = (gate.DEVICE / "manifest.json").read_bytes()
    files = gate.sealed_inputs()
    assert len(files) == 9
    assert before == (gate.DEVICE / "manifest.json").read_bytes()
