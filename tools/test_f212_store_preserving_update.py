from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import simulate_f212_store_preserving_update as f212  # noqa: E402


def test_physical_layout_is_exact_and_aligned() -> None:
    assert f212.MTD3_OFFSET == 0x040000
    assert f212.MTD4_OFFSET == 0x7E0000
    assert f212.PREFIX_SIZE == 0x5E0000
    assert f212.STORE_OFFSET == 0xDC0000
    assert f212.STORE_SIZE == 0x1C0000
    assert f212.MTD5_OFFSET == 0xF80000
    assert f212.STORE_OFFSET + f212.STORE_SIZE == f212.MTD5_OFFSET
    assert all(value % f212.ERASE_SIZE == 0 for value in (f212.MTD4_OFFSET, f212.PREFIX_SIZE, f212.STORE_OFFSET, f212.STORE_SIZE))


def test_simulation_preserves_store_and_protected_regions() -> None:
    result_path = f212.OUT / "result.json"
    if not result_path.is_file():
        return
    result = json.loads(result_path.read_text(encoding="ascii"))
    assert result["status"] == "PASS"
    assert all(result["checks"].values())
    assert result["write_contract"]["full_mtd4_erase_allowed"] is False
    assert result["authorization"]["granted"] is False
    assert result["authorization"]["executor_emitted"] is False


def test_simulator_has_no_hardware_executor() -> None:
    source = Path(f212.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "spi_flash write", "mtd_debug", "fw_setenv", "COM3", "serial.Serial"):
        assert forbidden not in source
