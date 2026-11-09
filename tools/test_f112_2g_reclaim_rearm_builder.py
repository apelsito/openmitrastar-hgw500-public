#!/usr/bin/env python3
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILDER = ROOT / "tools/build_f112_2g_reclaim_rearm_from_f111.py"
F111_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f111-5g-power-md5-fixed-from-f110/build"
F111_BASE = "openmitrastar-linux510-q3-persistent-f111-5g-power-md5-fixed-from-f110-LZMA-OFFLINE-NO-FLASH"
F112_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f112-2g-be-reclaim-rearm-from-f111/build"
F112_BASE = "openmitrastar-linux510-q3-persistent-f112-2g-be-reclaim-rearm-from-f111-LZMA-OFFLINE-NO-FLASH"
RTL_PCI_ENTRY = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko"
RTL8192EE_ENTRY = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko"
QDRV_ENTRY = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko"
RADIO5_START = "usr/sbin/om-radio5-start"


def entries_by_name(raw: bytes) -> dict[str, bytes]:
    _start, entries, _remainder = f71.parse_first_cpio(raw)
    return {entry.name: entry.data for entry in entries}


def test_f112_builder_scope_is_f111_plus_rtl_pci_rearm_only() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "f112-2g-be-reclaim-rearm-from-f111" in text
    assert "q3-persistent-composite-f111-5g-power-md5-fixed-from-f110" in text
    assert "all64-mcs7-be-reclaim-rearm-f106" in text
    assert "replaced only rtl_pci.ko" in text


def test_f112_preserves_payload_shape_and_boot_contracts() -> None:
    f111_raw = (F111_BUILD / f"{F111_BASE}.decompressed.bin").read_bytes()
    f112_raw = (F112_BUILD / f"{F112_BASE}.decompressed.bin").read_bytes()
    manifest = json.loads((F112_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert len(f112_raw) == len(f111_raw)
    assert manifest["patch"]["cpio"]["delta_bytes"] == 0
    assert manifest["patch"]["cpio"]["old_end"] == manifest["patch"]["cpio"]["new_end"]
    assert manifest["persistent_entry_contract"]["result"] == "PASS"
    assert manifest["bootbase_contract"]["result"] == "PASS"


def test_f112_replaces_only_2g_rtl_pci_and_metadata() -> None:
    before = entries_by_name((F111_BUILD / f"{F111_BASE}.decompressed.bin").read_bytes())
    after = entries_by_name((F112_BUILD / f"{F112_BASE}.decompressed.bin").read_bytes())
    changed = {name for name in before if before[name] != after[name]}
    assert RTL_PCI_ENTRY in changed
    assert "usr/share/openmitrastar/radio2g/artifacts.sha256" in changed
    assert "usr/share/openmitrastar/radio2g/bundle-manifest.json" in changed
    assert RTL8192EE_ENTRY not in changed
    assert QDRV_ENTRY not in changed
    assert RADIO5_START not in changed


def test_f112_keeps_f111_loader_policy_and_radio5_fix() -> None:
    after = entries_by_name((F112_BUILD / f"{F112_BASE}.decompressed.bin").read_bytes())
    loader = after["usr/sbin/om-radio-modules"].decode("ascii")
    radio5_start = after[RADIO5_START].decode("ascii")
    assert "swenc=0" in loader
    assert "hgw500_force_data_mcs7=1" in loader
    assert "hgw500_force_data_mcs15=0" in loader
    assert "hgw500_tx_queue_guard=1 hgw500_tx_queue_guard_high=16 hgw500_tx_queue_guard_low=8  hgw500_tx_reclaim_poll=1" in loader
    assert "power_sha=$(sha256sum /etc/power_tables/tx_power_QSR1000_es.txt" in radio5_start
    assert "power_md5=1a3e318227fdc19079418f847d3e2ee8" in radio5_start


def test_f112_embeds_rearm_module() -> None:
    manifest = json.loads((F112_BUILD / "manifest.json").read_text(encoding="ascii"))
    after = entries_by_name((F112_BUILD / f"{F112_BASE}.decompressed.bin").read_bytes())
    rtl_pci = after[RTL_PCI_ENTRY]
    new_hash = manifest["realtek_bundle"]["rtl_pci_sha256"]
    assert f71.sha256(rtl_pci) == new_hash
    assert b"OMRTLQGUARD stage=reclaim-rearm" in rtl_pci
    assert b"OMRTLQGUARD stage=reclaim-kick" not in rtl_pci
