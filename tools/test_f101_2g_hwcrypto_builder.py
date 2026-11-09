#!/usr/bin/env python3
from pathlib import Path
import json
import sys


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import build_f71_qcsapi_interp_from_f70 as f71


BUILDER = ROOT / "tools/build_f101_2g_hwcrypto_from_f100.py"
F100_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f100-2g-mcs7-fixedrate-quiet-from-f99/build"
F100_BASE = "openmitrastar-linux510-q3-persistent-f100-2g-mcs7-fixedrate-quiet-from-f99-LZMA-OFFLINE-NO-FLASH"
F101_BUILD = ROOT / "work/mission-state/q3-persistent-composite-f101-2g-hwcrypto-from-f100/build"
F101_BASE = "openmitrastar-linux510-q3-persistent-f101-2g-hwcrypto-from-f100-LZMA-OFFLINE-NO-FLASH"


def test_f101_builder_is_loader_only_hwcrypto_scope() -> None:
    text = BUILDER.read_text(encoding="ascii")
    assert "q3-persistent-composite-f100-2g-mcs7-fixedrate-quiet-from-f99" in text
    assert "f101-2g-hwcrypto-from-f100" in text
    assert "swenc=1" in text
    assert "swenc=0" in text
    assert "swenc=Y" in text
    assert "swenc=N" in text
    assert "radio2g_modules" in text
    assert "unchanged from F100" in text
    assert "radio5_modules" in text
    assert "qdrv" in text
    assert "touches_router\": False" in text
    assert "opens_uart\": False" in text
    assert "flash\": False" in text


def test_f101_artifact_preserves_f100_payload_layout() -> None:
    f100_raw = F100_BUILD / f"{F100_BASE}.decompressed.bin"
    f101_raw = F101_BUILD / f"{F101_BASE}.decompressed.bin"
    manifest = json.loads((F101_BUILD / "manifest.json").read_text(encoding="ascii"))
    source = f100_raw.read_bytes()
    candidate = f101_raw.read_bytes()
    assert len(candidate) == len(source)
    source_start, _source_entries, source_remainder = f71.parse_first_cpio(source)
    candidate_start, _candidate_entries, candidate_remainder = f71.parse_first_cpio(candidate)
    assert candidate_start == source_start == manifest["patch"]["cpio"]["start"]
    assert len(candidate) - len(candidate_remainder) == len(source) - len(source_remainder)
    assert candidate_remainder == source_remainder
    assert manifest["patch"]["cpio"]["delta_bytes"] == 0
    assert manifest["persistent_entry_contract"]["result"] == "PASS"
    assert manifest["bootbase_contract"]["result"] == "PASS"


def test_f101_artifact_changes_only_loader_entry_and_keeps_modules() -> None:
    f100_raw = (F100_BUILD / f"{F100_BASE}.decompressed.bin").read_bytes()
    f101_raw = (F101_BUILD / f"{F101_BASE}.decompressed.bin").read_bytes()
    _s1, f100_entries, _r1 = f71.parse_first_cpio(f100_raw)
    _s2, f101_entries, _r2 = f71.parse_first_cpio(f101_raw)
    before = {entry.name: entry.data for entry in f100_entries}
    after = {entry.name: entry.data for entry in f101_entries}
    changed = sorted(name for name in before if before[name] != after[name])
    assert changed == ["usr/sbin/om-radio-modules"]
    loader = after["usr/sbin/om-radio-modules"].decode("ascii")
    assert "swenc=0 disable_watchdog=0" in loader
    assert "msi=N dma64=N aspm=0 ips=N fwlps=N swenc=N" in loader
    assert "hgw500_force_data_mcs7=1" in loader
    assert "hgw500_tx_reclaim_poll=1" in loader
    for module in (
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl_pci.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio2g/rtl8192ee.ko",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko",
    ):
        assert before[module] == after[module]
