#!/usr/bin/env python3
"""Verify an offline HGW500 BE reclaim-poll hardware result.

The verifier reads only local artifacts.  It never contacts the router,
oracle laptop, UART, TFTP, MTD or flash.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CANDIDATE = ROOT / (
    "outputs/kernel-port/realtek-loop/"
    "txbd-readback-guard16-reclaim-poll-RAM-ONLY-NO-FLASH"
)
EXPECTED_RTL_PCI_SHA256 = "9a0c66835b9c135deb90382e0e325165b76a79982544e6c2ceacb663540c1ea8"
EXPECTED_RTL8192EE_SHA256 = "93a6e7da9d30fd14e0a94854dd74d3da42afaf7e97c57dfc891c63f64c187811"

STOP_RE = re.compile(
    r"OMRTLQGUARD stage=stop event=(?P<event>\d+) q=(?P<q>\d+) "
    r"queued=(?P<queued>\d+) high=(?P<high>\d+) rp=(?P<rp>\d+) wp=(?P<wp>\d+)"
)
ARM_RE = re.compile(
    r"OMRTLQGUARD stage=reclaim-arm q=(?P<q>\d+) queued=(?P<queued>\d+) "
    r"scheduled=(?P<scheduled>[01])"
)
POLL_RE = re.compile(
    r"OMRTLQGUARD stage=reclaim-poll event=(?P<event>\d+) q=(?P<q>\d+) "
    r"queued=(?P<before>\d+)->(?P<after>\d+) stopped=(?P<stopped>[01]) "
    r"rp=(?P<rp>\d+) wp=(?P<wp>\d+)"
)
WAKE_RE = re.compile(
    r"OMRTLQGUARD stage=wake event=(?P<event>\d+) q=(?P<q>\d+) "
    r"queued=(?P<queued>\d+) low=(?P<low>\d+) rp=(?P<rp>\d+) wp=(?P<wp>\d+)"
)
CURL_FIELD_RE = re.compile(r"(?:^|;)(?P<key>[A-Za-z_]+)=(?P<value>[^;]*)")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON root is not an object: {path}")
    return data


def ints(match: re.Match[str]) -> dict[str, int]:
    return {key: int(value) for key, value in match.groupdict().items()}


def parse_guard_events(raw: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    patterns = (("stop", STOP_RE), ("arm", ARM_RE), ("poll", POLL_RE), ("wake", WAKE_RE))
    for line_no, line in enumerate(raw.splitlines(), start=1):
        for kind, pattern in patterns:
            match = pattern.search(line)
            if match:
                events.append({"kind": kind, "line": line_no, **ints(match)})
                break
    return events


def forward_progress(old: int, new: int, ring_size: int = 512) -> int:
    return (new - old) % ring_size


def build_cycles(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stops = [index for index, event in enumerate(events) if event["kind"] == "stop"]
    cycles: list[dict[str, Any]] = []
    for stop_number, start in enumerate(stops):
        end = stops[stop_number + 1] if stop_number + 1 < len(stops) else len(events)
        window = events[start:end]
        stop = window[0]
        arms = [event for event in window if event["kind"] == "arm" and event["q"] == 1]
        polls = [event for event in window if event["kind"] == "poll" and event["q"] == 1]
        wakes = [event for event in window if event["kind"] == "wake" and event["q"] == 1]
        progress_events = [event for event in window if event["kind"] in ("poll", "wake")]
        rp_points = [stop["rp"]] + [event["rp"] for event in progress_events]
        rp_steps = [forward_progress(a, b) for a, b in zip(rp_points, rp_points[1:])]
        decreasing_poll = any(event["after"] < event["before"] for event in polls)
        wake_valid = any(event["queued"] <= event["low"] for event in wakes)
        final_poll_unstopped = bool(polls) and polls[-1]["stopped"] == 0
        complete = bool(arms and polls and wakes and wake_valid and final_poll_unstopped)
        cycles.append(
            {
                "number": stop_number + 1,
                "stop": stop,
                "arms": arms,
                "polls": polls,
                "wakes": wakes,
                "rp_steps": rp_steps,
                "rp_progress": any(step > 0 for step in rp_steps),
                "queue_decreased_in_poll": decreasing_poll,
                "wake_at_or_below_low": wake_valid,
                "final_poll_unstopped": final_poll_unstopped,
                "complete": complete,
            }
        )
    return cycles


def parse_curl_output(value: Any) -> dict[str, Any]:
    raw = str(value or "").strip()
    fields = {match["key"]: match["value"] for match in CURL_FIELD_RE.finditer(raw)}
    parsed: dict[str, Any] = {"raw": raw, **fields}
    for key in ("http", "bytes", "speed_Bps"):
        try:
            parsed[key] = int(float(fields.get(key, "0")))
        except ValueError:
            parsed[key] = 0
    try:
        parsed["seconds"] = float(fields.get("seconds", "0"))
    except ValueError:
        parsed["seconds"] = 0.0
    return parsed


def oracle_state(data: dict[str, Any], minimum_bytes: int) -> dict[str, Any]:
    schema = data.get("schema")
    curl = parse_curl_output(data.get("curl_output"))
    connected = data.get("connected") is True
    ipv4 = bool(str(data.get("wifi_ipv4") or "").strip())
    no_error = not data.get("error")
    ping = data.get("ping_pass") is True if schema == "openmitrastar.windows-wifi-oracle-roundtrip/v1" else True
    curl_ok = curl["http"] == 200 and curl["bytes"] >= minimum_bytes and curl["speed_Bps"] > 0
    return {
        "schema": schema,
        "connected": connected,
        "wifi_ipv4": data.get("wifi_ipv4"),
        "no_error": no_error,
        "ping_pass": ping,
        "curl": curl,
        "traffic_pass": connected and ipv4 and no_error and ping and curl_ok,
    }


def client_state(client: dict[str, Any] | None, traffic: dict[str, Any] | None) -> dict[str, Any]:
    sources = [item for item in (client, traffic) if isinstance(item, dict)]
    associated = any(
        item.get("association_observed") is True
        or int(item.get("max_associations", 0) or 0) > 0
        or (item.get("last_sample") or {}).get("kernel_associated") == 1
        for item in sources
    )
    authorized = any(
        item.get("authorization_observed") is True
        or int(item.get("max_authorized", 0) or 0) > 0
        or (item.get("last_sample") or {}).get("kernel_authorized") == 1
        for item in sources
    )
    traffic_ok = True
    if traffic is not None:
        traffic_ok = (
            int(traffic.get("wifi_tx_bytes_delta", 0) or 0) > 0
            and int(traffic.get("wifi_rx_bytes_delta", 0) or 0) > 0
            and int(traffic.get("fatal_markers_during_run", 1) or 0) == 0
            and traffic.get("ssh_alive_all_samples") is True
        )
    return {"associated": associated, "authorized": authorized, "monitor_traffic_pass": traffic_ok}


def audit_candidate(candidate: Path) -> dict[str, Any]:
    manifest_path = candidate / "manifest.json"
    rtl_pci = candidate / "modules/rtl_pci.ko"
    rtl8192ee = candidate / "modules/rtl8192ee.ko"
    sums_path = candidate / "SHA256SUMS"
    failures: list[str] = []
    try:
        manifest = load_json(manifest_path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {"pass": False, "failures": [f"manifest:{exc}"]}
    if manifest.get("schema") != "openmitrastar.realtek-be-reclaim-poll/v1":
        failures.append("candidate_schema")
    if manifest.get("classification") != "RAM-ONLY-NO-FLASH":
        failures.append("candidate_classification")
    if not rtl_pci.is_file() or sha256(rtl_pci) != EXPECTED_RTL_PCI_SHA256:
        failures.append("rtl_pci_hash")
    if not rtl8192ee.is_file() or sha256(rtl8192ee) != EXPECTED_RTL8192EE_SHA256:
        failures.append("rtl8192ee_hash")
    sums_checked = 0
    if not sums_path.is_file():
        failures.append("sha256sums_missing")
    else:
        for line in sums_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                expected, relative = line.split(None, 1)
            except ValueError:
                failures.append("sha256sums_format")
                continue
            artifact = candidate / relative.strip().lstrip("*")
            sums_checked += 1
            if not artifact.is_file():
                failures.append(f"sha256sums_missing:{relative.strip()}")
            elif sha256(artifact) != expected.lower():
                failures.append(f"sha256sums_mismatch:{relative.strip()}")
    return {
        "pass": not failures,
        "failures": failures,
        "manifest": str(manifest_path),
        "rtl_pci_sha256": sha256(rtl_pci) if rtl_pci.is_file() else None,
        "rtl8192ee_sha256": sha256(rtl8192ee) if rtl8192ee.is_file() else None,
        "sha256sums_checked": sums_checked,
    }


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--guard-log", type=Path, required=True)
    parser.add_argument("--oracle-json", type=Path, required=True)
    parser.add_argument("--client-json", type=Path)
    parser.add_argument("--traffic-json", type=Path)
    parser.add_argument("--candidate-dir", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--min-oracle-bytes", type=int, default=65_536)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    missing = [str(path) for path in (args.guard_log, args.oracle_json) if not path.is_file()]
    for optional in (args.client_json, args.traffic_json):
        if optional is not None and not optional.is_file():
            missing.append(str(optional))
    if missing:
        result = {
            "schema": "openmitrastar.w2-reclaim-poll-verification/v1",
            "status": "INCOMPLETE",
            "pass": False,
            "failures": ["missing_input"],
            "missing": missing,
            "mutations": False,
            "hardware_accessed": False,
            "flash": False,
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    guard_raw = args.guard_log.read_text(encoding="utf-8", errors="replace")
    oracle = load_json(args.oracle_json)
    client = load_json(args.client_json) if args.client_json else None
    traffic = load_json(args.traffic_json) if args.traffic_json else None
    events = parse_guard_events(guard_raw)
    cycles = build_cycles(events)
    candidate = audit_candidate(args.candidate_dir)
    oracle_result = oracle_state(oracle, args.min_oracle_bytes)
    client_result = client_state(client, traffic)

    failures: list[str] = []
    incomplete: list[str] = []
    if not candidate["pass"]:
        failures.extend(f"candidate.{item}" for item in candidate["failures"])
    if "OMRTLTXBD stage=final-readback-active target=hgw500 q=1" not in guard_raw:
        incomplete.append("final_readback_active_missing")
    if "OMRTLTXBD stage=final-readback-invalid" in guard_raw:
        failures.append("final_readback_invalid")
    if not cycles:
        incomplete.append("guard_stop_missing")
    for cycle in cycles:
        if not cycle["arms"]:
            incomplete.append(f"cycle_{cycle['number']}.arm_missing")
        if not cycle["polls"]:
            incomplete.append(f"cycle_{cycle['number']}.poll_missing")
        if not cycle["wakes"]:
            incomplete.append(f"cycle_{cycle['number']}.wake_missing")
        if cycle["polls"] and not cycle["rp_progress"]:
            failures.append(f"cycle_{cycle['number']}.rp_no_progress")
        if cycle["polls"] and not cycle["queue_decreased_in_poll"]:
            failures.append(f"cycle_{cycle['number']}.queue_not_decreased")
        if cycle["wakes"] and not cycle["wake_at_or_below_low"]:
            failures.append(f"cycle_{cycle['number']}.wake_above_low")
        if cycle["wakes"] and not cycle["final_poll_unstopped"]:
            failures.append(f"cycle_{cycle['number']}.poll_still_stopped")
    if not client_result["associated"]:
        incomplete.append("association_missing")
    if not client_result["authorized"]:
        incomplete.append("authorization_missing")
    if not client_result["monitor_traffic_pass"]:
        failures.append("traffic_monitor_failed")
    if not oracle_result["traffic_pass"]:
        failures.append("laptop_oracle_traffic_failed")

    status = "PASS" if not failures and not incomplete else "FAIL" if failures else "INCOMPLETE"
    inputs = {}
    for name, path in (
        ("guard_log", args.guard_log),
        ("oracle_json", args.oracle_json),
        ("client_json", args.client_json),
        ("traffic_json", args.traffic_json),
    ):
        if path is not None:
            inputs[name] = {"path": str(path), "sha256": sha256(path), "bytes": path.stat().st_size}
    result = {
        "schema": "openmitrastar.w2-reclaim-poll-verification/v1",
        "classification": "READONLY-OFFLINE-EVIDENCE-CORRELATION-NO-HARDWARE",
        "status": status,
        "pass": status == "PASS",
        "failures": sorted(set(failures)),
        "incomplete": sorted(set(incomplete)),
        "candidate": candidate,
        "guard": {
            "event_count": len(events),
            "cycle_count": len(cycles),
            "cycles": cycles,
            "final_readback_active": "OMRTLTXBD stage=final-readback-active target=hgw500 q=1" in guard_raw,
            "final_readback_invalid": "OMRTLTXBD stage=final-readback-invalid" in guard_raw,
        },
        "client": client_result,
        "laptop_oracle": oracle_result,
        "inputs": inputs,
        "correlation": "same-run artifact window plus guard-log line order",
        "thresholds": {"minimum_oracle_bytes": args.min_oracle_bytes, "ring_size": 512},
        "mutations": False,
        "hardware_accessed": False,
        "network_used": False,
        "uart_used": False,
        "flash": False,
    }
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if status == "PASS" else 1 if status == "FAIL" else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
