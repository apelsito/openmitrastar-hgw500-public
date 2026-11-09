#!/usr/bin/env python3
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILDER = ROOT / "tools/build_f100_2g_mcs7_fixedrate_quiet_from_f99.py"
F99_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f99-2g-mcs7-fixedrate-from-f98/build"
F99_BASE = "openmitrastar-linux510-q3-persistent-f99-2g-mcs7-fixedrate-from-f98-LZMA-OFFLINE-NO-FLASH"
F100_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f100-2g-mcs7-fixedrate-quiet-from-f99/build"
F100_BASE = "openmitrastar-linux510-q3-persistent-f100-2g-mcs7-fixedrate-quiet-from-f99-LZMA-OFFLINE-NO-FLASH"


def test_f100_builder_reuses_f99_cpio_logic_with_f100_bundle() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "build_f99_2g_mcs7_fixedrate_from_f98" in text
    assert "f100-2g-mcs7-fixedrate-quiet-from-f99" in text
    assert "q3-persistent-composite-f99-2g-mcs7-fixedrate-from-f98" in text
    assert "all64-mcs7-fixedrate-quiet-f100-RAM-ONLY-NO-FLASH" in text
    assert "hgw500_mgmt_trace=0 default" in text


def test_f100_artifact_preserves_f99_payload_layout() -> None:
    f99_raw = F99_BUILD / f"{F99_BASE}.decompressed.bin"
    f100_raw = F100_BUILD / f"{F100_BASE}.decompressed.bin"
    manifest = json.loads((F100_BUILD / "manifest.json").read_text(encoding="ascii"))
    source = f99_raw.read_bytes()
    candidate = f100_raw.read_bytes()
    assert len(candidate) == len(source) == 15_692_768
    source_start, _source_entries, source_remainder = f71.parse_first_cpio(source)
    candidate_start, _candidate_entries, candidate_remainder = f71.parse_first_cpio(candidate)
    assert candidate_start == source_start == manifest["patch"]["cpio"]["start"] == 8192
    assert candidate_remainder == source_remainder
    assert len(candidate) - len(candidate_remainder) == len(source) - len(source_remainder)
    assert manifest["patch"]["cpio"]["delta_bytes"] == 0
    assert manifest["patch"]["cpio"]["uncompensated_delta_bytes"] == 456
    assert manifest["patch"]["fixed_size_compensation"]["removed_bytes"] == 456
    assert manifest["persistent_entry_contract"]["result"] == "PASS"
    assert manifest["bootbase_contract"]["result"] == "PASS"


def test_f100_artifact_changes_only_rtl8192ee_hashes_and_compensation_json() -> None:
    f99_raw = (F99_BUILD / f"{F99_BASE}.decompressed.bin").read_bytes()
    f100_raw = (F100_BUILD / f"{F100_BASE}.decompressed.bin").read_bytes()
    _s1, f99_entries, _r1 = f71.parse_first_cpio(f99_raw)
    _s2, f100_entries, _r2 = f71.parse_first_cpio(f100_raw)
    before = {entry.name: entry.data for entry in f99_entries}
    after = {entry.name: entry.data for entry in f100_entries}
    changed = sorted(name for name in before if before[name] != after[name])
    assert changed == [
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        "usr/share/openmitrastar/q3-w3-direct-emac.json",
        "usr/share/openmitrastar/radio2g/artifacts.sha256",
        "usr/share/openmitrastar/radio2g/bundle-manifest.json",
    ]
    assert b"f014ad53084e1eb3cf7a9083913388ac907f0d254478dd63b0bc9ca054394e85" in after[
        "usr/share/openmitrastar/radio2g/artifacts.sha256"
    ]
    loader = after["usr/sbin/om-radio-modules"].decode("ascii")
    assert "hgw500_force_data_mcs7=1" in loader
    assert "hgw500_tx_reclaim_poll=1" in loader
    assert "hgw500_mgmt_trace=1" not in loader
    assert before["usr/sbin/om-radio-modules"] == after["usr/sbin/om-radio-modules"]


def test_f100_module_has_quiet_mgmt_trace_parameter_and_fixedrate_marker() -> None:
    module = ROOT / "outputs/kernel-port/realtek-loop/all64-mcs7-fixedrate-quiet-f100-RAM-ONLY-NO-FLASH/modules/rtl8192ee.ko"
    data = module.read_bytes()
    assert b"hgw500_mgmt_trace" in data
    assert b"Trace bounded HGW500 management RX/TX frames when explicitly enabled" in data
    assert b"fallback=0 dis_fb=1 pkt_bw=20 shortgi=0" in data
