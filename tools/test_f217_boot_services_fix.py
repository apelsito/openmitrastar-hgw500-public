from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_builder_normalizes_busybox_inputs() -> None:
    text = (ROOT / "tools/build_f217_boot_services_fix.py").read_text(encoding="utf-8")
    assert "write_bytes" in text
    assert 'web_hash.encode("ascii") + b"\\n"' in text
    assert "f214-machine-check" in text
    assert "multicast_snooping" in text
    assert 'engine.PRODUCT_VERSION = "lyoko-foundation-3.2-f217-device"' in text
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text


def test_device_gate_uses_configurable_known_hosts() -> None:
    text = (ROOT / "tools/post_flash_f214_device_gate.py").read_text(encoding="utf-8")
    assert '--known-hosts-name' in text
    assert 'SPI_PROBE_STATE=disabled' in text
    assert 'MULTICAST_STATE=available' in text


def test_f217_promoter_preserves_store_tail() -> None:
    text = (ROOT / "tools/promote_f217_mtd4_direct.ps1").read_text(encoding="utf-8")
    assert "2eb8b7be3e978e093a9168b45284acb8516edd464a7c0fca13ffc3475746b270" in text
    assert '$currentF215FullSlotCrc32 = "71bcfa11"' in text
    assert "--erase-bytes 0x5e0000" in text
    assert 'preserved_store_bytes = "0x001c0000"' in text
    assert "spi_flash write" not in text
    assert "fw_setenv" not in text
