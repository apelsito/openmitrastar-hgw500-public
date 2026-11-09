#!/usr/bin/env python3
"""Collect read-only TX12 RTL8192EE management-frame trace evidence.

This tool only reads the RAM-booted router through SSH. It does not restart
hostapd, reload modules, touch bootenv, write MTD, or flash.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import paramiko  # noqa: E402
from ramssh_exec import load_private_key  # noqa: E402


CTRL = "/run/openmitrastar/radio2g/ctrl"
IMAGE_PATH = "work/tftp/omvl/linux510-w2-2g-parity-tx12-mgmt-trace-v1-RAM-TEST-NO-FLASH.bin"
IMAGE_SHA256 = "5feef36a0aa7c17384a0f1fec05a1940399fb3100978b9faaa526cb46fcb02c9"
IMAGE_BYTES = 4_333_757
IMAGE_VARIANT = "TX12_MGMT_TRACE"
MGMT_RE = re.compile(r"OMRTLMGMT stage=(?P<stage>rx|tx) type=(?P<type>[a-z_]+)\b(?P<rest>.*)")
FIELD_RE = re.compile(r"(?P<key>[a-zA-Z0-9_]+)=(?P<value>\S+)")


def remote_command(seconds: int) -> str:
    return f"""set +e
echo OM_UNAME_BEGIN
uname -a
echo OM_UNAME_END
echo OM_BOOT_STATE_BEGIN
cat /run/openmitrastar/boot-state 2>/dev/null
echo OM_BOOT_STATE_END
echo OM_RADIO_STATE_BEGIN
cat /run/openmitrastar/radio2g/state 2>/dev/null
echo OM_RADIO_STATE_END
echo OM_HOSTAPD_STATUS_BEGIN
/usr/sbin/hostapd_cli -p {CTRL} -i wlan0 status 2>/dev/null
echo OM_HOSTAPD_STATUS_END
echo OM_HOSTAPD_ALL_STA_BEGIN
/usr/sbin/hostapd_cli -p {CTRL} -i wlan0 all_sta 2>/dev/null
echo OM_HOSTAPD_ALL_STA_END
echo OM_IW_INFO_BEGIN
iw dev wlan0 info 2>/dev/null
echo OM_IW_INFO_END
echo OM_IW_STATION_BEGIN
iw dev wlan0 station dump 2>/dev/null
echo OM_IW_STATION_END
echo OM_TRACE_BEFORE_BEGIN
dmesg | grep 'OMRTLMGMT' 2>/dev/null
echo OM_TRACE_BEFORE_END
sleep {seconds}
echo OM_TRACE_AFTER_BEGIN
dmesg | grep 'OMRTLMGMT' 2>/dev/null
echo OM_TRACE_AFTER_END
echo OM_HOSTAPD_STATUS_AFTER_BEGIN
/usr/sbin/hostapd_cli -p {CTRL} -i wlan0 status 2>/dev/null
echo OM_HOSTAPD_STATUS_AFTER_END
echo OM_HOSTAPD_ALL_STA_AFTER_BEGIN
/usr/sbin/hostapd_cli -p {CTRL} -i wlan0 all_sta 2>/dev/null
echo OM_HOSTAPD_ALL_STA_AFTER_END
echo OM_IW_STATION_AFTER_BEGIN
iw dev wlan0 station dump 2>/dev/null
echo OM_IW_STATION_AFTER_END
echo OM_DMESG_SAFETY_BEGIN
dmesg | grep -i oops 2>/dev/null
dmesg | grep -i 'kernel panic' 2>/dev/null
dmesg | grep -i 'kernel bug' 2>/dev/null
echo OM_DMESG_SAFETY_END
"""


def run_remote(host: str, timeout: int, seconds: int) -> str:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            host,
            username="root",
            pkey=load_private_key(),
            look_for_keys=False,
            allow_agent=False,
            timeout=5,
            banner_timeout=8,
            auth_timeout=8,
        )
        _, stdout, stderr = client.exec_command(remote_command(seconds), timeout=timeout)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace").strip()
        if err:
            out += f"\nOM_REMOTE_STDERR_BEGIN\n{err}\nOM_REMOTE_STDERR_END\n"
        return out
    finally:
        client.close()


def section(raw: str, name: str) -> str:
    match = re.search(
        rf"^OM_{re.escape(name)}_BEGIN\n(?P<body>.*?)^OM_{re.escape(name)}_END$",
        raw,
        flags=re.MULTILINE | re.DOTALL,
    )
    return match.group("body").strip("\n") if match else ""


def parse_kv(text: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            out[key.strip()] = value.strip()
    return out


def parse_trace(text: str) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    for line in text.splitlines():
        match = MGMT_RE.search(line)
        if not match:
            continue
        event = match.groupdict()
        event["fields"] = {
            field.group("key"): field.group("value")
            for field in FIELD_RE.finditer(event["rest"])
        }
        event["line"] = line.strip()
        events.append(event)
    return events


def rx_frame_valid(event: dict[str, object]) -> bool:
    if event.get("stage") != "rx":
        return True
    fields = event.get("fields")
    if not isinstance(fields, dict):
        return True
    if fields.get("crc", "0") != "0" or fields.get("icv", "0") != "0":
        return False
    try:
        frame_control = int(str(fields.get("fc", "0")), 16)
    except ValueError:
        return False
    # IEEE 802.11 protocol version must be zero. rtlwifi subtype helpers mask
    # these bits, so corrupted headers can otherwise look like valid AUTH or
    # ASSOC frames even when the addresses are clearly random.
    return (frame_control & 0x0003) == 0


def summarize(events: list[dict[str, object]], rejected_rx_errors: int = 0) -> dict[str, object]:
    counts = Counter(f"{event['stage']}:{event['type']}" for event in events)
    rx_types = {event["type"] for event in events if event["stage"] == "rx"}
    tx_types = {event["type"] for event in events if event["stage"] == "tx"}
    if "assoc_req" in rx_types and "assoc_resp" in tx_types:
        decision = "ASSOC_REQ_AND_RESP_OBSERVED"
    elif "assoc_req" in rx_types:
        decision = "ASSOC_REQ_RX_NO_ASSOC_RESP_TX"
    elif "auth" in rx_types and "auth" in tx_types:
        decision = "AUTH_RX_AND_TX_NO_ASSOC_REQ"
    elif "auth" in rx_types:
        decision = "AUTH_RX_NO_AUTH_TX"
    elif "auth" in tx_types:
        decision = "AUTH_TX_WITHOUT_RX_OBSERVED"
    elif "probe_req" in rx_types and "probe_resp" in tx_types:
        decision = "PROBE_EXCHANGE_NO_AUTH"
    elif "probe_req" in rx_types:
        decision = "PROBE_RX_NO_PROBE_RESPONSE"
    elif events:
        decision = "MGMT_OTHER_ONLY"
    elif rejected_rx_errors:
        decision = "RX_ERROR_ONLY"
    else:
        decision = "NO_OMRTLMGMT_EVENTS"
    return {
        "counts": dict(sorted(counts.items())),
        "rx_types": sorted(rx_types),
        "tx_types": sorted(tx_types),
        "decision": decision,
    }


def appended_trace_events(
    before: list[dict[str, str]], after: list[dict[str, str]]
) -> tuple[list[dict[str, str]], str]:
    """Return events appended during the capture window, preserving duplicates.

    dmesg output is normally append-only. If the ring wrapped, align the longest
    suffix of the first snapshot with the prefix of the second snapshot. A set
    difference is deliberately avoided because repeated management frames often
    have byte-identical trace lines.
    """
    before_lines = [event["line"] for event in before]
    after_lines = [event["line"] for event in after]
    if after_lines[: len(before_lines)] == before_lines:
        return after[len(before_lines) :], "FULL_PREFIX"

    for overlap in range(min(len(before_lines), len(after_lines)), 0, -1):
        if before_lines[-overlap:] == after_lines[:overlap]:
            return after[overlap:], "RING_SUFFIX_PREFIX"

    return after, "NO_OVERLAP_FULL_AFTER"


def build_report(
    raw: str,
    seconds: int,
    *,
    image_path: str = IMAGE_PATH,
    image_sha256: str = IMAGE_SHA256,
    image_bytes: int = IMAGE_BYTES,
    image_variant: str = IMAGE_VARIANT,
    report_schema: str = "openmitrastar.w2-tx12-mgmt-trace/v1",
) -> dict[str, object]:
    status_before = parse_kv(section(raw, "HOSTAPD_STATUS"))
    status_after = parse_kv(section(raw, "HOSTAPD_STATUS_AFTER")) or status_before
    hostapd_sta_before = section(raw, "HOSTAPD_ALL_STA")
    hostapd_sta_after = section(raw, "HOSTAPD_ALL_STA_AFTER") or hostapd_sta_before
    iw_station_before = section(raw, "IW_STATION")
    iw_station_after = section(raw, "IW_STATION_AFTER") or iw_station_before
    before = parse_trace(section(raw, "TRACE_BEFORE"))
    after = parse_trace(section(raw, "TRACE_AFTER"))
    window_events, delta_mode = appended_trace_events(before, after)
    events = [event for event in window_events if rx_frame_valid(event)]
    rejected_events = [event for event in window_events if not rx_frame_valid(event)]
    safety = [line.strip() for line in section(raw, "DMESG_SAFETY").splitlines() if line.strip()]
    summary = summarize(events, len(rejected_events))
    station_state = {
        "hostapd_auth": "[AUTH]" in hostapd_sta_after,
        "hostapd_assoc": "[ASSOC]" in hostapd_sta_after,
        "hostapd_authorized": "[AUTHORIZED]" in hostapd_sta_after,
        "kernel_authenticated": bool(re.search(r"(?m)^\s*authenticated:\s*yes\s*$", iw_station_after)),
        "kernel_associated": bool(re.search(r"(?m)^\s*associated:\s*yes\s*$", iw_station_after)),
        "kernel_authorized": bool(re.search(r"(?m)^\s*authorized:\s*yes\s*$", iw_station_after)),
    }
    return {
        "schema": report_schema,
        "classification": "READONLY-TX12-MGMT-TRACE-NO-FLASH",
        "image": {
            "path": image_path,
            "sha256": image_sha256,
            "bytes": image_bytes,
            "variant": image_variant,
        },
        "window_seconds": seconds,
        "hostapd": {
            "state": status_after.get("state"),
            "ssid": status_after.get("ssid[0]"),
            "num_sta": int(status_after.get("num_sta[0]", "0") or "0"),
            "freq": status_after.get("freq"),
            "channel": status_after.get("channel"),
            "before": status_before,
            "after": status_after,
        },
        "station_state_after": station_state,
        "hostapd_all_sta_before_raw": hostapd_sta_before,
        "hostapd_all_sta_after_raw": hostapd_sta_after,
        "iw_station_before_raw": iw_station_before,
        "iw_station_after_raw": iw_station_after,
        "events_considered": events,
        "events_rejected_rx_error": rejected_events,
        "trace_window": {
            "before_events": len(before),
            "after_events": len(after),
            "new_events": len(window_events),
            "valid_events": len(events),
            "rejected_rx_error_events": len(rejected_events),
            "delta_mode": delta_mode,
        },
        "summary": summary,
        "no_kernel_oops": not safety,
        "safety_findings": safety,
        "mutations": False,
        "flash": False,
        "next_gate": {
            "AUTH_RX_AND_TX_NO_ASSOC_REQ": "inspect over-air AUTH response acceptance, TX rate, and descriptor contents",
            "AUTH_RX_NO_AUTH_TX": "inspect hostapd/mac80211 authentication response path",
            "AUTH_TX_WITHOUT_RX_OBSERVED": "preserve raw trace and verify capture-window alignment",
            "PROBE_EXCHANGE_NO_AUTH": "repeat while the client explicitly joins; probe request and response already work",
            "PROBE_RX_NO_PROBE_RESPONSE": "inspect management TX before authentication",
            "RX_ERROR_ONLY": "repeat the join attempt; only CRC/ICV-failed RX candidates were observed",
            "ASSOC_REQ_RX_NO_ASSOC_RESP_TX": "instrument hostapd/mac80211 AP association response path",
            "ASSOC_REQ_AND_RESP_OBSERVED": "inspect over-air response acceptance, TX rate, and descriptor contents",
            "NO_OMRTLMGMT_EVENTS": "repeat while client actively attempts to join the TX12 SSID",
            "MGMT_OTHER_ONLY": "repeat with a fresh client join attempt and preserve raw dmesg",
        }[str(summary["decision"])],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input-raw", type=Path)
    source.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--seconds", type=int, default=45)
    parser.add_argument("--timeout", type=int, default=75)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path)
    parser.add_argument("--image-path", default=IMAGE_PATH)
    parser.add_argument("--image-sha256", default=IMAGE_SHA256)
    parser.add_argument("--image-bytes", type=int, default=IMAGE_BYTES)
    parser.add_argument("--image-variant", default=IMAGE_VARIANT)
    parser.add_argument("--report-schema", default="openmitrastar.w2-tx12-mgmt-trace/v1")
    args = parser.parse_args()
    if not 0 <= args.seconds <= 600:
        raise SystemExit("--seconds must be 0..600")
    if args.timeout < args.seconds + 10:
        raise SystemExit("--timeout must be at least --seconds + 10")

    raw = args.input_raw.read_text(encoding="utf-8", errors="replace") if args.input_raw else run_remote(args.host, args.timeout, args.seconds)
    if args.raw_output:
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        args.raw_output.write_text(raw, encoding="utf-8", newline="\n")
    report = build_report(
        raw,
        args.seconds,
        image_path=args.image_path,
        image_sha256=args.image_sha256,
        image_bytes=args.image_bytes,
        image_variant=args.image_variant,
        report_schema=args.report_schema,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")
    return 0 if report["hostapd"]["state"] == "ENABLED" and report["no_kernel_oops"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
