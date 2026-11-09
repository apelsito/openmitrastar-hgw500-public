#!/usr/bin/env python3
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILDER = ROOT / "tools/build_f103_emac_rxrestart_63pokes_from_f101.py"
F101_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f101-2g-hwcrypto-from-f100/build"
F101_BASE = "openmitrastar-linux510-q3-persistent-f101-2g-hwcrypto-from-f100-LZMA-OFFLINE-NO-FLASH"
F103_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f103-emac-rxrestart-63pokes-from-f101/build"
F103_BASE = "openmitrastar-linux510-q3-persistent-f103-emac-rxrestart-63pokes-from-f101-LZMA-OFFLINE-NO-FLASH"

OLD_CONTEXT = bytes.fromhex(
    "aa 15 00 16"
    "11 08 15 02"
    "4a 23 00 20"
    "4a 22 00 20"
    "93 01 00 00"
)
NEW_CONTEXT = bytes.fromhex(
    "aa 15 00 16"
    "11 08 d5 0f"
    "4a 23 00 20"
    "4a 22 00 20"
    "93 01 00 00"
)


def test_f103_builder_scope_is_single_emac_branch_patch() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "f103-emac-rxrestart-63pokes-from-f101" in text
    assert "brhs r0,0x8,+16" in text
    assert "brhs r0,0x3f,+16" in text
    assert "qtn,irq-poll-fallback" in text
    assert "unchanged from F101" in text
    assert "touches_router\": False" in text
    assert "opens_uart\": False" in text
    assert "flash\": False" in text


def test_f103_artifact_changes_only_unique_branch_context_and_preserves_layout() -> None:
    f101_raw = (F101_BUILD / f"{F101_BASE}.decompressed.bin").read_bytes()
    f103_raw = (F103_BUILD / f"{F103_BASE}.decompressed.bin").read_bytes()
    manifest = json.loads((F103_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert len(f103_raw) == len(f101_raw)
    assert f101_raw.count(OLD_CONTEXT) == 1
    assert f101_raw.count(NEW_CONTEXT) == 0
    assert f103_raw.count(OLD_CONTEXT) == 0
    assert f103_raw.count(NEW_CONTEXT) == 1
    assert manifest["patch"]["raw"]["offset"] == f101_raw.find(OLD_CONTEXT)
    assert manifest["patch"]["raw"]["new_same_cur_rx_pokes"] == 63
    assert manifest["patch"]["cpio"]["unchanged"] is True
    assert manifest["bootbase_contract"]["result"] == "PASS"


def test_f103_keeps_f101_cpio_dtb_modules_and_poll_fallback_property() -> None:
    f101_raw = (F101_BUILD / f"{F101_BASE}.decompressed.bin").read_bytes()
    f103_raw = (F103_BUILD / f"{F103_BASE}.decompressed.bin").read_bytes()
    _s1, f101_entries, _r1 = f71.parse_first_cpio(f101_raw)
    _s2, f103_entries, _r2 = f71.parse_first_cpio(f103_raw)
    before = {entry.name: entry.data for entry in f101_entries}
    after = {entry.name: entry.data for entry in f103_entries}
    assert before.keys() == after.keys()
    assert all(before[name] == after[name] for name in before)
    f101_dtb = (F101_BUILD / f"{F101_BASE}.dtb").read_bytes()
    f103_dtb = (F103_BUILD / f"{F103_BASE}.dtb").read_bytes()
    assert f103_dtb == f101_dtb
    assert b"qtn,irq-poll-fallback" in f103_dtb
    for module in (
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko",
    ):
        assert before[module] == after[module]


def test_f103_vmlinux_matches_binary_branch_patch() -> None:
    f101_vmlinux = (F101_BUILD / f"{F101_BASE}.vmlinux").read_bytes()
    f103_vmlinux = (F103_BUILD / f"{F103_BASE}.vmlinux").read_bytes()
    assert len(f103_vmlinux) == len(f101_vmlinux)
    assert f101_vmlinux.count(OLD_CONTEXT) == 1
    assert f103_vmlinux.count(OLD_CONTEXT) == 0
    assert f103_vmlinux.count(NEW_CONTEXT) == 1
