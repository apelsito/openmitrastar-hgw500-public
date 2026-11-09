#!/usr/bin/env python3
"""Read-only, client-MAC-redacted Q3 AP association monitor."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
MAC_RE = re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}:){5}[0-9a-f]{2}(?![0-9a-f])")

REMOTE = r'''
set -eu
echo SAMPLE_BEGIN
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 ping 2>/dev/null | awk '{print "HOSTAPD_PING=" $0}'
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 all_sta 2>/dev/null | awk '
BEGIN{IGNORECASE=1}
/^[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]:[0-9a-f][0-9a-f]$/ {stations++; next}
/^flags=/ {if($0 ~ /AUTHORIZED/) authorized++; if($0 ~ /AUTH/) authflag++; if($0 ~ /ASSOC/) assocflag++}
/^connected_time=/ {split($0,a,"="); if(a[2]+0>max_connected) max_connected=a[2]+0}
END{print "ALL_STA_COUNT=" stations+0; print "ALL_STA_AUTHORIZED=" authorized+0; print "ALL_STA_AUTH_FLAG=" authflag+0; print "ALL_STA_ASSOC_FLAG=" assocflag+0; print "ALL_STA_MAX_CONNECTED_SECONDS=" max_connected+0}'
/usr/sbin/hostapd-cli-qtn -p /var/run/hostapd -i wifi0 mib 2>/dev/null | awk -F= '
$1 == "dot11RSNA4WayHandshakeFailures" {print "MIB_4WAY_FAILURES=" $2}
$1 == "dot11RSNAAuthenticationSuiteSelected" {print "MIB_AUTH_SELECTED_ZERO=" ($2 == "00-00-00-0")}
$1 == "dot11RSNAAuthenticationSuiteRequested" {print "MIB_AUTH_REQUESTED_ZERO=" ($2 == "00-00-00-0")}'
log=/run/openmitrastar/radio5g/hostapd.log
if [ -r "$log" ]; then
  awk 'BEGIN{IGNORECASE=1}
  {
    low=tolower($0); has_peer=match(low,/([0-9a-f][0-9a-f]:){5}[0-9a-f][0-9a-f]/)
    if(has_peer && low ~ /authentication|authenticated/) auth_peer++
    if(has_peer && low ~ /association|associated/) assoc_peer++
    if(low ~ /ap-sta-connected/) connected++
    if(low ~ /ap-sta-disconnected/) disconnected++
    if(has_peer && low ~ /deauth/) deauth_peer++
    if(has_peer && low ~ /disassoc/) disassoc_peer++
    if(low ~ /deauthenticate all stations/) deauth_all++
  }
  END{
    print "LOG_AUTH_PEER_EVENTS=" auth_peer+0
    print "LOG_ASSOC_PEER_EVENTS=" assoc_peer+0
    print "LOG_CONNECTED_EVENTS=" connected+0
    print "LOG_DISCONNECTED_EVENTS=" disconnected+0
    print "LOG_DEAUTH_PEER_EVENTS=" deauth_peer+0
    print "LOG_DISASSOC_PEER_EVENTS=" disassoc_peer+0
    print "LOG_DEAUTH_ALL_EVENTS=" deauth_all+0
  }' "$log"
else
  echo LOG_MISSING=1
fi
for n in rx_packets tx_packets rx_bytes tx_bytes rx_errors tx_errors rx_dropped tx_dropped; do
  v=$(cat /sys/class/net/wifi0/statistics/$n 2>/dev/null || echo -1)
  echo WIFI0_${n}=$v
done
echo WIFI0_CARRIER=$(cat /sys/class/net/wifi0/carrier 2>/dev/null || echo -1)
echo WIFI0_FLAGS=$(cat /sys/class/net/wifi0/flags 2>/dev/null || echo -1)
echo RF=$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable 2>/dev/null || echo -1)
echo LED=$(cat /sys/class/leds/openmitrastar:green:wlan5g/brightness 2>/dev/null || echo -1)
awk '$1 ~ /^(8:|9:|10:)$/ {sum=0; for(i=2;i<=NF;i++) if($i ~ /^[0-9]+$/) sum+=$i; gsub(":","",$1); print "IRQ" $1 "=" sum}' /proc/interrupts
echo SAMPLE_END
'''


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_sample(host: str, timeout: int) -> dict[str, object]:
    result = subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", REMOTE, "--host", host, "--timeout", str(timeout)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        timeout=timeout + 20,
    )
    transcript = result.stdout + result.stderr
    if MAC_RE.search(transcript):
        raise RuntimeError("privacy gate: remote output contained a MAC-shaped value")
    if result.returncode != 0 or "SAMPLE_BEGIN" not in result.stdout or "SAMPLE_END" not in result.stdout:
        raise RuntimeError(f"sample failed rc={result.returncode}: {transcript[-500:]}")
    sample: dict[str, object] = {"captured_at": now()}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if not re.fullmatch(r"[A-Za-z0-9_]+", key):
            continue
        if re.fullmatch(r"-?[0-9]+", value):
            sample[key.lower()] = int(value)
        else:
            sample[key.lower()] = value
    return sample


def delta(first: dict[str, object], last: dict[str, object], key: str) -> int | None:
    a, b = first.get(key), last.get(key)
    if isinstance(a, int) and isinstance(b, int):
        return b - a
    return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--duration-seconds", type=int, default=300)
    parser.add_argument("--interval-seconds", type=int, default=10)
    parser.add_argument("--timeout", type=int, default=25)
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs/f3-certification/q3-ap-association-readonly",
    )
    args = parser.parse_args()
    if args.duration_seconds < 1 or args.interval_seconds < 1:
        raise SystemExit("duration and interval must be positive")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    deadline = started + args.duration_seconds
    samples: list[dict[str, object]] = []
    index = 0
    while True:
        sample = read_sample(args.host, args.timeout)
        sample["index"] = index
        samples.append(sample)
        print(
            "Q3_AP_SAMPLE "
            f"index={index} ping={sample.get('hostapd_ping')} "
            f"sta={sample.get('all_sta_count')} auth={sample.get('log_auth_peer_events')} "
            f"assoc={sample.get('log_assoc_peer_events')} rx={sample.get('wifi0_rx_packets')}",
            flush=True,
        )
        index += 1
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(args.interval_seconds, remaining))

    first, last = samples[0], samples[-1]
    attempt_keys = (
        "log_auth_peer_events", "log_assoc_peer_events", "log_connected_events",
        "log_deauth_peer_events", "log_disassoc_peer_events",
    )
    attempt_observed = any(isinstance(last.get(key), int) and int(last[key]) > 0 for key in attempt_keys)
    summary = {
        "schema": "openmitrastar.q3-ap-association-readonly/v1",
        "classification": "READ_ONLY-CLIENT-MAC-REDACTED",
        "host": args.host,
        "started_at": samples[0]["captured_at"],
        "ended_at": samples[-1]["captured_at"],
        "requested_duration_seconds": args.duration_seconds,
        "elapsed_seconds": round(time.monotonic() - started, 3),
        "interval_seconds": args.interval_seconds,
        "sample_count": len(samples),
        "client_mac_values_collected": False,
        "association_attempt_observed": attempt_observed,
        "final_station_count": last.get("all_sta_count"),
        "final_authorized_count": last.get("all_sta_authorized"),
        "final_log_counters": {key: last.get(key) for key in attempt_keys},
        "counter_deltas": {
            key: delta(first, last, key)
            for key in (
                "wifi0_rx_packets", "wifi0_tx_packets", "wifi0_rx_bytes", "wifi0_tx_bytes",
                "wifi0_rx_errors", "wifi0_tx_errors", "irq8", "irq9", "irq10",
            )
        },
        "all_samples_ap_healthy": all(
            sample.get("hostapd_ping") == "PONG"
            and sample.get("wifi0_carrier") == 1
            and sample.get("rf") == 1
            for sample in samples
        ),
        "samples": samples,
    }
    encoded = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    if MAC_RE.search(encoded):
        raise RuntimeError("privacy gate: report contained a MAC-shaped value")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    output = args.output_dir / f"q3-ap-association-readonly-{stamp}.json"
    output.write_text(encoded, encoding="utf-8", newline="\n")
    print(
        "Q3_AP_ASSOCIATION_CAPTURE_PASS "
        f"samples={len(samples)} attempts={int(attempt_observed)} "
        f"mac_values=0 output={output}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
