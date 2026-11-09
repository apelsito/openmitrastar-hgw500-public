from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-store-protection-observer/qtn-topaz-store-protection-observer.c"
OUT = ROOT / "outputs/kernel-port/f295-store-protection-observer-20260904"


def test_source_contains_only_read_commands() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    for marker in (
        "SPI_READ_STATUS",
        "SPI_READ_ID",
        "SPI_READ_SCUR",
        "SPI_READ_DPB",
        "store_dpb_scan_count",
        "read_commands_only = true",
        "control_restored",
    ):
        assert marker in source
    for marker in (
        "SPI_WRITE_ENABLE",
        "SPI_WRITE_DISABLE",
        "SPI_PAGE_PROGRAM",
        "SPI_SECTOR_ERASE",
        "SPI_WRITE_DPB",
        "SPI_GBLOCK",
        "mtd_device_register",
        "mtd_device_unregister",
        "memcpy_toio",
        "writeb(",
    ):
        assert marker not in source
    assert source.count("qtn_spi_read_command(ctrl,") == 2


def test_built_module_contract() -> None:
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f295-store-protection-observer/v1"
    assert manifest["status"] == "PASS"
    assert manifest["classification"] == "OFFLINE_READ_COMMAND_ONLY_MODULE_NEVER_LOADED"
    assert manifest["target"]["store"]["eraseblocks"] == 28
    assert manifest["safety"] == {
        "erase": False,
        "flash_window_mapping": False,
        "module_autoload": False,
        "mtd_registration": False,
        "program": False,
        "protection_mutation": False,
        "read_commands_only": True,
        "write_enable": False,
    }
    assert manifest["kernel_contract"]["all_imports_exported_by_f293_vmlinux"] is True
    assert manifest["physical_validation"] == "NOT_RUN"
