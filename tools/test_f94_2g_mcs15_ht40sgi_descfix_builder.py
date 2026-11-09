#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "tools/build_f94_2g_mcs15_ht40sgi_descfix_from_f93.py"


def test_f94_builder_starts_from_f93_and_replaces_only_realtek_leaf_modules() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f93-2g-ht40sgi-hostapd-compat-fixedsize-after-f92" in text
    assert "q3-persistent-composite-f94-2g-mcs15-ht40sgi-descfix-after-f93" in text
    assert "all64-mcs15-ht40sgi-descfix-f94-RAM-ONLY-NO-FLASH" in text
    assert "radio2g/rtl_pci.ko" in text
    assert "radio2g/rtl8192ee.ko" in text
    assert "cfg80211.ko" not in text.partition("MODULE_REPLACEMENTS = {")[2].partition("}")[0]
    assert "mac80211.ko" not in text.partition("MODULE_REPLACEMENTS = {")[2].partition("}")[0]


def test_f94_builder_updates_loader_and_hash_contracts() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "hgw500_force_data_ht40sgi=1" in text
    assert "hgw500_force_data_ht40sgi=Y" in text
    assert "usr/share/openmitrastar/radio2g/artifacts.sha256" in text
    assert '"rootfs": raw_path' in text
    assert '"rootfs": {' in text
    assert "F94 radio2g hash update did not touch every replacement" in text


def test_f94_builder_keeps_flash_disabled_in_manifest() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert '"flash": False' in text
    assert '"touches_router": False' in text
    assert '"opens_uart": False' in text
