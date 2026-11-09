"""Offline classification of historical UART readiness, with no device APIs."""
from copy import deepcopy

import pytest

from audit_lyoko_full_liberation import valid_recorded_uart_binding


def record():
    version = "lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device"
    return {
        "schema": "openmitrastar.f319-uart-readiness/v1",
        "status": "PASS_IDENTITY_AND_RX_BINDING_ONLY",
        "host": "192.168.1.90",
        "expected_version": version,
        "guard_source_sha256": "a" * 64,
        "pinned_ssh_verified": True,
        "exclusive_guard_acquired": True,
        "cleanup": "OWN_GUARD_RELEASED",
        "binding": {
            "RouterHost": "192.168.1.90",
            "ExpectedVersion": version,
            "Port": "COM3",
            "PnpDeviceId": r"FTDIBUS\VID_0403+PID_6001+AG41W2BLA\0000",
            "NonceObserved": True,
        },
    }


def test_accepts_only_recorded_rx_scope():
    assert valid_recorded_uart_binding(record(), "a" * 64)


@pytest.mark.parametrize("field,value", [
    ("status", "FAIL"), ("host", "192.168.1.1"),
    ("expected_version", "different-board"), ("pinned_ssh_verified", False),
    ("exclusive_guard_acquired", False), ("cleanup", "FAILED"),
    ("guard_source_sha256", "b" * 64),
])
def test_rejects_invalid_record(field, value):
    candidate = deepcopy(record())
    candidate[field] = value
    assert not valid_recorded_uart_binding(candidate, "a" * 64)


@pytest.mark.parametrize("field,value", [
    ("RouterHost", "192.168.1.1"), ("ExpectedVersion", "other"),
    ("Port", "COM4"), ("PnpDeviceId", "other-adapter"),
    ("NonceObserved", False), ("NonceObserved", "true"),
])
def test_rejects_invalid_binding(field, value):
    candidate = deepcopy(record())
    candidate["binding"][field] = value
    assert not valid_recorded_uart_binding(candidate, "a" * 64)


def test_missing_record_is_not_proof():
    assert not valid_recorded_uart_binding({}, "a" * 64)
