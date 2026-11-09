"""Offline regression tests against the preserved execution-time evidence.

These tests only read the known cycle and candidate. Corruptions are in memory
or pytest temporary directories; no router or historical output is changed.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

import pytest

import reconcile_f321_postboot_acceptance as gate

FRESH = gate.ROOT / "outputs/postflash/f321-independent-20260911T091309Z"
HISTORICAL = gate.ROOT / "outputs/postflash/f321-independent-20260908T0010"


@pytest.fixture
def traces():
    directory = gate.CYCLE / "writer"
    return ((directory / "bootbase-flash-uart.log").read_text(encoding="utf-8"),
            (directory / "backend.log").read_text(encoding="utf-8"))


def test_real_write_evidence_survives_the_known_linux_parser_false_positive(traces):
    observed = gate.verify_uart(*traces)
    assert observed["candidate_prefix_compared_bytes"] == 5337088
    assert observed["full_slot_crc32_observed"] == "6ed8e483"
    assert observed["full_slot_sha256_observed"] is None
    assert observed["boot_environment"]["writes"] == 0
    assert observed["uart_network_ready"] == "NOT_OBSERVED_BEFORE_PARSER_ABORT"


@pytest.mark.parametrize("old,new", [
    ("spi_flash erase 0x007e0000", "spi_flash erase 0x00040000"),
    ("spi_flash write 0x007e0000", "spi_flash write 0x00f80000"),
    ("size=5337088 ret_size=5337088", "size=5337088 ret_size=1"),
    ("Total of 5337088 bytes were the same", "Total of 0 bytes were the same"),
    ("84000000: 6ed8e483", "84000000: d6b13baa"),
    ("84000000: aa86bf2e", "84000000: deadbeef"),
    ("84000000: 1165e46d", "84000000: 1165e46e"),
    ("bootselect=0", "bootselect=1"),
    ("bootcmd=bootselect", "bootcmd=bootm"),
    ("Erase: flash=0x7e0000 size=6160384", "Erase: flash=0x7e0000 size=7995392"),
    ("do_bootselect: spi_flash read 0x007e0000", "do_bootselect: spi_flash read 0x00040000"),
    ("Linux version 5.10.260-openmitrastar-radiohw", "Linux version 2.6.35.12"),
])
def test_corrupted_physical_proof_fails_closed(traces, old, new):
    trace, backend = traces
    assert old in trace
    with pytest.raises(ValueError):
        gate.verify_uart(trace.replace(old, new), backend)


def test_missing_after_write_protected_read_cannot_be_replaced_by_pass_label(traces):
    trace, backend = traces
    before, after = trace.split("Total of 5337088 bytes were the same", 1)
    after = after.replace("84000000: 347cf8db", "84000000: deadbeef")
    with pytest.raises(ValueError, match="CRC"):
        gate.verify_uart(before + "Total of 5337088 bytes were the same" + after, backend)


@pytest.mark.parametrize("extra", [
    "topaz>spi_flash erase 0x00040000 0x007a0000\nErase: flash=0x40000 size=7995392\n",
    "topaz>setenv bootselect 1\n",
    "topaz>saveenv\n",
])
def test_extra_commands_are_rejected_even_when_required_markers_exist(traces, extra):
    trace, backend = traces
    with pytest.raises(ValueError):
        gate.verify_uart(trace + "\n" + extra, backend)


@pytest.mark.parametrize("line", ["Kernel panic - not syncing", "MuC has halted", "driver failed to initialize"])
def test_actual_linux_failure_is_not_excused_as_the_bar_warning(traces, line):
    trace, backend = traces
    with pytest.raises(ValueError):
        gate.verify_uart(trace + "\n" + line + "\n", backend)


def test_different_promoter_stop_is_not_reconciled(traces):
    trace, backend = traces
    with pytest.raises(ValueError, match="known Linux-parser"):
        gate.verify_uart(trace, backend.replace("Bootbase failure during flash boot network ready", "unexpected failure"))


def test_snapshot_hash_drift_rejected_before_use(tmp_path):
    snapshot = gate.CYCLE / "executor-source-snapshot"
    copy = tmp_path / "snapshot"
    shutil.copytree(snapshot, copy)
    source = copy / "tools/f321_mtd4_bootbase_flash.ps1"
    source.write_bytes(source.read_bytes() + b"\n# synthetic test corruption\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        gate.verify_snapshot(gate.Evidence(), copy)


def test_review_edit_cannot_rebind_changed_sources(tmp_path):
    snapshot = tmp_path / "snapshot"
    snapshot.mkdir()
    review = json.loads((gate.CYCLE / "executor-source-snapshot/executor-review.json").read_text())
    review["files"][0]["sha256"] = "0" * 64
    (snapshot / "executor-review.json").write_text(json.dumps(review))
    with pytest.raises(ValueError, match="hash mismatch"):
        gate.verify_snapshot(gate.Evidence(), snapshot)


def test_boolean_claims_cannot_be_missing_or_truthy_numbers():
    for values in ({"a": 1}, {}, {"a": True, "b": True}):
        with pytest.raises(ValueError):
            gate.all_checks(values, {"a"}, "synthetic")


def test_ui_pass_with_different_installed_hash_is_rejected(tmp_path):
    evidence = gate.Evidence()
    _, files, bundle = gate.verify_sealed_inputs(evidence, gate.CANDIDATE_DIR, gate.PACKAGE)
    ui = tmp_path / "ui"
    shutil.copytree(FRESH / "ui", ui)
    transcript = ui / "ssh.stdout.log"
    text = transcript.read_text()
    expected_sha = files["/etc/openmitrastar/release"]
    assert expected_sha in text
    transcript.write_text(text.replace(expected_sha, "0" * 64))
    with pytest.raises(ValueError, match="exact installed F321 files"):
        gate.verify_postchecks(evidence, FRESH / "platform/status.json", ui / "result.json",
                              FRESH / "authenticated-http/result.json", files, bundle, datetime.now(timezone.utc))


def test_original_ui_mime_failure_remains_failure():
    with pytest.raises(ValueError, match="UI gate did not pass"):
        gate.reconcile(gate.CYCLE, gate.CANDIDATE_DIR, gate.PACKAGE,
                       HISTORICAL / "platform/status.json", HISTORICAL / "ui/result.json",
                       HISTORICAL / "authenticated-http/result.json")


def test_fresh_reconciliation_has_separate_scope_and_keeps_original_result():
    original = gate.CYCLE / "result.json"
    before = original.read_bytes()
    report = gate.reconcile(gate.CYCLE, gate.CANDIDATE_DIR, gate.PACKAGE,
                            FRESH / "platform/status.json", FRESH / "ui/result.json",
                            FRESH / "authenticated-http/result.json")
    assert report["status"] == "PASS_F321_INDEPENDENT_POSTBOOT_VALIDATION"
    assert report["original_promoter_result"]["status"] == "STOP_NO_AUTOMATIC_RETRY"
    assert report["postboot_gates"]["platform"]["checks"] == 27
    assert report["postboot_gates"]["authenticated_http"]["checks"] == 10
    assert report["hardware_actions_performed"] is False
    assert report["physical_authorization_granted"] is False
    assert report["release_eligible"] is False
    assert any("DFS" in value for value in report["not_proven"])
    assert original.read_bytes() == before
    assert any(row["sha256"] == hashlib.sha256(before).hexdigest() for row in report["evidence"])


@pytest.mark.parametrize("time", ["2026-09-07T20:00:00+00:00", "2026-09-08T00:10:00", "2026-09-12T01:00:00+00:00"])
def test_gate_timestamps_cannot_precede_flash_or_be_ambiguous_or_future(time):
    with pytest.raises(ValueError):
        gate.timestamp(time, datetime(2026, 9, 11, 12, tzinfo=timezone.utc))


def cli_args(output: Path) -> list[str]:
    return ["--platform-result", str(FRESH / "platform/status.json"),
            "--ui-result", str(FRESH / "ui/result.json"),
            "--authenticated-http-result", str(FRESH / "authenticated-http/result.json"),
            "--output-dir", str(output)]


def test_output_cannot_overwrite_an_existing_result(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    result = output / "result.json"
    result.write_bytes(b"preserved historical result")
    with pytest.raises(FileExistsError):
        gate.main(cli_args(output))
    assert result.read_bytes() == b"preserved historical result"


def test_output_cannot_be_added_inside_historical_input_tree():
    output = gate.CYCLE / "synthetic-must-not-be-created"
    with pytest.raises(ValueError, match="outside historical"):
        gate.main(cli_args(output))
    assert not output.exists()
