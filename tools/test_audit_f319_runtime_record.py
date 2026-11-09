"""Historical F319 evidence validation with temporary synthetic records only."""
import json

import pytest

from audit_lyoko_full_liberation import load, verify_recorded_f319_runtime


FIRMWARE = "e33d851106aa342509184ab0d1d94fc0654d7206cb2a4c62c5fab7aa48c0dcc9"
MODULE = "79436442b62110351fba44262a05ae0f2a9ffc87b36fabe74cc651112e431317"


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


@pytest.fixture
def evidence(tmp_path):
    (tmp_path / "uart").mkdir()
    checks = ("claim", "mapping", "reads_zero", "writes_zero", "provider_disabled",
              "mtd_table_unchanged", "fatal_count_unchanged", "module_unloaded",
              "uart_no_fatal", "uart_complete_correlated")
    write(tmp_path / "result.json", {
        "schema": "openmitrastar.f319-spi-owner-runtime/v1", "status": "PASS",
        "firmware": "lyoko-foundation-6.8.3-f319-spi-owner-claim-device",
        "firmware_sha256": FIRMWARE, "module_sha256": MODULE,
        "flash": False, "mtd_writes": False, "checks": dict.fromkeys(checks, True),
        "uart_capture_exit_code": 0, "uart_capture_pid": 123,
        "uart_capture_run_id": "f319-test",
    })
    write(tmp_path / "plan.json", {
        "mode": "execute", "local_preflight_pass": True,
        "firmware_sha256": FIRMWARE, "module_sha256": MODULE,
    })
    raw = b"f319-test_BEGIN\r\nsynthetic evidence\r\nf319-test_END\r\n"
    (tmp_path / "uart/uart.raw.bin").write_bytes(raw)
    (tmp_path / "uart/uart.log").write_bytes(raw)
    write(tmp_path / "uart/capture-status.json", {
        "schema": "openmitrastar.uart-capture-status/v1", "state": "complete",
        "ready": True, "rx_only": True, "dtr": False, "rts": False, "gaps": 0,
        "error": None, "current_port": "COM3",
        "pinned_pnp_device_id": r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000",
        "capture_pid": 123, "run_id": "f319-test", "bytes": len(raw),
    })
    (tmp_path / "probe.stdout.log").write_text(
        "controller_resource_claimed=Y\ncontroller_mapped=Y\n"
        "controller_read_count=0\ncontroller_write_count=0\ntransaction_provider_ready=N\n"
        "MODULE_UNLOADED=1\nFATAL_BEFORE=0\nFATAL_AFTER=0\n"
        f"MTD_TABLE_HASH_BEFORE={'a' * 64}\nMTD_TABLE_HASH_AFTER={'a' * 64}\n"
        "OMF319_SPI_OWNER_PASS\n", encoding="ascii")
    return tmp_path


def test_complete_correlated_record_is_historical_pass(evidence):
    result = verify_recorded_f319_runtime(evidence)
    assert result["verified"] is True
    assert result["status"] == "PHYSICAL_PASS_RECORDED"
    assert len(result["evidence"]) == 6


@pytest.mark.parametrize("field,value", [
    ("status", "FAIL"), ("firmware", "F314"), ("firmware_sha256", "wrong"),
    ("uart_capture_exit_code", None), ("uart_capture_exit_code", 7),
    ("uart_capture_exit_code", False), ("uart_capture_pid", 456),
    ("uart_capture_run_id", "other"),
])
def test_invalid_result_cannot_be_accepted(evidence, field, value):
    path = evidence / "result.json"
    record = load(path)
    record[field] = value
    write(path, record)
    assert verify_recorded_f319_runtime(evidence)["verified"] is False


@pytest.mark.parametrize("field,value", [
    ("state", "capturing"), ("gaps", 1), ("rx_only", False),
    ("pinned_pnp_device_id", "another-adapter"), ("capture_pid", 456),
])
def test_capture_must_match_completed_run(evidence, field, value):
    path = evidence / "uart/capture-status.json"
    record = load(path)
    record[field] = value
    write(path, record)
    assert verify_recorded_f319_runtime(evidence)["verified"] is False


@pytest.mark.parametrize("old,new", [
    ("controller_read_count=0", "controller_read_count=1"),
    ("MODULE_UNLOADED=1", "MODULE_UNLOADED=0"),
    ("FATAL_AFTER=0", "FATAL_AFTER=1"),
    ("controller_mapped=Y", "controller_mapped=Y\ncontroller_mapped=Y"),
])
def test_stdout_is_rechecked_not_just_pass_flags(evidence, old, new):
    path = evidence / "probe.stdout.log"
    path.write_text(path.read_text().replace(old, new), encoding="ascii")
    assert verify_recorded_f319_runtime(evidence)["verified"] is False


def test_missing_exit_record_remains_incomplete(evidence):
    (evidence / "result.json").unlink()
    assert verify_recorded_f319_runtime(evidence)["status"] == "INCOMPLETE_NOT_ACCEPTED"


def test_raw_text_corruption_is_rejected(evidence):
    (evidence / "uart/uart.raw.bin").write_bytes(b"changed")
    assert verify_recorded_f319_runtime(evidence)["verified"] is False


def test_unknown_check_is_not_a_pass(evidence):
    path = evidence / "result.json"
    record = load(path)
    record["checks"]["uart_complete_correlated"] = "true"
    write(path, record)
    assert verify_recorded_f319_runtime(evidence)["verified"] is False


def test_absent_attempt_is_not_run():
    assert verify_recorded_f319_runtime(None)["status"] == "NOT_RUN"
