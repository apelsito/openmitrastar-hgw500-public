#!/usr/bin/env python3
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILDER = ROOT / "tools/build_f99_2g_mcs7_fixedrate_from_f98.py"
F98_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f98-2g-reclaim-poll-from-f97/build"
F98_BASE = "openmitrastar-linux510-q3-persistent-f98-2g-reclaim-poll-from-f97-LZMA-OFFLINE-NO-FLASH"
F99_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f99-2g-mcs7-fixedrate-from-f98/build"
F99_BASE = "openmitrastar-linux510-q3-persistent-f99-2g-mcs7-fixedrate-from-f98-LZMA-OFFLINE-NO-FLASH"


def test_f99_builder_is_f98_scoped_and_replaces_only_rtl8192ee() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f98-2g-reclaim-poll-from-f97" in text
    assert 'BUILD_TAG = "f99-2g-mcs7-fixedrate-from-f98"' in text
    assert 'OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"' in text
    assert "all64-mcs7-fixedrate-f99-RAM-ONLY-NO-FLASH" in text
    assert 'RTL8192EE_ENTRY = "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko"' in text
    replacements = text.partition("MODULE_REPLACEMENTS = {")[2].partition("}")[0]
    assert "RTL8192EE_ENTRY" in replacements
    assert "modules/rtl8192ee.ko" in replacements
    assert "radio2g/rtl_pci.ko" not in replacements
    assert "radio5g/qdrv.ko" not in replacements
    assert "usr/sbin/om-radio-modules" not in replacements


def test_f99_builder_preserves_loader_and_flash_disabled() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "radio2g_loader" in text
    assert "unchanged from F98" in text
    assert "hgw500_force_data_mcs7=1" in text
    assert "hgw500_tx_reclaim_poll=1" in text
    assert '"touches_router": False' in text
    assert '"opens_uart": False' in text
    assert '"flash": False' in text


def test_f99_artifact_preserves_f98_payload_layout() -> None:
    f98_raw = F98_BUILD / f"{F98_BASE}.decompressed.bin"
    f99_raw = F99_BUILD / f"{F99_BASE}.decompressed.bin"
    manifest = json.loads((F99_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert f98_raw.is_file()
    assert f99_raw.is_file()
    source = f98_raw.read_bytes()
    candidate = f99_raw.read_bytes()
    assert len(candidate) == len(source) == 15_692_768
    source_start, _source_entries, source_remainder = f71.parse_first_cpio(source)
    candidate_start, _candidate_entries, candidate_remainder = f71.parse_first_cpio(candidate)
    assert candidate_start == source_start == manifest["patch"]["cpio"]["start"] == 8192
    assert len(candidate) - len(candidate_remainder) == len(source) - len(source_remainder)
    assert candidate_remainder == source_remainder
    assert manifest["patch"]["cpio"]["delta_bytes"] == 0
    assert manifest["patch"]["cpio"]["uncompensated_delta_bytes"] == 716
    assert manifest["patch"]["fixed_size_compensation"]["removed_bytes"] == 716
    assert manifest["persistent_entry_contract"]["result"] == "PASS"
    assert manifest["bootbase_contract"]["result"] == "PASS"


def test_f99_artifact_changes_only_rtl8192ee_hashes_and_inert_json() -> None:
    f98_raw = (F98_BUILD / f"{F98_BASE}.decompressed.bin").read_bytes()
    f99_raw = (F99_BUILD / f"{F99_BASE}.decompressed.bin").read_bytes()
    _s1, f98_entries, _r1 = f71.parse_first_cpio(f98_raw)
    _s2, f99_entries, _r2 = f71.parse_first_cpio(f99_raw)
    before = {entry.name: entry.data for entry in f98_entries}
    after = {entry.name: entry.data for entry in f99_entries}
    changed = sorted(name for name in before if before[name] != after[name])
    assert changed == [
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        "usr/share/openmitrastar/q3-w3-direct-emac.json",
        "usr/share/openmitrastar/radio2g/artifacts.sha256",
    ]
    assert b"956bcf2ab4c9369514951efc5edc56615755c31a3a0b3f557328609b8855b177" in after[
        "usr/share/openmitrastar/radio2g/artifacts.sha256"
    ]
    assert b"540c14deace13342e978891085e00c4cc3f085de926f4c66cce76dc28f0bc432" not in after[
        "usr/share/openmitrastar/radio2g/artifacts.sha256"
    ]
    loader = after["usr/sbin/om-radio-modules"].decode("ascii")
    assert "hgw500_force_data_mcs7=1" in loader
    assert "hgw500_tx_reclaim_poll=1" in loader
    assert before["usr/sbin/om-radio-modules"] == after["usr/sbin/om-radio-modules"]


def test_f99_module_contains_fixedrate_marker() -> None:
    module = ROOT / "outputs/kernel-port/realtek-loop/all64-mcs7-fixedrate-f99-RAM-ONLY-NO-FLASH/modules/rtl8192ee.ko"
    data = module.read_bytes()
    assert b"fallback=0 dis_fb=1 pkt_bw=20 shortgi=0" in data
    assert b"hgw500_force_data_mcs7" in data
