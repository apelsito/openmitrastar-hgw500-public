#!/usr/bin/env python3
"""Passive single-SSH telemetry for the live OpenMitraStar 2.4 GHz AP.

The monitor deliberately performs no radio, module, boot or flash mutations.  A
single SSH command records a short pre-test baseline, the traffic window and a
post-test tail so a physical client test can be correlated with hostapd,
station, netdev, IRQ and bounded Realtek TX-completion telemetry.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import shlex
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import paramiko  # noqa: E402
from ramssh_exec import load_private_key  # noqa: E402


LINE_RE = re.compile(
    r"^OM2G seq=(?P<seq>\d+) phase=(?P<phase>before|during|after) "
    r"uptime=(?P<uptime>\d+) state=(?P<state>\w+) "
    r"assoc=(?P<assoc>\d+) authorized=(?P<authorized>\d+) "
    r"sta_tx_retries=(?P<sta_tx_retries>\d+) sta_tx_failed=(?P<sta_tx_failed>\d+) "
    r"wifi_rx=(?P<wifi_rx>\d+) wifi_tx=(?P<wifi_tx>\d+) "
    r"wifi_rx_bytes=(?P<wifi_rx_bytes>\d+) wifi_tx_bytes=(?P<wifi_tx_bytes>\d+) "
    r"wifi_rxerr=(?P<wifi_rxerr>\d+) wifi_txerr=(?P<wifi_txerr>\d+) "
    r"br_rx=(?P<br_rx>\d+) br_tx=(?P<br_tx>\d+) "
    r"br_rx_bytes=(?P<br_rx_bytes>\d+) br_tx_bytes=(?P<br_tx_bytes>\d+) "
    r"eth_rx=(?P<eth_rx>\d+) eth_tx=(?P<eth_tx>\d+) "
    r"eth_rx_bytes=(?P<eth_rx_bytes>\d+) eth_tx_bytes=(?P<eth_tx_bytes>\d+) "
    r"irq28=(?P<irq28>\d+) irq20=(?P<irq20>\d+) "
    r"be_boot_max=(?P<be_boot_max>\d+) be_run_max=(?P<be_run_max>\d+) "
    r"be_events=(?P<be_events>\d+) be_close_events=(?P<be_close_events>\d+) "
    r"be_doorbell_events=(?P<be_doorbell_events>\d+) "
    r"be_sw_rp=(?P<be_sw_rp>-?\d+) be_sw_wp=(?P<be_sw_wp>-?\d+) "
    r"be_hw_rp=(?P<be_hw_rp>-?\d+) be_hw_wp=(?P<be_hw_wp>-?\d+) "
    r"fatal_run=(?P<fatal_run>\d+) "
    r"carrier=(?P<carrier>[01]) ssh_alive=(?P<ssh_alive>[01])$"
)


def remote_command(
    seconds: int,
    interval: int,
    ctrl: str,
    pre_seconds: int,
    post_seconds: int,
) -> str:
    ctrl_candidates = [ctrl] if ctrl != "auto" else [
        "/run/openmitrastar/radio2g/ctrl-open",
        "/run/openmitrastar/radio2g/ctrl",
    ]
    candidate_words = " ".join(shlex.quote(path) for path in ctrl_candidates)
    return rf'''set +e
i=0
start=$(cut -d. -f1 /proc/uptime 2>/dev/null); [ -n "$start" ] || start=0
deadline=$((start + {seconds}))
dmesg_base=$(dmesg 2>/dev/null)
be_base=$(printf '%s\n' "$dmesg_base" | grep -E 'OMRTL stage=(tx-complete|pci-tx-queued)' | grep -E 'queue=1|q=1')
be_base_count=$(printf '%s\n' "$be_base" | awk 'NF {{ n++ }} END {{ print n + 0 }}')
be_boot_max=$(printf '%s\n' "$be_base" | sed -n -e 's/.*queue=1 queued=\([0-9][0-9]*\)->\([0-9][0-9]*\).*/\1 \2/p' -e 's/.*q=1 .*queue_len=\([0-9][0-9]*\).*/\1/p' | awk 'BEGIN {{ m=0 }} {{ if ($1>m) m=$1; if ($2>m) m=$2 }} END {{ print m+0 }}')
be_close_base=$(printf '%s\n' "$dmesg_base" | grep 'OMRTLTXCLOSE' | grep ' q=1 ')
be_close_base_count=$(printf '%s\n' "$be_close_base" | awk 'NF {{ n++ }} END {{ print n + 0 }}')
be_doorbell_base=$(printf '%s\n' "$dmesg_base" | grep 'OMRTL92 stage=tx-doorbell-post' | grep ' q=1 ')
be_doorbell_base_count=$(printf '%s\n' "$be_doorbell_base" | awk 'NF {{ n++ }} END {{ print n + 0 }}')
fatal_base_count=$(printf '%s\n' "$dmesg_base" | grep -Eic 'Kernel panic|Oops|BUG:|Unable to handle kernel|hard LOCKUP|soft lockup')
last_phase=
last_assoc=
last_authorized=
while :; do
  uptime=$(cut -d. -f1 /proc/uptime 2>/dev/null); [ -n "$uptime" ] || uptime=0
  elapsed=$((uptime - start))
  if [ "$elapsed" -lt {pre_seconds} ]; then
    phase=before
  elif [ "$elapsed" -ge $(({seconds} - {post_seconds})) ]; then
    phase=after
  else
    phase=during
  fi
  status=
  all_sta=
  ctrl_used=
  for ctrl_try in {candidate_words}; do
    status=$(/usr/sbin/hostapd_cli -p "$ctrl_try" -i wlan0 status 2>/dev/null)
    if printf '%s\n' "$status" | grep -q '^state='; then
      ctrl_used=$ctrl_try
      all_sta=$(/usr/sbin/hostapd_cli -p "$ctrl_try" -i wlan0 all_sta 2>/dev/null)
      break
    fi
  done
  state=$(printf '%s\n' "$status" | sed -n 's/^state=//p'); [ -n "$state" ] || state=DOWN
  assoc=$(printf '%s\n' "$status" | sed -n 's/^num_sta\[0\]=//p'); [ -n "$assoc" ] || assoc=0
  authorized=$(printf '%s\n' "$all_sta" | grep -c 'AUTHORIZED'); [ -n "$authorized" ] || authorized=0
  iwbin=/tmp/openmitrastar-ap/bundle/bin/iw
  [ -x "$iwbin" ] || iwbin=/usr/sbin/iw
  station=$($iwbin dev wlan0 station dump 2>/dev/null)
  sta_tx_retries=$(printf '%s\n' "$station" | awk '/^[ \t]*tx retries:/ {{ n += $3 }} END {{ print n + 0 }}')
  sta_tx_failed=$(printf '%s\n' "$station" | awk '/^[ \t]*tx failed:/ {{ n += $3 }} END {{ print n + 0 }}')
  wifi_rx=$(cat /sys/class/net/wlan0/statistics/rx_packets 2>/dev/null); [ -n "$wifi_rx" ] || wifi_rx=0
  wifi_tx=$(cat /sys/class/net/wlan0/statistics/tx_packets 2>/dev/null); [ -n "$wifi_tx" ] || wifi_tx=0
  wifi_rx_bytes=$(cat /sys/class/net/wlan0/statistics/rx_bytes 2>/dev/null); [ -n "$wifi_rx_bytes" ] || wifi_rx_bytes=0
  wifi_tx_bytes=$(cat /sys/class/net/wlan0/statistics/tx_bytes 2>/dev/null); [ -n "$wifi_tx_bytes" ] || wifi_tx_bytes=0
  wifi_rxerr=$(cat /sys/class/net/wlan0/statistics/rx_errors 2>/dev/null); [ -n "$wifi_rxerr" ] || wifi_rxerr=0
  wifi_txerr=$(cat /sys/class/net/wlan0/statistics/tx_errors 2>/dev/null); [ -n "$wifi_txerr" ] || wifi_txerr=0
  br_rx=$(cat /sys/class/net/br0/statistics/rx_packets 2>/dev/null); [ -n "$br_rx" ] || br_rx=0
  br_tx=$(cat /sys/class/net/br0/statistics/tx_packets 2>/dev/null); [ -n "$br_tx" ] || br_tx=0
  br_rx_bytes=$(cat /sys/class/net/br0/statistics/rx_bytes 2>/dev/null); [ -n "$br_rx_bytes" ] || br_rx_bytes=0
  br_tx_bytes=$(cat /sys/class/net/br0/statistics/tx_bytes 2>/dev/null); [ -n "$br_tx_bytes" ] || br_tx_bytes=0
  eth_rx=$(cat /sys/class/net/eth0/statistics/rx_packets 2>/dev/null); [ -n "$eth_rx" ] || eth_rx=0
  eth_tx=$(cat /sys/class/net/eth0/statistics/tx_packets 2>/dev/null); [ -n "$eth_tx" ] || eth_tx=0
  eth_rx_bytes=$(cat /sys/class/net/eth0/statistics/rx_bytes 2>/dev/null); [ -n "$eth_rx_bytes" ] || eth_rx_bytes=0
  eth_tx_bytes=$(cat /sys/class/net/eth0/statistics/tx_bytes 2>/dev/null); [ -n "$eth_tx_bytes" ] || eth_tx_bytes=0
  irq28=$(awk '$1 == "28:" {{ print $2 }}' /proc/interrupts); [ -n "$irq28" ] || irq28=0
  irq20=$(awk '$1 == "20:" {{ print $2 }}' /proc/interrupts); [ -n "$irq20" ] || irq20=0
  carrier=$(cat /sys/class/net/wlan0/carrier 2>/dev/null); [ "$carrier" = 1 ] || carrier=0
  dmesg_now=$(dmesg 2>/dev/null)
  be_now=$(printf '%s\n' "$dmesg_now" | grep -E 'OMRTL stage=(tx-complete|pci-tx-queued)' | grep -E 'queue=1|q=1')
  be_count=$(printf '%s\n' "$be_now" | awk 'NF {{ n++ }} END {{ print n + 0 }}')
  be_events=$((be_count - be_base_count)); [ "$be_events" -ge 0 ] || be_events=0
  be_first=$((be_base_count + 1))
  be_run_max=$(printf '%s\n' "$be_now" | sed -n "${{be_first}},\$p" | sed -n -e 's/.*queue=1 queued=\([0-9][0-9]*\)->\([0-9][0-9]*\).*/\1 \2/p' -e 's/.*q=1 .*queue_len=\([0-9][0-9]*\).*/\1/p' | awk 'BEGIN {{ m=0 }} {{ if ($1>m) m=$1; if ($2>m) m=$2 }} END {{ print m+0 }}')
  be_close_now=$(printf '%s\n' "$dmesg_now" | grep 'OMRTLTXCLOSE' | grep ' q=1 ')
  be_close_count=$(printf '%s\n' "$be_close_now" | awk 'NF {{ n++ }} END {{ print n + 0 }}')
  be_close_events=$((be_close_count - be_close_base_count)); [ "$be_close_events" -ge 0 ] || be_close_events=0
  be_close_last=$(printf '%s\n' "$be_close_now" | tail -n 1)
  be_doorbell_now=$(printf '%s\n' "$dmesg_now" | grep 'OMRTL92 stage=tx-doorbell-post' | grep ' q=1 ')
  be_doorbell_count=$(printf '%s\n' "$be_doorbell_now" | awk 'NF {{ n++ }} END {{ print n + 0 }}')
  be_doorbell_events=$((be_doorbell_count - be_doorbell_base_count)); [ "$be_doorbell_events" -ge 0 ] || be_doorbell_events=0
  be_doorbell_last=$(printf '%s\n' "$be_doorbell_now" | tail -n 1)
  be_sw_rp=$(printf '%s\n' "$be_close_last" | sed -n 's/.* sw_rp=\([0-9][0-9]*\).*/\1/p'); [ -n "$be_sw_rp" ] || be_sw_rp=-1
  be_sw_wp=$(printf '%s\n' "$be_close_last" | sed -n 's/.* sw_wp=\([0-9][0-9]*\).*/\1/p'); [ -n "$be_sw_wp" ] || be_sw_wp=-1
  be_hw_rp=$(printf '%s\n' "$be_close_last" | sed -n 's/.* hw_rp=\([0-9][0-9]*\).*/\1/p'); [ -n "$be_hw_rp" ] || be_hw_rp=-1
  be_hw_wp=$(printf '%s\n' "$be_close_last" | sed -n 's/.* hw_wp=\([0-9][0-9]*\).*/\1/p'); [ -n "$be_hw_wp" ] || be_hw_wp=-1
  if [ "$be_hw_rp" -lt 0 ] && [ -n "$be_doorbell_last" ]; then
    be_sw_rp=$(printf '%s\n' "$be_doorbell_last" | sed -n 's/.* rp=\([0-9][0-9]*\).*/\1/p'); [ -n "$be_sw_rp" ] || be_sw_rp=-1
    be_sw_wp=$(printf '%s\n' "$be_doorbell_last" | sed -n 's/.* new_wp=\([0-9][0-9]*\).*/\1/p'); [ -n "$be_sw_wp" ] || be_sw_wp=-1
    be_qidx_hex=$(printf '%s\n' "$be_doorbell_last" | sed -n 's/.* qidx=\([0-9a-fA-F][0-9a-fA-F]*\).*/\1/p')
    if [ -n "$be_qidx_hex" ]; then
      be_qidx_value=$((0x$be_qidx_hex))
      be_hw_rp=$(((be_qidx_value >> 16) & 4095))
      be_hw_wp=$((be_qidx_value & 4095))
    fi
  fi
  fatal_now=$(printf '%s\n' "$dmesg_now" | grep -Eic 'Kernel panic|Oops|BUG:|Unable to handle kernel|hard LOCKUP|soft lockup')
  fatal_run=$((fatal_now - fatal_base_count)); [ "$fatal_run" -ge 0 ] || fatal_run=0
  dump_snapshot=0
  [ "$i" -eq 0 ] && dump_snapshot=1
  [ "$phase" != "$last_phase" ] && dump_snapshot=1
  [ "$assoc" != "$last_assoc" ] && dump_snapshot=1
  [ "$authorized" != "$last_authorized" ] && dump_snapshot=1
  [ "$uptime" -ge "$deadline" ] && dump_snapshot=1
  if [ "$dump_snapshot" -eq 1 ]; then
    echo "OM2G_HOSTAPD_STATUS_BEGIN seq=$i phase=$phase ctrl=$ctrl_used"
    printf '%s\n' "$status"
    echo "OM2G_HOSTAPD_STATUS_END seq=$i phase=$phase"
    echo "OM2G_HOSTAPD_ALL_STA_BEGIN seq=$i phase=$phase"
    printf '%s\n' "$all_sta"
    echo "OM2G_HOSTAPD_ALL_STA_END seq=$i phase=$phase"
    echo "OM2G_IW_STATION_BEGIN seq=$i phase=$phase"
    printf '%s\n' "$station"
    echo "OM2G_IW_STATION_END seq=$i phase=$phase"
    echo "OM2G_BE_LOG_BEGIN seq=$i phase=$phase baseline=$be_base_count current=$be_count"
    printf '%s\n' "$be_now" | sed -n "${{be_first}},\$p"
    echo "OM2G_BE_LOG_END seq=$i phase=$phase"
    echo "OM2G_BE_CLOSE_BEGIN seq=$i phase=$phase baseline=$be_close_base_count current=$be_close_count"
    printf '%s\n' "$be_close_now" | sed -n "$((be_close_base_count + 1)),\$p"
    echo "OM2G_BE_CLOSE_END seq=$i phase=$phase"
    echo "OM2G_BE_DOORBELL_BEGIN seq=$i phase=$phase baseline=$be_doorbell_base_count current=$be_doorbell_count"
    printf '%s\n' "$be_doorbell_now" | sed -n "$((be_doorbell_base_count + 1)),\$p"
    echo "OM2G_BE_DOORBELL_END seq=$i phase=$phase"
  fi
  echo "OM2G seq=$i phase=$phase uptime=$uptime state=$state assoc=$assoc authorized=$authorized sta_tx_retries=$sta_tx_retries sta_tx_failed=$sta_tx_failed wifi_rx=$wifi_rx wifi_tx=$wifi_tx wifi_rx_bytes=$wifi_rx_bytes wifi_tx_bytes=$wifi_tx_bytes wifi_rxerr=$wifi_rxerr wifi_txerr=$wifi_txerr br_rx=$br_rx br_tx=$br_tx br_rx_bytes=$br_rx_bytes br_tx_bytes=$br_tx_bytes eth_rx=$eth_rx eth_tx=$eth_tx eth_rx_bytes=$eth_rx_bytes eth_tx_bytes=$eth_tx_bytes irq28=$irq28 irq20=$irq20 be_boot_max=$be_boot_max be_run_max=$be_run_max be_events=$be_events be_close_events=$be_close_events be_doorbell_events=$be_doorbell_events be_sw_rp=$be_sw_rp be_sw_wp=$be_sw_wp be_hw_rp=$be_hw_rp be_hw_wp=$be_hw_wp fatal_run=$fatal_run carrier=$carrier ssh_alive=1"
  [ "$uptime" -ge "$deadline" ] && break
  last_phase=$phase
  last_assoc=$assoc
  last_authorized=$authorized
  i=$((i + 1))
  sleep {interval}
done
'''


def counter_increase(samples: list[dict[str, int | str]], key: str) -> int:
    """Return positive progress while tolerating a counter reset/reassociation."""
    values = [int(row[key]) for row in samples if key in row]
    total = 0
    for previous, current in zip(values, values[1:]):
        total += current - previous if current >= previous else current
    return total


def peak_rate_mbps(
    samples: list[dict[str, int | str]], key: str, *, phase: str | None = None
) -> float:
    selected = [row for row in samples if phase is None or row.get("phase") == phase]
    peak = 0.0
    for previous, current in zip(selected, selected[1:]):
        elapsed = int(current["uptime"]) - int(previous["uptime"])
        if elapsed <= 0:
            continue
        before = int(previous[key])
        after = int(current[key])
        delta = after - before if after >= before else after
        peak = max(peak, delta * 8 / elapsed / 1_000_000)
    return round(peak, 3)


def observed_progress(samples: list[dict[str, int | str]], key: str) -> bool:
    values = {int(row[key]) for row in samples if int(row.get(key, -1)) >= 0}
    return len(values) > 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--interval", type=int, default=1)
    parser.add_argument("--pre-seconds", type=int, default=10)
    parser.add_argument("--post-seconds", type=int, default=10)
    parser.add_argument(
        "--ctrl",
        default="auto",
        help="hostapd ctrl directory or 'auto' for ctrl-open then ctrl",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-output-bytes", type=int, default=64 * 1024 * 1024)
    args = parser.parse_args()
    if not 10 <= args.seconds <= 1800:
        raise SystemExit("--seconds must be 10..1800")
    if not 1 <= args.interval <= 10:
        raise SystemExit("--interval must be 1..10")
    if args.pre_seconds < 1 or args.post_seconds < 1:
        raise SystemExit("--pre-seconds and --post-seconds must be positive")
    if args.pre_seconds + args.post_seconds >= args.seconds:
        raise SystemExit("pre + post must leave a non-empty traffic window")
    if args.ctrl != "auto" and not re.fullmatch(r"/[A-Za-z0-9_./-]+", args.ctrl):
        raise SystemExit("--ctrl must be 'auto' or an absolute safe path")
    if not 1_048_576 <= args.max_output_bytes <= 256 * 1024 * 1024:
        raise SystemExit("--max-output-bytes must be 1 MiB..256 MiB")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    samples: list[dict[str, int | str]] = []
    error = ""
    captured_bytes = 0
    started = time.monotonic()
    with args.output.open("w", encoding="utf-8", buffering=1) as stream:
        try:
            client.connect(
                args.host, username="root", pkey=load_private_key(),
                look_for_keys=False, allow_agent=False, timeout=5,
                banner_timeout=8, auth_timeout=8,
            )
            _, stdout, stderr = client.exec_command(
                remote_command(
                    args.seconds,
                    args.interval,
                    args.ctrl,
                    args.pre_seconds,
                    args.post_seconds,
                ),
                timeout=args.seconds + 30,
            )
            channel = stdout.channel
            channel.settimeout(1.0)
            pending = b""
            deadline = started + args.seconds + max(60, args.seconds // 5)
            last_sample_at = time.monotonic()
            while not channel.exit_status_ready() or channel.recv_ready():
                now = time.monotonic()
                if now >= deadline:
                    error = "local-deadline-exceeded"
                    break
                if now - last_sample_at > max(15, args.interval * 8):
                    error = "remote-sample-heartbeat-timeout"
                    break
                if channel.recv_ready():
                    chunk = channel.recv(8192)
                    captured_bytes += len(chunk)
                    if captured_bytes > args.max_output_bytes:
                        error = "remote-output-limit-exceeded"
                        channel.close()
                        break
                    pending += chunk
                    while b"\n" in pending:
                        raw, pending = pending.split(b"\n", 1)
                        line = raw.decode("utf-8", "replace")
                        stream.write(line + "\n")
                        match = LINE_RE.match(line.strip())
                        if match:
                            row: dict[str, int | str] = {
                                key: (value if key in {"state", "phase"} else int(value))
                                for key, value in match.groupdict().items()
                            }
                            samples.append(row)
                            last_sample_at = time.monotonic()
                            print(line, flush=True)
                else:
                    time.sleep(0.05)
            err = stderr.read(65_536).decode("utf-8", "replace").strip()
            if err:
                error = err[:512]
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:512]
        finally:
            client.close()

    first = samples[0] if samples else {}
    last = samples[-1] if samples else {}
    observed_span = (
        int(last.get("uptime", 0)) - int(first.get("uptime", 0))
        if samples else 0
    )
    duration_complete = observed_span >= max(0, args.seconds - args.interval)
    phases_observed = {str(row["phase"]) for row in samples}
    phase_capture_complete = {"before", "during", "after"}.issubset(phases_observed)
    counters = (
        "wifi_rx", "wifi_tx", "wifi_rx_bytes", "wifi_tx_bytes",
        "br_rx", "br_tx", "br_rx_bytes", "br_tx_bytes",
        "eth_rx", "eth_tx", "eth_rx_bytes", "eth_tx_bytes",
        "irq28", "irq20",
    )
    result = {
        "schema": "openmitrastar.2g-live-traffic/v1",
        "host": args.host,
        "duration_requested_seconds": args.seconds,
        "pre_seconds": args.pre_seconds,
        "traffic_window_seconds": args.seconds - args.pre_seconds - args.post_seconds,
        "post_seconds": args.post_seconds,
        "duration_observed_seconds": round(time.monotonic() - started, 3),
        "minimum_observed_span_seconds": max(0, args.seconds - args.interval),
        "samples_observed": len(samples),
        "observed_span_seconds": observed_span,
        "complete": duration_complete and phase_capture_complete and not error,
        "connection_error": error or None,
        "association_observed": any(int(row["assoc"]) > 0 for row in samples),
        "max_associations": max((int(row["assoc"]) for row in samples), default=0),
        "authorization_observed": any(int(row["authorized"]) > 0 for row in samples),
        "max_authorized": max((int(row["authorized"]) for row in samples), default=0),
        "ap_enabled_all_samples": bool(samples) and all(row["state"] == "ENABLED" for row in samples),
        "carrier_all_samples": bool(samples) and all(int(row["carrier"]) == 1 for row in samples),
        "ssh_alive_all_samples": bool(samples) and all(int(row["ssh_alive"]) == 1 for row in samples),
        "phases_observed": sorted(phases_observed),
        "phase_capture_complete": phase_capture_complete,
        "before_samples": sum(row["phase"] == "before" for row in samples),
        "during_samples": sum(row["phase"] == "during" for row in samples),
        "after_samples": sum(row["phase"] == "after" for row in samples),
        "rx_errors_delta": int(last.get("wifi_rxerr", 0)) - int(first.get("wifi_rxerr", 0)),
        "tx_errors_delta": int(last.get("wifi_txerr", 0)) - int(first.get("wifi_txerr", 0)),
        "station_tx_retries_delta": int(last.get("sta_tx_retries", 0)) - int(first.get("sta_tx_retries", 0)),
        "station_tx_failed_delta": int(last.get("sta_tx_failed", 0)) - int(first.get("sta_tx_failed", 0)),
        "station_tx_retries_increase": counter_increase(samples, "sta_tx_retries"),
        "station_tx_failed_increase": counter_increase(samples, "sta_tx_failed"),
        "station_tx_retries_max": max((int(row["sta_tx_retries"]) for row in samples), default=0),
        "station_tx_failed_max": max((int(row["sta_tx_failed"]) for row in samples), default=0),
        "be_queue_boot_max": max((int(row["be_boot_max"]) for row in samples), default=0),
        "be_queue_run_max": max((int(row["be_run_max"]) for row in samples), default=0),
        "be_queue_cumulative_max_by_phase": {
            phase: max(
                (int(row["be_run_max"]) for row in samples if row["phase"] == phase),
                default=0,
            )
            for phase in ("before", "during", "after")
        },
        "be_events_observed": max((int(row["be_events"]) for row in samples), default=0),
        "be_close_events_observed": max((int(row["be_close_events"]) for row in samples), default=0),
        "be_doorbell_events_observed": max((int(row["be_doorbell_events"]) for row in samples), default=0),
        "be_sw_rp_progress": observed_progress(samples, "be_sw_rp"),
        "be_sw_wp_progress": observed_progress(samples, "be_sw_wp"),
        "be_hw_rp_progress": observed_progress(samples, "be_hw_rp"),
        "be_hw_wp_progress": observed_progress(samples, "be_hw_wp"),
        "be_last_indices": {
            key: int(next((row[key] for row in reversed(samples) if int(row.get(key, -1)) >= 0), -1))
            for key in ("be_sw_rp", "be_sw_wp", "be_hw_rp", "be_hw_wp")
        },
        "fatal_markers_during_run": max((int(row["fatal_run"]) for row in samples), default=0),
        **{f"{name}_delta": int(last.get(name, 0)) - int(first.get(name, 0)) for name in counters},
        "wifi_rx_mbps_average": round(
            (int(last.get("wifi_rx_bytes", 0)) - int(first.get("wifi_rx_bytes", 0))) * 8
            / max(args.seconds, 1) / 1_000_000, 3
        ),
        "wifi_tx_mbps_average": round(
            (int(last.get("wifi_tx_bytes", 0)) - int(first.get("wifi_tx_bytes", 0))) * 8
            / max(args.seconds, 1) / 1_000_000, 3
        ),
        "wifi_rx_mbps_peak": peak_rate_mbps(samples, "wifi_rx_bytes"),
        "wifi_tx_mbps_peak": peak_rate_mbps(samples, "wifi_tx_bytes"),
        "wifi_rx_mbps_peak_during": peak_rate_mbps(samples, "wifi_rx_bytes", phase="during"),
        "wifi_tx_mbps_peak_during": peak_rate_mbps(samples, "wifi_tx_bytes", phase="during"),
        "wifi_rx_bytes_during_increase": counter_increase(
            [row for row in samples if row["phase"] == "during"], "wifi_rx_bytes"
        ),
        "wifi_tx_bytes_during_increase": counter_increase(
            [row for row in samples if row["phase"] == "during"], "wifi_tx_bytes"
        ),
        "last_sample": last or None,
        "raw_log": str(args.output),
        "raw_log_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "producer": "tools/monitor_2g_live_traffic.py",
        "max_output_bytes": args.max_output_bytes,
        "mutations": False,
        "flash": False,
    }
    summary = args.output.with_suffix(args.output.suffix + ".json")
    summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["complete"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
