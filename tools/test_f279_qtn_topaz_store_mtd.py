from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-store-mtd/qtn-topaz-store-mtd.c"
OUT = ROOT / "outputs/kernel-port/f279-qtn-topaz-store-mtd-20260903"


def test_source_is_bounded_and_write_disabled_by_default() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    assert "LYOKO_STORE_OFFSET\t0x00dc0000" in source
    assert "LYOKO_STORE_SIZE\t0x001c0000" in source
    assert "LYOKO_STORE_ERASE_SIZE\t0x00010000" in source
    assert "module_param(allow_write, bool, 0400)" in source
    assert "module_param(register_mtd, bool, 0400)" in source
    assert "qtn_spi_read_scur" in source
    assert "qtn_spi_read_dpb" in source
    assert "store_first_dpb" in source and "store_last_dpb" in source
    assert "if (allow_write && !register_mtd)" in source
    assert "static bool allow_write;" in source
    assert "qtn_store_range_valid" in source
    assert "qtn_store_page_matches" in source
    assert "MTD_FAIL_ADDR_UNKNOWN" in source
    assert "instr->fail_addr = offset" in source
    assert "instr->fail_addr = LYOKO_STORE_OFFSET + offset" not in source
    # The source gained additional read-only protection probes after the
    # immutable F279 artifact was built. Every direct transaction must still
    # deassert chip select before returning to the caller.
    assert source.count("qtn_spi_deassert_cs(qs);") >= 3
    assert "MTD_CAP_ROM" in source and "MTD_CAP_NORFLASH" in source
    assert "SPI_BULK_ERASE" not in source


def test_manifest_records_no_hardware_action() -> None:
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f279-qtn-topaz-store-mtd/v1"
    assert manifest["status"] == "PASS"
    assert manifest["classification"] == "OFFLINE_MODULE_NEVER_LOADED"
    assert manifest["safety"]["write_default"] is False
    # The archived first F279 manifest predates the explicit field, while the
    # source default and documentation already require register_mtd=false.
    assert manifest["safety"].get("register_mtd_default", False) is False
    assert manifest["safety"]["bulk_erase"] is False
    assert manifest["safety"]["mtd0_mtd1_mtd2_mtd3_mtd5_unaddressable"] is True
    assert manifest["kernel_contract"]["all_imports_exported_by_f223_vmlinux"] is True
    assert manifest["kernel_contract"]["module_symvers_required"] is False
    assert "mtd_device_parse_register" in manifest["kernel_contract"]["undefined_symbols"]
    assert manifest["hardware_actions"] == {
        "router": False,
        "uart": False,
        "module_load": False,
        "mtd_write": False,
    }
