#!/usr/bin/env python3
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILDER = ROOT / "tools/build_f102_emac_irq_poll_disabled_from_f101.py"
F101_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f101-2g-hwcrypto-from-f100/build"
F101_BASE = "openmitrastar-linux510-q3-persistent-f101-2g-hwcrypto-from-f100-LZMA-OFFLINE-NO-FLASH"
F102_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f102-emac-irq-poll-disabled-from-f101/build"
F102_BASE = "openmitrastar-linux510-q3-persistent-f102-emac-irq-poll-disabled-from-f101-LZMA-OFFLINE-NO-FLASH"


def test_f102_builder_is_dtb_only_emac_scope() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f101-2g-hwcrypto-from-f100" in text
    assert "f102-emac-irq-poll-disabled-from-f101" in text
    assert "qtn,irq-poll-fallback" in text
    assert "qtn,irq-poll-disabled" in text
    assert "initramfs_cpio" in text
    assert "unchanged byte-for-byte" in text
    assert "radio2g_modules" in text
    assert "unchanged from F101" in text
    assert "radio5_modules" in text
    assert "qdrv" in text
    assert "touches_router\": False" in text
    assert "opens_uart\": False" in text
    assert "flash\": False" in text


def test_f102_artifact_patches_only_embedded_fdt_occurrence() -> None:
    f101_raw = (F101_BUILD / f"{F101_BASE}.decompressed.bin").read_bytes()
    f102_raw = (F102_BUILD / f"{F102_BASE}.decompressed.bin").read_bytes()
    manifest = json.loads((F102_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert len(f102_raw) == len(f101_raw)
    assert f101_raw.count(b"qtn,irq-poll-fallback") == 2
    assert f102_raw.count(b"qtn,irq-poll-fallback") == 1
    assert f101_raw.count(b"qtn,irq-poll-disabled") == 0
    assert f102_raw.count(b"qtn,irq-poll-disabled") == 1
    raw_patch = manifest["patch"]["raw"]["matches"][0]
    assert raw_patch["fdt_offset"] < raw_patch["property_offset"]
    assert raw_patch["property_offset"] < raw_patch["fdt_offset"] + raw_patch["total_size"]
    assert manifest["patch"]["raw"]["old"] == "qtn,irq-poll-fallback"
    assert manifest["patch"]["raw"]["new"] == "qtn,irq-poll-disabled"
    assert manifest["patch"]["cpio"]["unchanged"] is True
    assert manifest["bootbase_contract"]["result"] == "PASS"


def test_f102_cpio_entries_and_modules_are_unchanged() -> None:
    f101_raw = (F101_BUILD / f"{F101_BASE}.decompressed.bin").read_bytes()
    f102_raw = (F102_BUILD / f"{F102_BASE}.decompressed.bin").read_bytes()
    _s1, f101_entries, _r1 = f71.parse_first_cpio(f101_raw)
    _s2, f102_entries, _r2 = f71.parse_first_cpio(f102_raw)
    before = {entry.name: entry.data for entry in f101_entries}
    after = {entry.name: entry.data for entry in f102_entries}
    assert before.keys() == after.keys()
    assert all(before[name] == after[name] for name in before)
    for module in (
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko",
    ):
        assert before[module] == after[module]


def test_f102_copied_dtb_has_disabled_property() -> None:
    f101_dtb = (F101_BUILD / f"{F101_BASE}.dtb").read_bytes()
    f102_dtb = (F102_BUILD / f"{F102_BASE}.dtb").read_bytes()
    assert len(f102_dtb) == len(f101_dtb)
    assert b"qtn,irq-poll-fallback" in f101_dtb
    assert b"qtn,irq-poll-disabled" not in f101_dtb
    assert b"qtn,irq-poll-fallback" not in f102_dtb
    assert b"qtn,irq-poll-disabled" in f102_dtb
