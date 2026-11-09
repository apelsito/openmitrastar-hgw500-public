#!/usr/bin/env python3
"""Observe the Q3 5 GHz client gate without changing radio or network state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
MAC_RE = re.compile(r"(?im)^(?:[0-9a-f]{2}:){5}[0-9a-f]{2}$")


def ssh(host: str, command: str, timeout: int = 20) -> str:
    result = subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", command, "--host", host,
         "--timeout", str(timeout)],
        cwd=ROOT, text=True, capture_output=True, timeout=timeout + 15,
    )
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


def section(text: str, name: str) -> str:
    start = f"__{name}_BEGIN__\n"
    end = f"__{name}_END__\n"
    if start not in text or end not in text:
        return ""
    return text.split(start, 1)[1].split(end, 1)[0]


def number(text: str, key: str) -> int:
    match = re.search(rf"(?m)^{re.escape(key)}=(\d+)$", text)
    return int(match.group(1)) if match else 0


def sample(host: str, timeout: int = 20) -> dict[str, object]:
    command = r'''set +e
echo __PING_BEGIN__
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping 2>&1
echo __PING_END__
echo __MIB_BEGIN__
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 mib 2>&1 | grep -E '^(dot11RSNA4WayHandshakeFailures|dot11RSNAAuthenticationSuiteSelected|dot11RSNAPairwiseCipherSelected|hostapdWPAGroupState)='
echo __MIB_END__
echo __STA_BEGIN__
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 all_sta 2>&1
echo __STA_END__
echo __HISTORY_BEGIN__
/usr/sbin/iwpriv-qtn wifi0 assoc_history 2>&1
/usr/sbin/iwpriv-qtn wifi0 disassoc_reason 2>&1
echo __HISTORY_END__
echo __EVENTS_BEGIN__
grep -a -E 'AP-STA|IEEE 802.11: (authentication|association)|authentication failed|association rejected|WPA:.*(fail|timeout)|EAPOL.*(fail|timeout)|4-Way Handshake|MIC failure' /run/openmitrastar/radio5g/hostapd.log 2>/dev/null | tail -n 80
echo __EVENTS_END__
echo __FATAL_BEGIN__
dmesg | grep -E 'No DDR heap memory for beacon buffer|MuC exception|forcing reboot|EV_TLB|OMQDRVBC stage=quarantined|OMQDRVHLINK stage=quarantine' | tail -n 80
echo __FATAL_END__
echo RX=$(cat /sys/class/net/wifi0/statistics/rx_packets 2>/dev/null)
echo TX=$(cat /sys/class/net/wifi0/statistics/tx_packets 2>/dev/null)
echo RXB=$(cat /sys/class/net/wifi0/statistics/rx_bytes 2>/dev/null)
echo TXB=$(cat /sys/class/net/wifi0/statistics/tx_bytes 2>/dev/null)
echo IRQ8=$(awk '$1 == "8:" { print $2 }' /proc/interrupts)
echo IRQ10=$(awk '$1 == "10:" { print $2 }' /proc/interrupts)
echo RF=$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable 2>/dev/null)
echo CARRIER=$(cat /sys/class/net/wifi0/carrier 2>/dev/null)
'''
    raw = ssh(host, command, timeout=timeout)
    stations = section(raw, "STA")
    return {
        "raw": raw,
        "control": "PONG" in section(raw, "PING"),
        "mib": section(raw, "MIB"),
        "stations": stations,
        "station_macs": MAC_RE.findall(stations),
        "history": section(raw, "HISTORY"),
        "events": section(raw, "EVENTS"),
        "fatal": section(raw, "FATAL"),
        "handshake_failures": number(raw, "dot11RSNA4WayHandshakeFailures"),
        "rx_packets": number(raw, "RX"),
        "tx_packets": number(raw, "TX"),
        "rx_bytes": number(raw, "RXB"),
        "tx_bytes": number(raw, "TXB"),
        "irq8": number(raw, "IRQ8"),
        "irq10": number(raw, "IRQ10"),
        "rf": number(raw, "RF"),
        "carrier": number(raw, "CARRIER"),
    }


def classify(before: dict[str, object], after: dict[str, object]) -> str:
    fatal = str(after["fatal"])
    if re.search(r"MuC exception|forcing reboot|EV_TLB|stage=quarantined|stage=quarantine", fatal) or int(after["irq10"]) > 0:
        return "RADIO_MUC_FATAL_COLD_RESTART_REQUIRED"
    if "No DDR heap memory for beacon buffer" in fatal and (
        int(after["irq8"]) == int(before["irq8"])
        and int(after["tx_packets"]) == int(before["tx_packets"])
    ):
        return "BEACON_HEAP_EXHAUSTED_RADIO_STALLED"
    stations = after["station_macs"]
    events = str(after["events"])
    if stations:
        authorized = "[AUTHORIZED]" in str(after["stations"])
        traffic = (
            int(after["rx_packets"]) > int(before["rx_packets"])
            and int(after["tx_packets"]) > int(before["tx_packets"])
        )
        if authorized and traffic:
            return "ASSOCIATED_AUTHORIZED_DATA_PROGRESS"
        if authorized:
            return "ASSOCIATED_AUTHORIZED_NO_DATA_PROGRESS"
        return "ASSOCIATED_NOT_AUTHORIZED"
    if int(after["handshake_failures"]) > int(before["handshake_failures"]):
        return "WPA_4WAY_HANDSHAKE_FAILURE"
    if re.search(r"(?i)authentication failed|association rejected|WPA:.*(?:fail|timeout)|EAPOL.*(?:fail|timeout)|MIC failure", events):
        return "AUTH_OR_PSK_REJECT_OBSERVED"
    if re.search(r"(?i)authentication|association|AP-STA", events):
        return "CLIENT_ATTEMPT_OBSERVED_BEFORE_AUTHORIZATION"
    if int(after["rx_packets"]) > int(before["rx_packets"]):
        return "RX_PROGRESS_WITHOUT_HOSTAPD_ASSOCIATION"
    return "NO_CLIENT_ATTEMPT_OBSERVED_BY_AP"


def history_summary(text: str) -> tuple[bool, int]:
    assoc = re.search(r"assoc_history:(.*)", text)
    assoc_nonzero = bool(
        assoc and any(int(value) for value in re.findall(r"\d+", assoc.group(1)))
    )
    reason = re.search(r"disassoc_reason:(\d+)", text)
    return assoc_nonzero, int(reason.group(1)) if reason else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--seconds", type=int, default=60)
    parser.add_argument("--interval-seconds", type=float, default=1.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 0 <= args.seconds <= 300:
        raise SystemExit("--seconds must be 0..300")
    if not 0.2 <= args.interval_seconds <= 30:
        raise SystemExit("--interval-seconds must be 0.2..30")

    def compact(value: dict[str, object], elapsed: float) -> dict[str, object]:
        return {
            "elapsed_seconds": round(elapsed, 3),
            "control_alive": value["control"],
            "station_count": len(value["station_macs"]),
            "rx_packets": value["rx_packets"],
            "tx_packets": value["tx_packets"],
            "rx_bytes": value["rx_bytes"],
            "tx_bytes": value["tx_bytes"],
            "irq8": value["irq8"],
            "irq10": value["irq10"],
            "rf": value["rf"],
            "carrier": value["carrier"],
        }

    started = time.monotonic()
    before = sample(args.host, timeout=8)
    after = before
    snapshots = [compact(before, 0.0)]
    connection_error = ""
    deadline = started + args.seconds
    while time.monotonic() < deadline:
        time.sleep(min(args.interval_seconds, max(0.0, deadline - time.monotonic())))
        try:
            after = sample(args.host, timeout=8)
        except Exception as exc:  # Preserve the last successful sample on loss.
            connection_error = f"{type(exc).__name__}: {exc}"[:512]
            break
        snapshots.append(compact(after, time.monotonic() - started))
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps({
                    "schema": "openmitrastar.q3-client-gate-checkpoint/v1",
                    "host": args.host,
                    "state": "running",
                    "snapshots": snapshots,
                    "flash": False,
                    "mutations": False,
                }, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
    assoc_history_nonzero, disassoc_reason = history_summary(str(after["history"]))
    result = {
        "schema": "openmitrastar.q3-client-gate-readonly/v1",
        "host": args.host,
        "seconds": args.seconds,
        "classification": (
            "MANAGEMENT_LOST_DURING_CLIENT_TEST"
            if connection_error else classify(before, after)
        ),
        "control_socket": "/var/run/hostapd/wifi0",
        "control_alive": after["control"],
        "station_count": len(after["station_macs"]),
        "handshake_failures_before": before["handshake_failures"],
        "handshake_failures_after": after["handshake_failures"],
        "rx_packets_delta": int(after["rx_packets"]) - int(before["rx_packets"]),
        "tx_packets_delta": int(after["tx_packets"]) - int(before["tx_packets"]),
        "irq8_delta": int(after["irq8"]) - int(before["irq8"]),
        "irq10": after["irq10"],
        "rf": after["rf"],
        "carrier": after["carrier"],
        "events": str(after["events"]).splitlines(),
        "fatal_markers": str(after["fatal"]).splitlines(),
        "assoc_history_nonzero": assoc_history_nonzero,
        "disassoc_reason": disassoc_reason,
        "connection_error": connection_error or None,
        "snapshots": snapshots,
        "flash": False,
        "mutations": False,
    }
    encoded = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded, encoding="utf-8")
    print(encoded, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
