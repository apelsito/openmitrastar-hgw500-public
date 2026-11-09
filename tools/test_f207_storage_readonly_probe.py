from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f207_storage_readonly_probe as f207  # noqa: E402


def test_variant_dts_has_non_overlapping_read_only_windows() -> None:
    text = f207.DTS.read_text(encoding="utf-8")
    assert 'reg = <0x90960000 0x00460000>;' in text
    assert 'lyoko_store: flash@90dc0000' in text
    assert 'reg = <0x90dc0000 0x001c0000>;' in text
    assert text.count('compatible = "mtd-rom";') >= 5
    assert 'linux,mtd-name = "lyoko_store";' in text


def test_built_storage_contract() -> None:
    manifest_path = f207.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f205 = json.loads((f207.F205_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f207-storage-readonly-probe/v1"
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    assert manifest["storage"]["store_size"] == "0x001c0000"
    assert manifest["storage"]["store_write"] is False
    assert manifest["storage"]["store_erased_ff"] is True
    assert manifest["storage"]["candidate_ends_before_store"] is True
    assert manifest["artifacts"]["rootfs_squashfs"]["sha256"] != f205["artifacts"]["rootfs_squashfs"]["sha256"]
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] != f205["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["artifacts"]["config"]["sha256"] == f205["artifacts"]["config"]["sha256"]
    assert manifest["spi_probe"]["write"] is False
    assert manifest["spi_probe"]["mtd_registration"] is False
    assert manifest["layout"]["rootfs_headroom_bytes"] > 0
    assert manifest["physical_validation"]["status"] == "NOT_RUN"


def test_dtb_contains_store_identity() -> None:
    manifest_path = f207.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    dtb = f207.OUT / f"{f207.BASE}.dtb"
    data = dtb.read_bytes()
    assert b"rootfs_live" in data
    assert b"lyoko_store" in data


def test_probe_source_and_boot_script_are_read_only() -> None:
    source = (f207.SPI_SOURCE / "qtn-topaz-spi-probe.c").read_text(encoding="utf-8")
    script = (f207.SPI_OVERLAY / "etc/init.d/S31-spi-probe").read_text(encoding="utf-8")
    assert "readl" in source and "write_capable = false" in source
    assert "insmod" in script and "write_capable" in script
    for forbidden in ("writel", "spi_write", "erase", "mtd_device_register", "flash_erase", "mtd_debug", "dd of=", "mount"):
        assert forbidden not in source + "\n" + script
