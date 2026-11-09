#!/usr/bin/env python3
"""Read-only F3 client/data-plane certification for an already-live wifi0 AP.

This stage never opens RF, changes qdrv, reconfigures networking, reads a PSK,
tests Internet, runs a speedtest, or enters DFS.  It observes a real associated
client for ten minutes and certifies only the 5 GHz local radio/data plane.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import time

import monitor_qtn_w3_5g_client as client_monitor


ROOT = Path(__file__).resolve().parents[1]
CLOSED = ROOT / "work/mission-state/w3-offline/W3_QTN_5G_F3_CLIENT_CERT_GATE.env"
APPROVED = ROOT / "work/mission-state/w3-offline/W3_QTN_5G_F3_CLIENT_CERT_GATE.approved.env"
MONITOR = ROOT / "tools/monitor_qtn_w3_5g_client.py"
ACK = "OPENMITRASTAR_QTN_W3_5G_F3_CLIENT_CERT_READ_ONLY"
CONTROL_PASS = "W3_QTN_5G_AUTOPILOT_AP_CONTROL_PLANE_PASS=1"
COUNTERS = ("rx_bytes", "tx_bytes", "rx_packets", "tx_packets")
IRQS = ("irq8", "irq9", "irq10")

HEALTH_REMOTE = r'''
root=/tmp/w3-qcsapi-5g-ap
runtime=$root/runtime
test -x "$runtime/bin/call_qcsapi" || exit 61
test -e /sys/class/net/wifi0 || exit 62
test -e /sys/class/net/br0/brif/wifi0 || exit 63
test -e /sys/class/net/br0/brif/eth1_emac1 || exit 64
test "$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable 2>/dev/null)" = 1 || exit 65
grep -q '^qdrv ' /proc/modules || exit 66
qc() {
  LD_LIBRARY_PATH="$runtime/lib" "$runtime/lib/ld-uClibc-0.9.29.so" \
    "$runtime/bin/call_qcsapi" "$@" 2>/dev/null
}
channel=$(qc get_channel wifi0) || exit 67
bw=$(qc get_bw wifi0) || exit 68
region=$(qc get_regulatory_region wifi0) || exit 69
case "$channel:$bw:$region" in *[!0-9A-Za-z:_-]*) exit 70 ;; esac
irq_count() {
  awk -v irq="$1:" '$1 == irq { for (i=2; i<=NF; i++) if ($i ~ /^[0-9]+$/) n += $i } END { print n+0 }' /proc/interrupts
}
irq8=$(irq_count 8); irq9=$(irq_count 9); irq10=$(irq_count 10)
for value in "$irq8" "$irq9" "$irq10"; do case "$value" in ''|*[!0-9]*) exit 71 ;; esac; done
fatal=$(dmesg | grep -Eic 'MuC:.*exception|MuC exception|MuC has halted|forcing reboot|OMQDRV.*start-fail|Kernel panic|Oops:|BUG:|Unable to handle' || true)
case "$fatal" in ''|*[!0-9]*) exit 72 ;; esac
watchdog=0
dmesg | grep -q 'OMWDT stage=armed' && dmesg | grep -q 'OMWDT stage=pet first=1' && watchdog=1
printf 'OM5GF3 irq8=%s irq9=%s irq10=%s fatal=%s watchdog=%s qdrv=1 rf=1 bridge=1 channel=%s bw=%s region=%s\n' \
  "$irq8" "$irq9" "$irq10" "$fatal" "$watchdog" "$channel" "$bw" "$region"
'''.strip()

HEALTH_RE = re.compile(
    r"OM5GF3 irq8=(\d+) irq9=(\d+) irq10=(\d+) fatal=(\d+) "
    r"watchdog=(\d+) qdrv=(\d+) rf=(\d+) bridge=(\d+) "
    r"channel=(\d+) bw=(\d+) region=([A-Za-z0-9_-]+)"
)


class CertificationError(RuntimeError):
    pass


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def values(path: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def exact_marker(text: str, marker: str) -> bool:
    return any(line == marker or line.startswith(marker + " ") for line in text.splitlines())


def verify_gate(gate: dict[str, str]) -> None:
    required = {
        "W3_F3_CLIENT_CERT_ONLY": "1",
        "W3_READ_ONLY": "1",
        "W3_RF_WRITE_ENABLE": "0",
        "W3_QDRV_WRITE_ENABLE": "0",
        "W3_NETWORK_CONFIG_WRITE_ENABLE": "0",
        "W3_FLASH_ENABLE": "0",
        "W3_ASSOCIATION_MIN": "1",
        "W3_ASSOCIATION_EVERY_SAMPLE": "1",
        "W3_COUNTERS_REQUIRED": "rx_bytes,tx_bytes,rx_packets,tx_packets",
        "W3_IRQS_REQUIRED": "8,9,10",
        "W3_IRQ8_PROGRESS_REQUIRED": "1",
        "W3_IRQ9_10_PROGRESS_REQUIRED": "0",
        "W3_FATAL_MAX": "0",
        "W3_SOAK_SECONDS": "600",
        "W3_INTERVAL_SECONDS": "10",
        "W3_MIN_SOAK_SAMPLES": "58",
        "W3_ASSOCIATION_WAIT_SECONDS": "300",
        "W3_SSH_FAILURES_MAX": "0",
        "W3_EXPECTED_CHANNEL": "36",
        "W3_EXPECTED_BW": "80",
        "W3_EXPECTED_REGION": "es",
        "W3_INTERNET": "UNVERIFIED",
        "W3_SPEEDTEST": "UNVERIFIED",
        "W3_DFS": "UNVERIFIED",
        "W3_F3_FULL": "0",
    }
    for key, wanted in required.items():
        if gate.get(key) != wanted:
            raise SystemExit(f"F3 client-cert gate mismatch: {key}")
    if gate.get("W3_MONITOR_SHA256") != sha256(MONITOR):
        raise SystemExit("F3 client-cert monitor hash mismatch")
    max_irq_rate = int(gate.get("W3_IRQ_MAX_PER_SECOND", "0"))
    if not 1000 <= max_irq_rate <= 100000:
        raise SystemExit("F3 client-cert IRQ rate gate invalid")


def health_sample(host: str, timeout: int = 15) -> dict[str, int | str] | None:
    result = subprocess.run(
        [sys.executable, "tools/ramssh_exec.py", HEALTH_REMOTE,
         "--host", host, "--timeout", str(timeout)],
        cwd=ROOT, text=True, capture_output=True, timeout=timeout + 15, check=False,
    )
    if result.returncode != 0:
        return None
    match = HEALTH_RE.search(result.stdout)
    if not match:
        return None
    keys = ("irq8", "irq9", "irq10", "fatal", "watchdog", "qdrv", "rf",
            "bridge", "channel", "bw", "region")
    values_raw = match.groups()
    parsed: dict[str, int | str] = {
        key: (value if key == "region" else int(value))
        for key, value in zip(keys, values_raw, strict=True)
    }
    return parsed


def sample_f3(host: str) -> dict[str, int | str] | None:
    """Reuse the established client monitor and add health/IRQ observations."""
    client = client_monitor.sample(host)
    if client is None:
        return None
    health = health_sample(host)
    if health is None:
        return None
    return {**client, **health, "ssh_sessions": 2}


def health_violation(sample: dict[str, int | str], gate: dict[str, str]) -> str | None:
    if int(sample["assoc"]) < int(gate["W3_ASSOCIATION_MIN"]):
        return "association-lost"
    for key in ("hostapd", "watchdog", "qdrv", "rf", "bridge"):
        if int(sample[key]) != 1:
            return f"{key}-not-ready"
    if int(sample["fatal"]) > int(gate["W3_FATAL_MAX"]):
        return "muc-or-kernel-fatal"
    if int(sample["channel"]) != int(gate["W3_EXPECTED_CHANNEL"]):
        return "channel-changed"
    if int(sample["bw"]) != int(gate["W3_EXPECTED_BW"]):
        return "bandwidth-changed"
    if str(sample["region"]).lower() != gate["W3_EXPECTED_REGION"]:
        return "region-changed"
    return None


def evaluate_soak(
    samples: list[dict[str, int | str]], elapsed: float, gate: dict[str, str]
) -> dict[str, int | float]:
    soak_seconds = int(gate["W3_SOAK_SECONDS"])
    if elapsed < soak_seconds:
        raise CertificationError("soak-too-short")
    if len(samples) < int(gate["W3_MIN_SOAK_SAMPLES"]):
        raise CertificationError("insufficient-ssh-samples")
    for current in samples:
        violation = health_violation(current, gate)
        if violation:
            raise CertificationError(violation)
    for previous, current in zip(samples, samples[1:]):
        for key in (*COUNTERS, *IRQS):
            if int(current[key]) < int(previous[key]):
                raise CertificationError(f"counter-regressed:{key}")
    first, last = samples[0], samples[-1]
    deltas = {key: int(last[key]) - int(first[key]) for key in (*COUNTERS, *IRQS)}
    for key in COUNTERS:
        if deltas[key] <= 0:
            raise CertificationError(f"no-progress:{key}")
    if deltas["irq8"] <= 0:
        raise CertificationError("no-progress:irq8")
    max_rate = int(gate["W3_IRQ_MAX_PER_SECOND"])
    for key in IRQS:
        if deltas[key] / elapsed > max_rate:
            raise CertificationError(f"irq-storm:{key}")
    return {
        **{f"{key}_delta": value for key, value in deltas.items()},
        "samples": len(samples),
        "ssh_sessions": sum(int(sample["ssh_sessions"]) for sample in samples),
        "assoc_min": min(int(sample["assoc"]) for sample in samples),
        "elapsed_seconds": elapsed,
    }


def write_report(output_dir: Path, result: dict[str, object], status: str) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / ("f3-5g-client-" + time.strftime("%Y%m%d-%H%M%S") + ".json")
    document = {
        "status": status,
        "scope": "5GHz local AP association/data-plane soak",
        "read_only": True,
        "result": result,
        "internet": "UNVERIFIED",
        "speedtest": "UNVERIFIED",
        "dfs": "UNVERIFIED",
        "f3_full": False,
    }
    path.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack")
    parser.add_argument("--autopilot-log", type=Path)
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--output-dir", type=Path,
                        default=ROOT / "outputs/f3-certification/5g-client")
    args = parser.parse_args()

    gate_path = APPROVED if args.execute else CLOSED
    gate = values(gate_path)
    verify_gate(gate)
    summary = {
        "mode": "execute" if args.execute else "dry-run",
        "scope": "5GHz-local-client-data-plane-only",
        "read_only": True,
        "association_min": 1,
        "soak_seconds": 600,
        "interval_seconds": 10,
        "ssh_failures_max": 0,
        "irqs": [8, 9, 10],
        "internet": "UNVERIFIED",
        "speedtest": "UNVERIFIED",
        "dfs": "UNVERIFIED",
        "f3_full": False,
    }
    print(summary)
    if not args.execute:
        print("W3_QTN_5G_F3_CLIENT_CERT_DRY_RUN_PASS=1 read_only=1 F3=0")
        return 0
    if args.ack != ACK or gate.get("W3_F3_CLIENT_CERT_APPROVED") != "1":
        raise SystemExit(f"require --ack {ACK} and approved gate")
    if args.autopilot_log is None:
        raise SystemExit("--autopilot-log is required")
    args.autopilot_log = args.autopilot_log.resolve()
    if not client_monitor.wait_control_plane(args.autopilot_log, 30):
        raise SystemExit("AP control-plane marker not found")
    log_text = args.autopilot_log.read_text(encoding="utf-8", errors="replace")
    if not exact_marker(log_text, CONTROL_PASS):
        raise SystemExit("AP control-plane marker is not an exact line")

    association_deadline = time.monotonic() + int(gate["W3_ASSOCIATION_WAIT_SECONDS"])
    baseline: dict[str, int | str] | None = None
    while time.monotonic() < association_deadline:
        current = sample_f3(args.host)
        if current is None:
            raise SystemExit("management SSH/sample failed before association")
        violation = health_violation({**current, "assoc": max(1, int(current["assoc"]))}, gate)
        if violation and violation != "association-lost":
            raise SystemExit(f"pre-soak health failure: {violation}")
        if int(current["assoc"]) >= int(gate["W3_ASSOCIATION_MIN"]):
            baseline = current
            break
        print("OM5GF3 state=waiting-client association=0", flush=True)
        time.sleep(int(gate["W3_INTERVAL_SECONDS"]))
    if baseline is None:
        raise SystemExit("client association timeout")

    samples: list[dict[str, int | str]] = [baseline]
    started = time.monotonic()
    deadline = started + int(gate["W3_SOAK_SECONDS"])
    next_tick = started + int(gate["W3_INTERVAL_SECONDS"])
    while time.monotonic() < deadline:
        delay = next_tick - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        current = sample_f3(args.host)
        if current is None:
            raise SystemExit("management SSH/sample failed during soak")
        violation = health_violation(current, gate)
        if violation:
            raise SystemExit(f"soak health failure: {violation}")
        samples.append(current)
        print(
            "OM5GF3 state=soak "
            f"elapsed={int(time.monotonic() - started)} assoc={current['assoc']} "
            f"rx_packets={current['rx_packets']} tx_packets={current['tx_packets']} "
            f"irq8={current['irq8']} irq9={current['irq9']} irq10={current['irq10']}",
            flush=True,
        )
        next_tick += int(gate["W3_INTERVAL_SECONDS"])

    elapsed = time.monotonic() - started
    try:
        result = evaluate_soak(samples, elapsed, gate)
    except CertificationError as exc:
        report = write_report(args.output_dir.resolve(), {"reason": str(exc)}, "FAIL")
        print(f"W3_QTN_5G_F3_CLIENT_CERT_FAIL=1 reason={exc} report={report}", file=sys.stderr)
        return 1
    report = write_report(args.output_dir.resolve(), result, "PASS")
    print(
        "W3_QTN_5G_F3_CLIENT_TRAFFIC_SOAK_PASS=1 "
        f"soak_seconds={int(result['elapsed_seconds'])} samples={result['samples']} "
        f"associations_min={result['assoc_min']} ssh_sessions={result['ssh_sessions']} "
        f"rx_bytes_delta={result['rx_bytes_delta']} tx_bytes_delta={result['tx_bytes_delta']} "
        f"rx_packets_delta={result['rx_packets_delta']} tx_packets_delta={result['tx_packets_delta']} "
        f"irq8_delta={result['irq8_delta']} irq9_delta={result['irq9_delta']} "
        f"irq10_delta={result['irq10_delta']} fatal=0 "
        "internet=UNVERIFIED speedtest=UNVERIFIED dfs=UNVERIFIED F3_FULL=0 "
        f"report={report}",
        flush=True,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
