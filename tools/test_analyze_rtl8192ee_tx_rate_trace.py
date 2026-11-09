#!/usr/bin/env python3
import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("rate_trace", ROOT / "tools/analyze_rtl8192ee_tx_rate_trace.py")
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def test_analyze_descriptor_and_firmware_rates() -> None:
    raw = """
OMRTLRA stage=tx-desc event=1 len=1500 tid=0 macid=2 ratr=1 hw_rate=27 use_rate=0 dis_fb=0 ampdu=1 shortgi=1 pkt_bw=0 bw40=0 qsel=0 d0=0 d1=0 d2=0 d3=0 d4=0 d5=0
OMRTLRA stage=fw-report event=1 len=4 rate=27 sgi=0 macid=2 collision=1 raw=1b:02:00:01
OMRTLRA stage=fw-report event=2 len=4 rate=19 sgi=0 macid=2 collision=0 raw=13:02:00:00
"""
    result = MODULE.analyze(raw)
    assert result["status"] == "FW_RATE_OBSERVED"
    assert result["tx_descriptor_events"] == 1
    assert result["firmware_rate_histogram"] == {"MCS15": 1, "MCS7": 1}
    assert result["firmware_collision_events"] == 1
    assert result["descriptor_ampdu_events"] == 1
    assert result["descriptor_forced_rate_events"] == 0
    assert result["observed_hw_rate_hints"] == {"MCS15": 1}
    assert result["descriptor_tx_rate_histogram"] == {"1M": 1}


def test_empty_trace_is_explicit() -> None:
    result = MODULE.analyze("unrelated\n")
    assert result["status"] == "NO_RATE_TRACE"
    assert result["firmware_ra_events"] == 0
