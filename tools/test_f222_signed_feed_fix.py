from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build_f222_signed_feed_fix.py"


def test_f222_binds_runtime_to_signed_two_package_feed() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'source": {"firmware": "F221"' in text
    assert "lyoko-runtime-signature-v1.1" in text
    assert "/usr/libexec/lyoko/busybox" in text
    assert "Packages.sig.json" in text
    assert "signature_verified_before_write" in text
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text


def test_f222_promoter_is_mtd4_only() -> None:
    text = (ROOT / "tools/promote_f222_mtd4_direct.ps1").read_text(encoding="utf-8")
    assert "ab8f8727f3b1c29a312eddb21f1aa5bc9f474d7be91569f57c9230aaf1fc1c21" in text
    assert '$currentF221FullSlotCrc32 = "4593529d"' in text
    assert "--erase-bytes 0x5e0000" in text
    assert "post_flash_f219_package_gate.py" in text
    assert "spi_flash write" not in text
