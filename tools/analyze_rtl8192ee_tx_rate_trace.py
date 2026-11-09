#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import re


TX_RE = re.compile(
    r"OMRTLRA stage=tx-desc event=(?P<event>\d+) len=(?P<len>\d+) tid=(?P<tid>\d+) "
    r"macid=(?P<macid>\d+) ratr=(?P<ratr>\d+) hw_rate=(?P<hw_rate>\d+) "
    r"use_rate=(?P<use_rate>[01]) dis_fb=(?P<dis_fb>[01]) ampdu=(?P<ampdu>[01]) "
    r"shortgi=(?P<shortgi>[01]) pkt_bw=(?P<pkt_bw>\d+) bw40=(?P<bw40>\d+) "
    r"qsel=(?P<qsel>\d+) d0=(?P<d0>[0-9a-fA-F]+) d1=(?P<d1>[0-9a-fA-F]+) "
    r"d2=(?P<d2>[0-9a-fA-F]+) d3=(?P<d3>[0-9a-fA-F]+) "
    r"d4=(?P<d4>[0-9a-fA-F]+) d5=(?P<d5>[0-9a-fA-F]+)"
)
FW_RE = re.compile(
    r"OMRTLRA stage=fw-report event=(?P<event>\d+) len=(?P<len>\d+) "
    r"rate=(?P<rate>\d+) sgi=(?P<sgi>[01]) macid=(?P<macid>\d+) "
    r"collision=(?P<collision>[01])"
)


def rate_name(rate: int) -> str:
    legacy = ["1M", "2M", "5.5M", "11M", "6M", "9M", "12M", "18M", "24M", "36M", "48M", "54M"]
    if 0 <= rate < len(legacy):
        return legacy[rate]
    if 0x0C <= rate <= 0x1B:
        return f"MCS{rate - 0x0C}"
    return f"RATE_{rate}"


def analyze(raw: str) -> dict:
    tx = []
    for match in TX_RE.finditer(raw):
        item = {
            key: int(value, 16) if key.startswith("d") else int(value)
            for key, value in match.groupdict().items()
        }
        item["descriptor_tx_rate"] = item["d4"] & 0x7F
        tx.append(item)
    fw = [{key: int(value) for key, value in match.groupdict().items()} for match in FW_RE.finditer(raw)]
    rates = Counter(rate_name(item["rate"]) for item in fw)
    macids = Counter(str(item["macid"]) for item in fw)
    return {
        "schema": "openmitrastar.rtl8192ee-tx-rate-trace-analysis/v1",
        "status": "FW_RATE_OBSERVED" if fw else "DESCRIPTOR_ONLY" if tx else "NO_RATE_TRACE",
        "tx_descriptor_events": len(tx),
        "firmware_ra_events": len(fw),
        "firmware_rate_histogram": dict(sorted(rates.items())),
        "firmware_macid_histogram": dict(sorted(macids.items())),
        "firmware_collision_events": sum(item["collision"] for item in fw),
        "descriptor_ampdu_events": sum(item["ampdu"] for item in tx),
        "descriptor_forced_rate_events": sum(item["use_rate"] for item in tx),
        "descriptor_rate_fallback_disabled_events": sum(item["dis_fb"] for item in tx),
        "descriptor_shortgi_requested_events": sum(item["shortgi"] for item in tx),
        "descriptor_bw40_events": sum(bool(item["bw40"]) for item in tx),
        "observed_hw_rate_hints": dict(sorted(Counter(rate_name(item["hw_rate"]) for item in tx).items())),
        "descriptor_tx_rate_histogram": dict(
            sorted(Counter(rate_name(item["descriptor_tx_rate"]) for item in tx).items())
        ),
        "mutations": False,
        "hardware_accessed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = analyze(args.log.read_text(encoding="utf-8", errors="replace"))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if result["status"] != "NO_RATE_TRACE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
