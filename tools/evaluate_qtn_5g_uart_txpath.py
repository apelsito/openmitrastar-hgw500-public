#!/usr/bin/env python3
"""Evaluate one Quantenna TXPATH run from out-of-band UART evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re


STAGES = (
    "enqueue",
    "hardstart",
    "desc-ready",
    "mailbox-enter",
    "mailbox-published",
    "txdone",
)
OBSERVED_STAGES = ("dequeue-enter",) + STAGES
RUN_BEGIN = re.compile(r"OMQTN5G_RUN stage=begin run_id=([A-Za-z0-9._-]+)")
TXPATH = re.compile(r"OMQDRVTXPATH stage=([a-z-]+)\s+([^\r\n]+)")
FIELD = re.compile(r"([a-z_]+)=([^\s]+)")
FATAL = re.compile(
    r"MuC:.*exception|MuC exception|MuC has halted|Kernel panic|Oops|BUG:|"
    r"Unable to handle|EV_TLB|EV_ProtV|Misaligned Access",
    re.I,
)


def run_window(text: str, run_id: str) -> tuple[str, int, int]:
    matches = list(RUN_BEGIN.finditer(text))
    selected = next((match for match in matches if match.group(1) == run_id), None)
    if selected is None:
        return "", -1, -1
    later = next((match for match in matches if match.start() > selected.start()), None)
    end = later.start() if later else len(text)
    return text[selected.start():end], selected.start(), end


def load_capture_events(path: Path | None) -> list[dict]:
    if not path or not path.is_file():
        return []
    events = []
    for line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def parse_tx_events(window: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for match in TXPATH.finditer(window):
        fields = dict(FIELD.findall(match.group(2)))
        fields["stage"] = match.group(1)
        fields["offset"] = str(match.start())
        events.append(fields)
    return events


def packet_frontiers(events: list[dict[str, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple[str, str, str], list[dict[str, str]]] = {}
    order: list[tuple[str, str, str]] = []
    for event in events:
        key = (event.get("seq", "?"), event.get("proto", "?"), event.get("len", "?"))
        if key not in grouped:
            grouped[key] = []
            order.append(key)
        grouped[key].append(event)

    results = []
    for key in order:
        expected_index = 0
        observed: list[str] = []
        hd_pa: str | None = None
        mismatch = False
        for event in grouped[key]:
            stage = event["stage"]
            if stage == "dequeue-enter":
                if not observed:
                    observed.append(stage)
                continue
            if expected_index >= len(STAGES) or stage != STAGES[expected_index]:
                continue
            candidate_hd = event.get("hd_pa")
            if stage in {"desc-ready", "mailbox-enter", "mailbox-published", "txdone"}:
                if not candidate_hd:
                    mismatch = True
                    break
                if hd_pa is None:
                    hd_pa = candidate_hd
                elif candidate_hd != hd_pa:
                    mismatch = True
                    break
            observed.append(stage)
            expected_index += 1
        results.append({
            "seq": key[0],
            "proto": key[1],
            "len": key[2],
            "hd_pa": hd_pa,
            "stages": observed,
            "frontier": observed[-1] if observed else "UNOBSERVED",
            "complete": [stage for stage in observed if stage != "dequeue-enter"] == list(STAGES),
            "identity_mismatch": mismatch,
        })
    return results


def evaluate(text: str, run_id: str, capture_events: list[dict], one_shot_rc: int,
             post_recovery: dict | None = None) -> dict[str, object]:
    window, start, end = run_window(text, run_id)
    ready = any(event.get("stage") in {"ready", "reconnected"} for event in capture_events)
    gap_offsets = [
        int(event.get("bytes", -1)) for event in capture_events
        if event.get("stage") == "port-lost"
    ]
    gap_in_critical_window = start >= 0 and any(start <= offset <= end for offset in gap_offsets)
    events = parse_tx_events(window)
    packets = packet_frontiers(events)
    best = max(packets, key=lambda packet: len(packet["stages"]), default=None)
    ordered_events = [event["stage"] for event in events if event["stage"] in OBSERVED_STAGES]
    reset_seen = bool(re.search(r"reboot: Restarting system|Boot reached stage 13", window))
    recovery_seen = "OMSSH_READY port=22" in window
    rollback_match = re.search(
        rf"OMRADIO5_ROLLBACK_COMPLETE run_id={re.escape(run_id)} "
        r"stop_rc=(\d+) loglevel_restore_rc=(\d+) eth0_2g=preserved",
        window,
    )
    rollback_complete = rollback_match is not None
    rollback_codes_ok = bool(
        rollback_match
        and rollback_match.group(1) == "0"
        and rollback_match.group(2) == "0"
    )
    committed = f"OMQTN5G_RUN stage=commit run_id={run_id}" in window
    fatal_markers = sorted(set(match.group(0) for match in FATAL.finditer(window)))
    post_recovery = post_recovery or {}
    management_ok = post_recovery.get("management_ok") is True
    recovery_clean = post_recovery.get("recovery_clean") is True
    loglevel_restored = post_recovery.get("loglevel_matches_original") is True

    capture_valid = start >= 0 and ready and not gap_in_critical_window
    if not capture_valid:
        terminal = "CAPTURE_INVALID"
    elif committed and best and best["complete"] and not fatal_markers and one_shot_rc == 0 and management_ok:
        terminal = "PASS_COMMITTED"
    elif (rollback_complete and rollback_codes_ok and not reset_seen
          and management_ok and recovery_clean and loglevel_restored):
        terminal = "FAIL_ROLLED_BACK"
    elif reset_seen and recovery_seen and management_ok and recovery_clean:
        terminal = "FAIL_RECOVERED_AFTER_REBOOT"
    else:
        terminal = "FAIL_RECOVERY_UNPROVEN"

    return {
        "schema": "openmitrastar.qtn-5g-uart-txpath-evaluation/v1",
        "run_id": run_id,
        "terminal_state": terminal,
        "capture": {
            "ready": ready,
            "valid": capture_valid,
            "gap_in_critical_window": gap_in_critical_window,
            "window_start": start,
            "window_end": end,
        },
        "txpath": {
            "first_marker": ordered_events[0] if ordered_events else "UNOBSERVED",
            "last_marker": ordered_events[-1] if ordered_events else "UNOBSERVED",
            "event_count": len(ordered_events),
            "best_packet": best,
            "packets": packets,
        },
        "rollback_complete": rollback_complete,
        "rollback_codes_ok": rollback_codes_ok,
        "rollback_stop_rc": int(rollback_match.group(1)) if rollback_match else None,
        "rollback_loglevel_restore_rc": int(rollback_match.group(2)) if rollback_match else None,
        "reset_seen": reset_seen,
        "recovery_seen": recovery_seen,
        "fatal_markers": fatal_markers,
        "one_shot_rc": one_shot_rc,
        "post_recovery": post_recovery,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--uart-log", type=Path, required=True)
    parser.add_argument("--uart-events", type=Path)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--one-shot-rc", type=int, required=True)
    parser.add_argument("--post-recovery-json", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    text = args.uart_log.read_text(encoding="utf-8-sig", errors="replace")
    post_recovery = (
        json.loads(args.post_recovery_json.read_text(encoding="utf-8-sig"))
        if args.post_recovery_json else None
    )
    result = evaluate(
        text, args.run_id, load_capture_events(args.uart_events),
        args.one_shot_rc, post_recovery,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["terminal_state"] == "PASS_COMMITTED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
