from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f181_spi_readonly_probe as f181  # noqa: E402


def test_source_has_no_write_path() -> None:
    source = (f181.SOURCE / "qtn-topaz-spi-probe.c").read_text(encoding="utf-8")
    assert "TOPAZ_SPI_READ_ID\t0x00009f00" in source
    assert "TOPAZ_SPI_EXPECTED_ID\t0x00c22018" in source
    assert "write_capable = false" in source
    for forbidden in ("writel(", "mtd_info", "spi_flash_erase", "spi_flash_write", "register_mtd"):
        assert forbidden not in source


def test_built_module_contract() -> None:
    manifest_path = f181.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["classification"] == "OFFLINE_MODULE_NOT_LOADED"
    assert manifest["target"]["expected_jedec_id"] == "0xc22018"
    assert manifest["capabilities"] == {
        "erase": False,
        "mtd_registration": False,
        "read_jedec_id": True,
        "read_status": True,
        "write": False,
    }
    assert manifest["hardware_actions"]["module_load"] is False
