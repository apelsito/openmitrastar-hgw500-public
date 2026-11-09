#!/usr/bin/env python3
"""Evaluate qdrv scheduler TX stages using skb as the primary identity."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


STAGES = (
    "enqueue",
    "enqueue-result",
    "dequeue-ready",
    "hardstart",
    "desc-ready",
    "mailbox-enter",
    "mailbox-published",
    "txdone",
)
EVENT = re.compile(r"OMQDRVTXPATH stage=([a-z-]+)\s+([^\r\n]+)")
FIELD = re.compile(r"([a-z_]+)=([^\s]+)")
AUC_MODE = re.compile(r"OMRADIO5_AUC_TX_MODE mode=([a-z]+) value=(\d+)")


def parse(text: str) -> dict[str, object]:
    packet_events: dict[str, list[dict[str, str]]] = {}
    packet_order: list[str] = []
    dequeue_snapshots: list[dict[str, str]] = []

    for match in EVENT.finditer(text):
        stage = match.group(1)
        fields = dict(FIELD.findall(match.group(2)))
        fields["stage"] = stage
        fields["offset"] = str(match.start())
        if stage == "dequeue-enter":
            dequeue_snapshots.append(fields)
            continue
        skb = fields.get("skb")
        if not skb or stage not in STAGES:
            continue
        if skb not in packet_events:
            packet_events[skb] = []
            packet_order.append(skb)
        packet_events[skb].append(fields)

    packets: list[dict[str, object]] = []
    for skb in packet_order:
        events = packet_events[skb]
        expected = 0
        observed: list[str] = []
        hd_pa: str | None = None
        hd_mismatch = False
        for event in events:
            stage = event["stage"]
            if expected >= len(STAGES) or stage != STAGES[expected]:
                continue
            if stage in {"desc-ready", "mailbox-enter", "mailbox-published", "txdone"}:
                candidate = event.get("hd_pa")
                if not candidate:
                    hd_mismatch = True
                    break
                if hd_pa is None:
                    hd_pa = candidate
                elif candidate != hd_pa:
                    hd_mismatch = True
                    break
            observed.append(stage)
            expected += 1
        first_missing = STAGES[len(observed)] if len(observed) < len(STAGES) else None
        first = events[0]
        packets.append({
            "skb": skb,
            "proto": first.get("proto"),
            "len": first.get("len"),
            "mgmt": first.get("mgmt"),
            "fc": first.get("fc"),
            "hd_pa": hd_pa,
            "stages": observed,
            "frontier": observed[-1] if observed else "UNOBSERVED",
            "first_missing_transition": first_missing,
            "complete": observed == list(STAGES),
            "identity_mismatch": hd_mismatch,
        })

    best = max(packets, key=lambda item: len(item["stages"]), default=None)
    auc = AUC_MODE.search(text)
    return {
        "schema": "openmitrastar.qtn-5g-v6-scheduler-evaluation/v1",
        "auc_tx_mode": (
            {"mode": auc.group(1), "value": int(auc.group(2))} if auc else None
        ),
        "packet_count": len(packets),
        "best_packet": best,
        "packets": packets,
        "dequeue_snapshots": dequeue_snapshots,
        "queue_enabled_values": sorted({
            item["queue_enabled"] for item in dequeue_snapshots if "queue_enabled" in item
        }),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("uart_log", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = parse(args.uart_log.read_text(encoding="utf-8-sig", errors="replace"))
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
