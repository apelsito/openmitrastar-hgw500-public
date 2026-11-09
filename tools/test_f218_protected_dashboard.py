from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_f218_protected_dashboard.py"


def test_dashboard_moves_behind_session_cgi() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert 'engine.REMOVE_PATHS = ("www/dashboard.html",)' in text
    assert 'overlay / "www/dashboard.cgi"' in text
    assert 'overlay / "usr/share/openmitrastar/web/dashboard.html"' in text
    assert "require_page_session || return 1" in text
    assert "redirect /dashboard.cgi" in text
    assert "Location: /dashboard.cgi" in text


def test_f218_has_no_hardware_actions() -> None:
    text = BUILDER.read_text(encoding="utf-8")
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text
    assert '"hardware_actions": {"router": False, "uart": False, "flash": False}' in text


def test_rootfs_builder_keeps_cgi_executable() -> None:
    text = (ROOT / "tools/build_f170_lyoko_foundation_runtime_fix.py").read_text(encoding="utf-8")
    assert "! -name '*.cgi'" in text
    assert "-name '*.cgi' -exec chmod 0755" in text


def test_gate_checks_protected_and_removed_dashboard_paths() -> None:
    text = (ROOT / "tools/post_flash_f214_device_gate.py").read_text(encoding="utf-8")
    assert 'http://{args.host}/dashboard.cgi' in text
    assert 'http://{args.host}/dashboard.html' in text
    assert '"legacy_dashboard_removed": legacy_dashboard_status == 404' in text


def test_f218_promoter_preserves_store_tail() -> None:
    text = (ROOT / "tools/promote_f218_mtd4_direct.ps1").read_text(encoding="utf-8")
    assert "aca5d0f92cdad7a3ef7cbc1539f6abacbe463c8fca5b1afd07e960cedade52df" in text
    assert '$currentF217FullSlotCrc32 = "6738ed5a"' in text
    assert "--erase-bytes 0x5e0000" in text
    assert "spi_flash write" not in text
