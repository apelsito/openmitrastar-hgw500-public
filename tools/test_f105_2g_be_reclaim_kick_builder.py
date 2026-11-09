#!/usr/bin/env python3
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILDER = ROOT / "tools/build_f105_2g_be_reclaim_kick_from_f104.py"
F104_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f104-2g-be-guard16-from-f103/build"
F104_BASE = "openmitrastar-linux510-q3-persistent-f104-2g-be-guard16-from-f103-LZMA-OFFLINE-NO-FLASH"
F105_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f105-2g-be-reclaim-kick-from-f104/build"
F105_BASE = "openmitrastar-linux510-q3-persistent-f105-2g-be-reclaim-kick-from-f104-LZMA-OFFLINE-NO-FLASH"
RTL_PCI_ENTRY = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko"


def entries_by_name(raw: bytes) -> dict[str, bytes]:
    _start, entries, _remainder = f71.parse_first_cpio(raw)
    return {entry.name: entry.data for entry in entries}


def test_f105_builder_scope_is_rtl_pci_reclaim_kick_only() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "f105-2g-be-reclaim-kick-from-f104" in text
    assert "replaced only rtl_pci.ko" in text
    assert "schedule_delayed_work return 0" in text
    assert "qdrv" in text
    assert "flash\": False" in text
    assert "opens_uart\": False" in text


def test_f105_preserves_payload_shape_and_boot_contracts() -> None:
    f104_raw = (F104_BUILD / f"{F104_BASE}.decompressed.bin").read_bytes()
    f105_raw = (F105_BUILD / f"{F105_BASE}.decompressed.bin").read_bytes()
    manifest = json.loads((F105_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert len(f105_raw) == len(f104_raw)
    assert manifest["patch"]["cpio"]["delta_bytes"] == 0
    assert manifest["patch"]["cpio"]["old_end"] == manifest["patch"]["cpio"]["new_end"]
    assert manifest["persistent_entry_contract"]["result"] == "PASS"
    assert manifest["bootbase_contract"]["result"] == "PASS"


def test_f105_replaces_only_rtl_pci_and_inert_hash_jsons() -> None:
    before = entries_by_name((F104_BUILD / f"{F104_BASE}.decompressed.bin").read_bytes())
    after = entries_by_name((F105_BUILD / f"{F105_BASE}.decompressed.bin").read_bytes())
    changed = {name for name in before if before[name] != after[name]}
    assert RTL_PCI_ENTRY in changed
    assert "usr/share/openmitrastar/radio2g/artifacts.sha256" in changed
    assert "usr/share/openmitrastar/radio2g/bundle-manifest.json" in changed
    assert "usr/share/openmitrastar/radio5g/q3-dual-radio-build-manifest.json" in changed
    assert "usr/share/openmitrastar/cgi-overlay-v1.json" in changed
    assert "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko" not in changed
    assert "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko" not in changed


def test_f105_loader_keeps_f104_runtime_policy() -> None:
    after = entries_by_name((F105_BUILD / f"{F105_BASE}.decompressed.bin").read_bytes())
    loader = after["usr/sbin/om-radio-modules"].decode("ascii")
    assert "profile=all64-mcs7-eapol-mgntq-guard16-nosplit" in loader
    assert "swenc=0" in loader
    assert "hgw500_force_data_mcs7=1" in loader
    assert "hgw500_force_data_mcs15=0" in loader
    assert "hgw500_tx_queue_guard=1 hgw500_tx_queue_guard_high=16 hgw500_tx_queue_guard_low=8  hgw500_tx_reclaim_poll=1" in loader


def test_f105_embeds_reclaim_kick_module_and_hashes() -> None:
    manifest = json.loads((F105_BUILD / "manifest.json").read_text(encoding="ascii"))
    after = entries_by_name((F105_BUILD / f"{F105_BASE}.decompressed.bin").read_bytes())
    rtl_pci = after[RTL_PCI_ENTRY]
    new_hash = manifest["realtek_bundle"]["rtl_pci_sha256"]
    assert f71.sha256(rtl_pci) == new_hash
    assert b"OMRTLQGUARD stage=reclaim-kick" in rtl_pci
    hashes = after["usr/share/openmitrastar/radio2g/artifacts.sha256"].decode("ascii")
    assert f"{new_hash} /{RTL_PCI_ENTRY}" in hashes

    bundle_manifest = json.loads(after["usr/share/openmitrastar/radio2g/bundle-manifest.json"].decode("ascii"))
    rtl_pci_nodes = [
        item for item in bundle_manifest["artifacts"]
        if item.get("path") == "modules/rtl_pci.ko"
    ]
    assert rtl_pci_nodes == [{
        "bytes": len(rtl_pci),
        "path": "modules/rtl_pci.ko",
        "sha256": new_hash,
    }]
