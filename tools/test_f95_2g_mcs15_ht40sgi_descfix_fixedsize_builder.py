#!/usr/bin/env python3
from pathlib import Path
import json


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_f95_2g_mcs15_ht40sgi_descfix_fixedsize_from_f93.py"
WRAPPER = ROOT / "tools/flash_f95_2g_mcs15_ht40sgi_descfix_fixedsize_after_f93.ps1"
F93_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92/build"
F93_BASE = "openmitrastar-linux510-q3-persistent-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92-LZMA-OFFLINE-NO-FLASH"
F95_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93/build"
F95_BASE = "openmitrastar-linux510-q3-persistent-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93-LZMA-OFFLINE-NO-FLASH"


def test_f95_builder_starts_from_f93_and_replaces_only_realtek_leaf_modules() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92" in text
    assert "q3-persistent-composite-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93" in text
    assert "all64-mcs15-ht40sgi-descfix-f94-RAM-ONLY-NO-FLASH" in text
    assert "radio2g/rtl_pci.ko" in text
    assert "radio2g/rtl8192ee.ko" in text
    assert "cfg80211.ko" not in text.partition("MODULE_REPLACEMENTS = {")[2].partition("}")[0]
    assert "mac80211.ko" not in text.partition("MODULE_REPLACEMENTS = {")[2].partition("}")[0]


def test_f95_builder_updates_loader_hashes_and_fixed_size_contracts() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "hgw500_force_data_ht40sgi=1" in text
    assert "hgw500_force_data_ht40sgi=Y" in text
    assert "usr/share/openmitrastar/radio2g/artifacts.sha256" in text
    assert "COMPENSATION_ENTRIES" in text
    assert "F95 fixed-size patch changed decompressed payload size" in text
    assert "F95 fixed-size patch changed CPIO end" in text
    assert "raw_bytes_preserved" in text
    assert '"rootfs": raw_path' in text
    assert '"rootfs": {' in text
    assert "F94 radio2g hash update did not touch every replacement" in text


def test_f95_builder_keeps_flash_disabled_in_manifest() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert '"flash": False' in text
    assert '"touches_router": False' in text
    assert '"opens_uart": False' in text


def test_f95_flash_wrapper_targets_f93_and_supports_blind_autobreak() -> None:
    text = WRAPPER.read_text(encoding="ascii")
    assert 'q3-persistent-composite-f95-2g-mcs15-ht40sgi-descfix-fixedsize-after-f93' in text
    assert 'OPENMITRASTAR_Q3_F95_2G_MCS15_HT40SGI_DESCFIX_FIXEDSIZE_AFTER_F93_MTD4_FLASH' in text
    assert '[string]$CurrentLiveCrc32 = "b68554e2"' in text
    assert "[switch]$AllowBlindAutobreak" in text
    assert "$q3Params.AllowBlindAutobreak = $true" in text


def test_f95_artifact_preserves_f93_boot_entry_offset_contract() -> None:
    f93_raw = F93_BUILD / f"{F93_BASE}.decompressed.bin"
    f95_raw = F95_BUILD / f"{F95_BASE}.decompressed.bin"
    manifest = json.loads((F95_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert f93_raw.is_file()
    assert f95_raw.is_file()
    f93 = f93_raw.read_bytes()
    f95 = f95_raw.read_bytes()
    assert len(f95) == len(f93) == 15_692_768
    assert manifest["patch"]["cpio"]["start"] == 8192
    assert manifest["patch"]["cpio"]["old_end"] == 12_046_444
    assert manifest["patch"]["cpio"]["new_end"] == 12_046_444
    assert manifest["patch"]["cpio"]["delta_bytes"] == 0
    assert manifest["patch"]["cpio"]["uncompensated_delta_bytes"] == 2356
    assert manifest["patch"]["fixed_size_compensation"]["removed_bytes"] == 2356
    entry_offset = 0xB7E000
    assert f95[entry_offset:entry_offset + 256] == f93[entry_offset:entry_offset + 256]
