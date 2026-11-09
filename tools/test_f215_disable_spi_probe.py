from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_f215_is_a_single_boot_script_change() -> None:
    text = (ROOT / "tools/build_f215_disable_spi_probe.py").read_text(encoding="utf-8")
    assert 'private_source_build = args.private_output_root.resolve()' in text
    assert '"firmware/f214-device-bound"' in text
    assert 'shutil.copytree(private_source_build, source_build)' in text
    assert 'status=disabled' in text
    assert 'reason=f214-machine-check' in text
    assert 'engine.PRODUCT_VERSION = "lyoko-foundation-3.1-f215-device"' in text
    assert '"source": {"firmware": "F214"' in text
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text


def test_f215_powercycle_promoter_is_mtd4_only() -> None:
    text = (ROOT / "tools/promote_f215_mtd4_after_powercycle.ps1").read_text(encoding="utf-8")
    assert "2f660934f258810642c605244b7d93fd9c0736f3c47f143b7b08431b013e3c6a" in text
    assert '$currentF214FullSlotCrc32 = "7c9a60f2"' in text
    assert 'write_target = "mtd4/linux_live"' in text
    assert 'erase_bytes = "0x005e0000"' in text
    assert 'preserved_store_bytes = "0x001c0000"' in text
    assert "--transport uart-ymodem" in text
    assert "--uart-attach-topaz" in text
    assert "--erase-bytes 0x5e0000" in text
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text
