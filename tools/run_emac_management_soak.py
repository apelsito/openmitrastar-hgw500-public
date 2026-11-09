#!/usr/bin/env python3
"""Evidence-producing EMAC management soak for the RAM-only lab target."""

from __future__ import annotations

import argparse
import datetime as dt
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
import paramiko  # noqa: E402


def load_private_key() -> paramiko.Ed25519Key:
    key = subprocess.check_output(
        [
            "wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e",
            "cat", "/home/user/openmitrastar-ramssh-keys/client_ed25519",
        ],
        text=True,
        stderr=subprocess.DEVNULL,
    )
    return paramiko.Ed25519Key.from_private_key(io.StringIO(key))


def ping(host: str, count: int = 1) -> bool:
    return subprocess.run(
        ["ping", "-n", str(count), "-w", "1000", host],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode == 0


def ssh_command(host: str, key: paramiko.Ed25519Key, command: str) -> str:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            host,
            port=22,
            username="root",
            pkey=key,
            look_for_keys=False,
            allow_agent=False,
            timeout=4,
            banner_timeout=6,
            auth_timeout=6,
        )
        _, stdout, stderr = client.exec_command(command, timeout=12)
        out = stdout.read().decode("utf-8", "replace")
        err = stderr.read().decode("utf-8", "replace")
        rc = stdout.channel.recv_exit_status()
        if rc:
            raise RuntimeError(f"remote rc={rc}: {err.strip()}")
        return out
    finally:
        client.close()


def parse_snapshot(text: str) -> dict[str, int | float]:
    lines = text.splitlines()
    if not lines:
        raise ValueError("empty SSH snapshot")
    uptime = float(lines[0].split()[0])
    eth_line = next(line for line in lines if re.match(r"\s*eth0:", line))
    fields = eth_line.replace(":", " ").split()
    # iface rx_bytes rx_packets rx_err rx_drop ... tx_bytes tx_packets tx_err ...
    values = [int(value) for value in fields[1:]]
    irq20_line = next((line for line in lines if re.match(r"\s*20:", line)), "")
    irq28_line = next((line for line in lines if re.match(r"\s*28:", line)), "")

    def irq_count(line: str) -> int:
        match = re.match(r"\s*\d+:\s+(\d+)", line)
        return int(match.group(1)) if match else 0

    return {
        "uptime": uptime,
        "rx_bytes": values[0],
        "rx_packets": values[1],
        "rx_errors": values[2],
        "rx_dropped": values[3],
        "tx_bytes": values[8],
        "tx_packets": values[9],
        "tx_errors": values[10],
        "tx_dropped": values[11],
        "irq20": irq_count(irq20_line),
        "irq28": irq_count(irq28_line),
    }


def integer_series(samples: list[dict[str, object]], key: str) -> list[int] | None:
    """Return a complete integer counter series, or None when evidence is missing."""
    if not samples or any(key not in sample for sample in samples):
        return None
    return [int(sample[key]) for sample in samples]


def is_monotonic(values: list[int] | None) -> bool:
    return bool(values) and all(current >= previous for previous, current in zip(values, values[1:]))


def strictly_progresses(values: list[int] | None) -> bool:
    return bool(values) and len(values) >= 2 and all(
        current > previous for previous, current in zip(values, values[1:])
    )


def appended_log(before: str, after: str) -> tuple[str, bool]:
    """Extract log lines appended after a baseline without clearing kernel logs."""
    before_lines = before.splitlines()
    after_lines = after.splitlines()
    if not before_lines:
        return after, False
    if after_lines[:len(before_lines)] == before_lines:
        return "\n".join(after_lines[len(before_lines):]), True
    # Accept a shifted ring buffer only when the final baseline line still exists.
    try:
        boundary = len(after_lines) - 1 - after_lines[::-1].index(before_lines[-1])
    except ValueError:
        return after, False
    return "\n".join(after_lines[boundary + 1:]), True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.200")
    parser.add_argument("--duration", type=int, default=600)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--burst-every", type=int, default=120)
    parser.add_argument("--evidence-dir")
    args = parser.parse_args()
    if args.duration < 60 or args.interval < 2 or args.burst_every < 1:
        raise SystemExit("duration must be >=60, interval >=2, and burst-every >=1")

    stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    evidence = Path(args.evidence_dir) if args.evidence_dir else (
        ROOT / "outputs" / "kernel-port" / "emac-management-soak" / stamp
    )
    evidence.mkdir(parents=True, exist_ok=False)
    samples_path = evidence / "samples.jsonl"
    dmesg_path = evidence / "dmesg.log"
    dmesg_before_path = evidence / "dmesg-before.log"
    summary_path = evidence / "summary.json"
    key = load_private_key()
    try:
        dmesg_before = ssh_command(args.host, key, "dmesg")
    except Exception as exc:
        dmesg_before = f"DMESG_BASELINE_FAIL {type(exc).__name__}: {exc}\n"
    dmesg_before_path.write_text(dmesg_before, encoding="utf-8")
    start = time.monotonic()
    next_burst = 0
    samples: list[dict[str, object]] = []

    while True:
        elapsed = int(time.monotonic() - start)
        burst_ping: bool | None = None
        if elapsed >= next_burst:
            burst_ping = ping(args.host, count=20)
            while next_burst <= elapsed:
                next_burst += args.burst_every
        sample: dict[str, object] = {
            "elapsed_s": elapsed,
            "timestamp": dt.datetime.now(dt.timezone.utc).isoformat(),
            "ping": ping(args.host),
            "ssh": False,
        }
        if burst_ping is not None:
            sample["burst_ping"] = burst_ping
        try:
            raw = ssh_command(
                args.host,
                key,
                "cat /proc/uptime; cat /proc/net/dev; cat /proc/interrupts",
            )
            sample.update(parse_snapshot(raw))
            sample["ssh"] = True
        except Exception as exc:  # evidence path, do not abort the whole soak
            sample["error"] = f"{type(exc).__name__}: {exc}"
        samples.append(sample)
        with samples_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, sort_keys=True) + "\n")
        print(
            "EMAC_SOAK_SAMPLE "
            f"t={elapsed} ping={int(bool(sample['ping']))} "
            f"ssh={int(bool(sample['ssh']))} "
            f"rx={sample.get('rx_packets', '-')} "
            f"tx={sample.get('tx_packets', '-')} "
            f"irq20={sample.get('irq20', '-')}",
            flush=True,
        )
        remaining = args.duration - (time.monotonic() - start)
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))

    duration_observed = time.monotonic() - start

    try:
        dmesg = ssh_command(args.host, key, "dmesg")
    except Exception as exc:
        dmesg = f"DMESG_FETCH_FAIL {type(exc).__name__}: {exc}\n"
    dmesg_path.write_text(dmesg, encoding="utf-8")
    dmesg_delta, dmesg_delta_reliable = appended_log(dmesg_before, dmesg)

    successful = [sample for sample in samples if sample.get("ssh")]
    fatal_pattern = re.compile(
        r"Kernel panic|\bOops\b|BUG:|use-after-free|KASAN|nobody cared|"
        r"Unable to handle kernel|DMA.*error|descriptor.*error",
        re.IGNORECASE,
    )
    rearm_count = dmesg_delta.count("OMEMAC poll rearmed")
    tick_count = dmesg_delta.count("OMEMAC poll tick=")
    enabled_count = dmesg.count("OMEMAC poll-fallback enabled")
    direct_fallback_count = dmesg.count("with polling fallback")
    rx_series = integer_series(successful, "rx_packets")
    tx_series = integer_series(successful, "tx_packets")
    irq20_series = integer_series(successful, "irq20")
    uptime_series = integer_series(successful, "uptime")
    rx_error_series = integer_series(successful, "rx_errors")
    tx_error_series = integer_series(successful, "tx_errors")
    bursts = [sample for sample in samples if "burst_ping" in sample]
    summary = {
        "schema": "openmitrastar.emac-management-soak/v1",
        "duration_requested_s": args.duration,
        "duration_observed_s": round(duration_observed, 3),
        "samples": len(samples),
        "ping_pass": sum(bool(sample.get("ping")) for sample in samples),
        "ssh_pass": len(successful),
        "rx_start": successful[0].get("rx_packets") if successful else None,
        "rx_end": successful[-1].get("rx_packets") if successful else None,
        "tx_start": successful[0].get("tx_packets") if successful else None,
        "tx_end": successful[-1].get("tx_packets") if successful else None,
        "irq20_start": successful[0].get("irq20") if successful else None,
        "irq20_end": successful[-1].get("irq20") if successful else None,
        "rx_strict_progress": strictly_progresses(rx_series),
        "tx_strict_progress": strictly_progresses(tx_series),
        "irq20_monotonic": is_monotonic(irq20_series),
        "uptime_monotonic": is_monotonic(uptime_series),
        "rx_errors_delta": (
            rx_error_series[-1] - rx_error_series[0] if rx_error_series else None
        ),
        "tx_errors_delta": (
            tx_error_series[-1] - tx_error_series[0] if tx_error_series else None
        ),
        "burst_attempts": len(bursts),
        "burst_pass": sum(bool(sample.get("burst_ping")) for sample in bursts),
        "poll_enabled_markers": enabled_count,
        "direct_fallback_markers": direct_fallback_count,
        "poll_tick_markers": tick_count,
        "poll_rearm_markers": rearm_count,
        "dmesg_delta_reliable": dmesg_delta_reliable,
        "fatal_log_match": bool(fatal_pattern.search(dmesg_delta)),
    }
    fail_reasons: list[str] = []
    checks = (
        (bool(samples), "no_samples"),
        (duration_observed >= args.duration, "duration_short"),
        (len(successful) == len(samples), "ssh_failure"),
        (summary["ping_pass"] == len(samples), "ping_failure"),
        (bool(bursts) and summary["burst_pass"] == len(bursts), "burst_ping_failure"),
        (bool(summary["rx_strict_progress"]), "rx_not_continuously_advancing"),
        (bool(summary["tx_strict_progress"]), "tx_not_continuously_advancing"),
        (bool(summary["irq20_monotonic"]), "irq20_missing_or_nonmonotonic"),
        (bool(summary["uptime_monotonic"]), "uptime_missing_or_nonmonotonic"),
        (summary["rx_errors_delta"] == 0, "rx_errors_increased"),
        (summary["tx_errors_delta"] == 0, "tx_errors_increased"),
        (direct_fallback_count >= 1, "direct_fallback_marker_missing"),
        (enabled_count >= 1, "poll_enabled_marker_missing"),
        (tick_count >= 2, "poll_ticks_insufficient"),
        (rearm_count >= 2, "poll_rearms_insufficient"),
        (dmesg_delta_reliable, "dmesg_delta_unreliable"),
        (not summary["fatal_log_match"], "fatal_kernel_log_match"),
    )
    fail_reasons.extend(reason for passed, reason in checks if not passed)
    summary["fail_reasons"] = fail_reasons
    summary["pass"] = not fail_reasons
    summary_path.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        f"EMAC_SOAK_{'PASS' if summary['pass'] else 'FAIL'} "
        f"evidence={evidence} samples={len(samples)} rearm={rearm_count}",
        flush=True,
    )
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
