from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/run_f227_package_api_physical_gate.py"


def test_gate_is_explicit_volatile_and_mtd5_read_only() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "--execute" in source
    assert "OPENMITRASTAR_F227_VOLATILE_PACKAGE_API" in source
    assert "om-package-api enable" not in source
    assert "$ctl enable" in source and "$ctl disable" in source
    assert "DATA_HASH_BEFORE" in source and "DATA_HASH_AFTER" in source
    assert "runtime_installed_count" in source
    assert "spi_flash write" not in source
    assert "flash_erase" not in source
    assert "/dev/mtdblock2" in source
