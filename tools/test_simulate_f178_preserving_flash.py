from pathlib import Path

import pytest

import simulate_f178_preserving_flash as f178


def test_prefix_flash_preserves_store_and_protected_partitions() -> None:
    candidate = bytes((index * 13) & 0xFF for index in range(0x4DF000))
    result = f178.simulate(candidate)
    assert result["status"] == "PASS"
    assert result["checks"]["store_preserved"] is True
    assert result["checks"]["mtd3_preserved"] is True
    assert result["checks"]["mtd5_preserved"] is True
    assert result["candidate"]["prefix_headroom_bytes"] == 0x101000


def test_oversized_candidate_is_rejected() -> None:
    with pytest.raises(ValueError, match="does not fit"):
        f178.simulate(b"x" * (f178.PREFIX_SIZE + 1))


def test_layout_matches_physical_flash_end() -> None:
    assert f178.STORE_OFFSET == 0xDC0000
    assert f178.STORE_SIZE == 0x1C0000
    assert f178.STORE_OFFSET + f178.STORE_SIZE == f178.MTD5_OFFSET
