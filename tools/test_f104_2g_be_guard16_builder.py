#!/usr/bin/env python3
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILDER = ROOT / "tools/build_f104_2g_be_guard16_from_f103.py"
F103_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f103-emac-rxrestart-63pokes-from-f101/build"
F103_BASE = "openmitrastar-linux510-q3-persistent-f103-emac-rxrestart-63pokes-from-f101-LZMA-OFFLINE-NO-FLASH"
F104_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f104-2g-be-guard16-from-f103/build"
F104_BASE = "openmitrastar-linux510-q3-persistent-f104-2g-be-guard16-from-f103-LZMA-OFFLINE-NO-FLASH"
PATCH_ENTRY = "usr/sbin/om-radio-modules"

F103_EMAC_CONTEXT = bytes.fromhex(
    "aa 15 00 16"
    "11 08 d5 0f"
    "4a 23 00 20"
    "4a 22 00 20"
    "93 01 00 00"
)
F101_EMAC_CONTEXT = bytes.fromhex(
    "aa 15 00 16"
    "11 08 15 02"
    "4a 23 00 20"
    "4a 22 00 20"
    "93 01 00 00"
)


def entries_by_name(raw: bytes) -> dict[str, bytes]:
    _start, entries, _remainder = f71.parse_first_cpio(raw)
    return {entry.name: entry.data for entry in entries}


def test_f104_builder_scope_is_queue_guard_only() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "f104-2g-be-guard16-from-f103" in text
    assert "hgw500_tx_queue_guard=0" in text
    assert "hgw500_tx_queue_guard=1" in text
    assert "hgw500_tx_queue_guard_high=16" in text
    assert "hgw500_tx_queue_guard_low=8" in text
    assert "swenc=0" in text
    assert "MCS7 forced" in text
    assert "unchanged from F103" in text
    assert "touches_router\": False" in text
    assert "opens_uart\": False" in text
    assert "flash\": False" in text


def test_f104_changes_only_om_radio_modules_entry_and_preserves_payload_shape() -> None:
    f103_raw = (F103_BUILD / f"{F103_BASE}.decompressed.bin").read_bytes()
    f104_raw = (F104_BUILD / f"{F104_BASE}.decompressed.bin").read_bytes()
    manifest = json.loads((F104_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert len(f104_raw) == len(f103_raw)
    assert manifest["patch"]["cpio"]["delta_bytes"] == 0
    assert manifest["patch"]["cpio"]["old_end"] == manifest["patch"]["cpio"]["new_end"]
    assert manifest["persistent_entry_contract"]["result"] == "PASS"
    assert manifest["bootbase_contract"]["result"] == "PASS"

    before = entries_by_name(f103_raw)
    after = entries_by_name(f104_raw)
    assert before.keys() == after.keys()
    changed = [name for name in before if before[name] != after[name]]
    assert changed == [PATCH_ENTRY]


def test_f104_loader_enables_be_guard16_and_keeps_f103_rate_crypto_profile() -> None:
    f104_raw = (F104_BUILD / f"{F104_BASE}.decompressed.bin").read_bytes()
    loader = entries_by_name(f104_raw)[PATCH_ENTRY].decode("ascii")
    assert "swenc=0" in loader
    assert "hgw500_force_data_mcs7=1" in loader
    assert "hgw500_force_data_mcs15=0" in loader
    assert "hgw500_tx_reclaim_poll=1" in loader
    assert "hgw500_tx_queue_guard=1 hgw500_tx_queue_guard_high=16 hgw500_tx_queue_guard_low=8  hgw500_tx_reclaim_poll=1" in loader
    assert "hgw500_txbd_be_legacy64=N hgw500_tx_queue_guard=Y" in loader
    assert "hgw500_tx_queue_guard_high=16 hgw500_tx_queue_guard_low=8" in loader
    assert "hgw500_txbd_final_readback=N hgw500_tx_reclaim_poll=Y" in loader


def test_f104_keeps_f103_dtb_modules_and_emac_threshold_patch() -> None:
    f103_raw = (F103_BUILD / f"{F103_BASE}.decompressed.bin").read_bytes()
    f104_raw = (F104_BUILD / f"{F104_BASE}.decompressed.bin").read_bytes()
    assert f103_raw.count(F103_EMAC_CONTEXT) == 1
    assert f104_raw.count(F103_EMAC_CONTEXT) == 1
    assert f104_raw.count(F101_EMAC_CONTEXT) == 0

    f103_dtb = (F103_BUILD / f"{F103_BASE}.dtb").read_bytes()
    f104_dtb = (F104_BUILD / f"{F104_BASE}.dtb").read_bytes()
    assert f104_dtb == f103_dtb
    assert b"qtn,irq-poll-fallback" in f104_dtb

    before = entries_by_name(f103_raw)
    after = entries_by_name(f104_raw)
    for module in (
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko",
    ):
        assert before[module] == after[module]

