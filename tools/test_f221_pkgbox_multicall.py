from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build_f221_pkgbox_multicall.py"


def test_f221_is_multicall_pkgbox_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'source": {"firmware": "F220"' in text
    assert '"multicall_dispatcher": True' in text
    assert 'required = {"etc/openmitrastar/release", "usr/libexec/lyoko/pkgbox"}' in text
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text


def test_f221_promoter_is_mtd4_only() -> None:
    text = (ROOT / "tools/promote_f221_mtd4_direct.ps1").read_text(encoding="utf-8")
    assert "d2ee724161881375a6dfdbb991c3195d5548c0a2ff7a612ddb204c197be4b665" in text
    assert '$currentF220FullSlotCrc32 = "c694ff31"' in text
    assert "--erase-bytes 0x5e0000" in text
    assert "post_flash_f219_package_gate.py" in text
    assert "spi_flash write" not in text
