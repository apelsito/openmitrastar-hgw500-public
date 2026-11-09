#!/usr/bin/env python3
"""Read-only OEM-parity soak for the native open Quantenna 5 GHz AP.

The AP must already be live with its target-local rollback still pending.  This
runner performs no RF, bridge, module, credential or flash writes.  It waits
for a real station, then requires fresh management SSH, bidirectional wifi0
traffic, IRQ8 progress, a live 2.4 GHz AP and the OEM management address for a
bounded soak.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
ACK = "OPENMITRASTAR_QTN_W3_NATIVE_OPEN_SOAK_READ_ONLY"
COUNTERS = ("rx_packets", "tx_packets", "rx_bytes", "tx_bytes", "irq8")


class SoakError(RuntimeError):
    pass


def remote_sample(expected_ip: str) -> str:
    return rf'''
set -eu
cli=/tmp/hostapd-cli-qtn-v4
test -x "$cli"
(test -e /sys/class/net/br0/brif/eth1_emac1 || \
 (test -e /sys/class/net/br0/brif/eth0 && \
  dmesg | grep -Fq 'OMEMACSW stage=symbols-only-ready target=mitrastar,hgw-500bna-qcv2'))
test -e /sys/class/net/br0/brif/wifi0
test -e /sys/class/net/br0/brif/wlan0
test "$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable)" = 1
test "$(cat /sys/module/hbm/parameters/w3_hbm_timer_reclaim_enable)" = 0
ifconfig br0 | grep -Eq 'inet (addr:)?{re.escape(expected_ip)}([[:space:]]|$)'
"$cli" -p /var/run/hostapd -i wifi0 ping 2>/dev/null | grep -qx PONG
/usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null | grep -q '^state=ENABLED$'
assoc=$("$cli" -p /var/run/hostapd -i wifi0 all_sta 2>/dev/null | grep -Ec '^[0-9a-fA-F]{{2}}(:[0-9a-fA-F]{{2}}){{5}}$' || true)
case "$assoc" in ''|*[!0-9]*) exit 201 ;; esac
for name in rx_packets tx_packets rx_bytes tx_bytes; do
	eval "$name=$(cat /sys/class/net/wifi0/statistics/$name)"
	eval "value=\$$name"
	case "$value" in ''|*[!0-9]*) exit 202 ;; esac
done
wlan0_rx=$(cat /sys/class/net/wlan0/statistics/rx_packets)
wlan0_tx=$(cat /sys/class/net/wlan0/statistics/tx_packets)
irq8=$(awk '$1 == "8:" {{ for (i=2; i<=NF; i++) if ($i ~ /^[0-9]+$/) n += $i; found=1 }} END {{ if (!found) exit 1; print n+0 }}' /proc/interrupts)
fatal=$(dmesg | grep -Eic 'MuC:.*exception|MuC exception|MuC has halted|forcing reboot|OMQDRV.*start-fail|Kernel panic|Oops:|BUG:|Unable to handle' || true)
printf 'OM5GNATIVE assoc=%s rx_packets=%s tx_packets=%s rx_bytes=%s tx_bytes=%s irq8=%s wlan0_rx=%s wlan0_tx=%s fatal=%s management=1 radio2g=1 timer_reclaim=0\n' \
	"$assoc" "$rx_packets" "$tx_packets" "$rx_bytes" "$tx_bytes" "$irq8" "$wlan0_rx" "$wlan0_tx" "$fatal"
'''.strip()


SAMPLE_RE = re.compile(
    r"OM5GNATIVE assoc=(\d+) rx_packets=(\d+) tx_packets=(\d+) "
    r"rx_bytes=(\d+) tx_bytes=(\d+) irq8=(\d+) wlan0_rx=(\d+) "
    r"wlan0_tx=(\d+) fatal=(\d+) management=(\d+) radio2g=(\d+) "
    r"timer_reclaim=(\d+)"
)


def sample(host: str, expected_ip: str, timeout: int = 15) -> dict[str, int] | None:
    result = subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", remote_sample(expected_ip),
         "--host", host, "--timeout", str(timeout)],
        cwd=ROOT, text=True, capture_output=True, timeout=timeout + 15,
        check=False,
    )
    if result.returncode:
        return None
    match = SAMPLE_RE.search(result.stdout)
    if not match:
        return None
    keys = (
        "assoc", "rx_packets", "tx_packets", "rx_bytes", "tx_bytes",
        "irq8", "wlan0_rx", "wlan0_tx", "fatal", "management",
        "radio2g", "timer_reclaim",
    )
    return dict(zip(keys, map(int, match.groups()), strict=True))


def violation(current: dict[str, int]) -> str | None:
    if current["assoc"] < 1:
        return "association-lost"
    for key in ("management", "radio2g"):
        if current[key] != 1:
            return f"{key}-lost"
    if current["timer_reclaim"] != 0:
        return "hbm-timer-reclaim-enabled"
    if current["fatal"] != 0:
        return "muc-or-kernel-fatal"
    return None


def evaluate(
    samples: list[dict[str, int]], elapsed: float, minimum_seconds: int,
    interval_seconds: int = 5,
) -> dict[str, int | float]:
    if elapsed < minimum_seconds:
        raise SoakError("soak-too-short")
    minimum_samples = max(3, minimum_seconds // interval_seconds - 1)
    if len(samples) < minimum_samples:
        raise SoakError("insufficient-management-samples")
    for current in samples:
        problem = violation(current)
        if problem:
            raise SoakError(problem)
    monotonic = (*COUNTERS, "wlan0_rx", "wlan0_tx")
    for previous, current in zip(samples, samples[1:]):
        for key in monotonic:
            if current[key] < previous[key]:
                raise SoakError(f"counter-regressed:{key}")
    first, last = samples[0], samples[-1]
    deltas = {key: last[key] - first[key] for key in COUNTERS}
    for key in COUNTERS:
        if deltas[key] <= 0:
            raise SoakError(f"no-progress:{key}")
    if deltas["irq8"] / elapsed > 50_000:
        raise SoakError("irq8-storm")
    return {
        **{f"{key}_delta": value for key, value in deltas.items()},
        "elapsed_seconds": elapsed,
        "samples": len(samples),
        "association_min": min(item["assoc"] for item in samples),
        "management_ssh_sessions": len(samples),
    }


def write_report(output_dir: Path, status: str, result: dict[str, object]) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ("native-open-5g-soak-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
    document = {
        "status": status,
        "scope": "5GHz channel36 open AP local association/data path",
        "management_ipv4": "192.168.1.90",
        "radio2g_preserved": True,
        "hbm_timer_reclaim": False,
        "internet": "UNVERIFIED",
        "dfs": "UNVERIFIED",
        "result": result,
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--interval", type=int, default=5)
    parser.add_argument("--association-wait-seconds", type=int, default=300)
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "outputs/f3-certification/5g-native-open")
    args = parser.parse_args()
    try:
        ipaddress.IPv4Address(args.host)
    except ipaddress.AddressValueError as exc:
        raise SystemExit(f"invalid --host: {exc}") from exc
    if not 180 <= args.seconds <= 900:
        raise SystemExit("--seconds must be 180..900")
    if not 3 <= args.interval <= 15:
        raise SystemExit("--interval must be 3..15")
    if not 30 <= args.association_wait_seconds <= 600:
        raise SystemExit("--association-wait-seconds must be 30..600")
    if not args.execute:
        print(json.dumps({
            "mode": "dry-run", "host": args.host, "seconds": args.seconds,
            "association_required": True, "bidirectional_progress": True,
            "irq8_progress": True, "radio2g_preserved": True,
            "hbm_timer_reclaim": False, "channel": 36, "bandwidth_mhz": 80,
            "security": "OPEN", "flash": False, "dfs": False,
        }, sort_keys=True))
        print("W3_QTN_NATIVE_OPEN_SOAK_DRY_RUN_PASS=1")
        return 0
    if args.ack != ACK:
        raise SystemExit(f"require --ack {ACK}")

    association_deadline = time.monotonic() + args.association_wait_seconds
    baseline: dict[str, int] | None = None
    while time.monotonic() < association_deadline:
        current = sample(args.host, args.host)
        if current is None:
            raise SystemExit("management/sample failed before association")
        if current["fatal"] or current["management"] != 1 or current["radio2g"] != 1:
            raise SystemExit("pre-soak health failure")
        if current["assoc"] >= 1:
            baseline = current
            break
        print("OM5GNATIVE state=waiting-client association=0", flush=True)
        time.sleep(args.interval)
    if baseline is None:
        raise SystemExit("client association timeout")

    samples = [baseline]
    started = time.monotonic()
    deadline = started + args.seconds
    next_tick = started + args.interval
    while time.monotonic() < deadline:
        time.sleep(max(0.0, next_tick - time.monotonic()))
        current = sample(args.host, args.host)
        if current is None:
            raise SystemExit("management/sample failed during soak")
        problem = violation(current)
        if problem:
            raise SystemExit(f"soak health failure: {problem}")
        samples.append(current)
        print(
            f"OM5GNATIVE state=soak elapsed={int(time.monotonic() - started)} "
            f"assoc={current['assoc']} rx_packets={current['rx_packets']} "
            f"tx_packets={current['tx_packets']} irq8={current['irq8']} "
            "management=1 radio2g=1 timer_reclaim=0",
            flush=True,
        )
        next_tick += args.interval
    elapsed = time.monotonic() - started
    try:
        result = evaluate(samples, elapsed, args.seconds, args.interval)
    except SoakError as exc:
        report = write_report(args.output_dir.resolve(), "FAIL", {"reason": str(exc)})
        print(f"W3_QTN_NATIVE_OPEN_SOAK_FAIL=1 reason={exc} report={report}", file=sys.stderr)
        return 1
    report = write_report(args.output_dir.resolve(), "PASS", result)
    print(
        "W3_QTN_NATIVE_OPEN_SOAK_PASS=1 "
        f"seconds={int(result['elapsed_seconds'])} samples={result['samples']} "
        f"association_min={result['association_min']} "
        f"rx_packets_delta={result['rx_packets_delta']} "
        f"tx_packets_delta={result['tx_packets_delta']} "
        f"rx_bytes_delta={result['rx_bytes_delta']} "
        f"tx_bytes_delta={result['tx_bytes_delta']} "
        f"irq8_delta={result['irq8_delta']} management=PASS radio2g=PASS "
        f"timer_reclaim=0 internet=UNVERIFIED dfs=UNVERIFIED report={report}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
