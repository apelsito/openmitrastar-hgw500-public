from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build_f220_pkgbox_wc.py"


def test_f220_is_pkgbox_only() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'source": {"firmware": "F219"' in text
    assert '"added_applet": "wc"' in text
    assert 'required = {"etc/openmitrastar/release", "usr/libexec/lyoko/pkgbox"}' in text
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text


def test_f220_promoter_is_mtd4_only() -> None:
    text = (ROOT / "tools/promote_f220_mtd4_direct.ps1").read_text(encoding="utf-8")
    assert "ed11085896453b031153f092a1188de7e9cbd6e977b45ede0e3d53c974998e78" in text
    assert '$currentF219FullSlotCrc32 = "18399a03"' in text
    assert "--erase-bytes 0x5e0000" in text
    assert "post_flash_f219_package_gate.py" in text
    assert "spi_flash write" not in text
