from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_rootfs_builder_sets_all_top_level_cgi_executable() -> None:
    text = (ROOT / "tools/build_f170_lyoko_foundation_runtime_fix.py").read_text(encoding="utf-8")
    assert "find \"$stage/new/www\" -maxdepth 1 -type f -name '*.cgi' -exec chmod 0755" in text


def test_f219_builder_is_permission_only() -> None:
    text = (ROOT / "tools/build_f219_cgi_permissions.py").read_text(encoding="utf-8")
    assert 'source": {"firmware": "F218"' in text
    assert "cgi_modes" in text
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text


def test_f219_promoter_preserves_store_tail() -> None:
    text = (ROOT / "tools/promote_f219_mtd4_direct.ps1").read_text(encoding="utf-8")
    assert "e8468c7dae8ab774355a8650ac9d4ac52faa54061220d918aba360b3f0928bb1" in text
    assert '$currentF218FullSlotCrc32 = "7f1c2e0c"' in text
    assert "--erase-bytes 0x5e0000" in text
    assert "spi_flash write" not in text
