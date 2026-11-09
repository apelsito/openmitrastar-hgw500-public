#!/usr/bin/env python3
"""Stream Q3 client/EMAC telemetry through the persistent OpenSSH identity."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import queue
import re
import shlex
import socket
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
REQUIRED_FIELDS = {
    "seq", "uptime", "control", "assoc", "wifi_rx", "wifi_tx",
    "eth_rx", "eth_tx", "irq8", "irq20", "carrier", "rf",
    "br_eth", "br_2g", "br_5g", "radio2g", "fatal",
}


def remote_command(seconds: int, interval: int,
                   hostapd_log: str = "/run/openmitrastar/radio5g/hostapd.log",
                   lightweight: bool = False) -> str:
    samples = seconds // interval
    log_path = shlex.quote(hostapd_log)
    association_sample = "  assoc=0\n" if lightweight else rf"""\
  assoc=$(tail -n 512 {log_path} 2>/dev/null | awk '
    /AP-STA-CONNECTED/ {{ sta[$NF] = 1 }}
    /AP-STA-DISCONNECTED/ {{ delete sta[$NF] }}
    END {{ for (mac in sta) n++; print n + 0 }}
  ' 2>/dev/null)
  [ -n "$assoc" ] || assoc=0
"""
    network_sample = """\
  wifi_rx=0
  wifi_tx=0
  eth_rx=0
  eth_tx=0
  br_rx=0
  br_tx=0
""" if lightweight else """\
  wifi_rx=$(cat /sys/class/net/wifi0/statistics/rx_packets 2>/dev/null); [ -n "$wifi_rx" ] || wifi_rx=0
  wifi_tx=$(cat /sys/class/net/wifi0/statistics/tx_packets 2>/dev/null); [ -n "$wifi_tx" ] || wifi_tx=0
  eth_rx=$(cat /sys/class/net/eth0/statistics/rx_packets 2>/dev/null); [ -n "$eth_rx" ] || eth_rx=0
  eth_tx=$(cat /sys/class/net/eth0/statistics/tx_packets 2>/dev/null); [ -n "$eth_tx" ] || eth_tx=0
  br_rx=$(cat /sys/class/net/br0/statistics/rx_packets 2>/dev/null); [ -n "$br_rx" ] || br_rx=0
  br_tx=$(cat /sys/class/net/br0/statistics/tx_packets 2>/dev/null); [ -n "$br_tx" ] || br_tx=0
"""
    radio_sample = """\
  radio5_state=$(cat /run/openmitrastar/radio5g/state 2>/dev/null)
  if [ "$radio5_state" = ready ] && [ -e /sys/class/net/wifi0 ]; then carrier=1; rf=1; else carrier=0; rf=0; fi
""" if lightweight else """\
  carrier=$(cat /sys/class/net/wifi0/carrier 2>/dev/null); [ "$carrier" = 1 ] || carrier=0
  rf=$(cat /sys/module/qdrv/parameters/openmitrastar_rf_enable 2>/dev/null); [ "$rf" = 1 ] || rf=0
"""
    datapath_sample = """\
  tqe_rx=0
  tqe_tx=0
  emac_irq_count=0
  emac_napi_polls=0
  emac_napi_work=0
  emac_napi_budget=0
  emac_rx_owned=0
  emac_cpu_owned=0
  emac_no_desc=0
  emac_rx_stopped=0
  emac_rx_missed=0
  emac_restarts=0
  emac_restart_no_desc=0
  emac_restart_stopped=0
  emac_restart_missed=0
  emac_restart_stagnant=0
""" if lightweight else """\
  tqe_rx=$(cat /sys/class/net/tqe/statistics/rx_packets 2>/dev/null); [ -n "$tqe_rx" ] || tqe_rx=0
  tqe_tx=$(cat /sys/class/net/tqe/statistics/tx_packets 2>/dev/null); [ -n "$tqe_tx" ] || tqe_tx=0
  emac=/sys/bus/platform/devices/e8000000.ethernet/lyoko_emac_stats
  emac_irq_count=$(sed -n 's/^irq_count=//p' "$emac" 2>/dev/null); [ -n "$emac_irq_count" ] || emac_irq_count=0
  emac_napi_polls=$(sed -n 's/^napi_polls=//p' "$emac" 2>/dev/null); [ -n "$emac_napi_polls" ] || emac_napi_polls=0
  emac_napi_work=$(sed -n 's/^napi_rx_work=//p' "$emac" 2>/dev/null); [ -n "$emac_napi_work" ] || emac_napi_work=0
  emac_napi_budget=$(sed -n 's/^napi_budget_exhaustions=//p' "$emac" 2>/dev/null); [ -n "$emac_napi_budget" ] || emac_napi_budget=0
  emac_rx_owned=$(sed -n 's/^rx_head_dma_owned_samples=//p' "$emac" 2>/dev/null); [ -n "$emac_rx_owned" ] || emac_rx_owned=0
  emac_cpu_owned=$(sed -n 's/^rx_head_cpu_owned_descs=//p' "$emac" 2>/dev/null); [ -n "$emac_cpu_owned" ] || emac_cpu_owned=0
  emac_no_desc=$(sed -n 's/^dma_no_rx_desc_samples=//p' "$emac" 2>/dev/null); [ -n "$emac_no_desc" ] || emac_no_desc=0
  emac_rx_stopped=$(sed -n 's/^dma_rx_stopped_samples=//p' "$emac" 2>/dev/null); [ -n "$emac_rx_stopped" ] || emac_rx_stopped=0
  emac_rx_missed=$(sed -n 's/^dma_rx_missed_samples=//p' "$emac" 2>/dev/null); [ -n "$emac_rx_missed" ] || emac_rx_missed=0
  emac_restarts=$(sed -n 's/^rx_restart_total=//p' "$emac" 2>/dev/null); [ -n "$emac_restarts" ] || emac_restarts=0
  emac_restart_no_desc=$(sed -n 's/^rx_restart_reason_no_desc=//p' "$emac" 2>/dev/null); [ -n "$emac_restart_no_desc" ] || emac_restart_no_desc=0
  emac_restart_stopped=$(sed -n 's/^rx_restart_reason_stopped=//p' "$emac" 2>/dev/null); [ -n "$emac_restart_stopped" ] || emac_restart_stopped=0
  emac_restart_missed=$(sed -n 's/^rx_restart_reason_missed=//p' "$emac" 2>/dev/null); [ -n "$emac_restart_missed" ] || emac_restart_missed=0
  emac_restart_stagnant=$(sed -n 's/^rx_restart_reason_stagnant=//p' "$emac" 2>/dev/null); [ -n "$emac_restart_stagnant" ] || emac_restart_stagnant=0
"""
    return rf'''set +e
i=0
while [ "$i" -le {samples} ]; do
  uptime=$(cut -d. -f1 /proc/uptime 2>/dev/null)
  control=0
  [ -e /var/run/hostapd/wifi0 ] && [ -s /run/openmitrastar/radio5g/hostapd.pid ] && \
    kill -0 "$(cat /run/openmitrastar/radio5g/hostapd.pid)" 2>/dev/null && control=1
{association_sample.rstrip()}
{network_sample.rstrip()}
{datapath_sample.rstrip()}
  irq8=$(awk '$1 == "8:" {{ print $2 }}' /proc/interrupts); [ -n "$irq8" ] || irq8=0
  irq20=$(awk '$1 == "20:" {{ print $2 }}' /proc/interrupts); [ -n "$irq20" ] || irq20=0
  set -- $(head -n 1 /proc/stat)
  cpu_user=$2; cpu_nice=$3; cpu_system=$4; cpu_idle=$5; cpu_iowait=$6; cpu_irq=$7; cpu_softirq=$8
  mem_available=$(awk '/^MemAvailable:/ {{ print $2 }}' /proc/meminfo); [ -n "$mem_available" ] || mem_available=0
{radio_sample.rstrip()}
  [ -e /sys/class/net/br0/brif/eth0 ] && br_eth=1 || br_eth=0
  [ -e /sys/class/net/br0/brif/wlan0 ] && br_2g=1 || br_2g=0
  [ -e /sys/class/net/br0/brif/wifi0 ] && br_5g=1 || br_5g=0
  radio2g=0
  for pidfile in /run/openmitrastar/radio2g/hostapd-open.pid /run/openmitrastar/radio2g/hostapd.pid; do
    [ -s "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null && radio2g=1 && break
  done
  echo "OMSTREAM seq=$i uptime=$uptime control=$control assoc=$assoc wifi_rx=$wifi_rx wifi_tx=$wifi_tx eth_rx=$eth_rx eth_tx=$eth_tx br_rx=$br_rx br_tx=$br_tx tqe_rx=$tqe_rx tqe_tx=$tqe_tx irq8=$irq8 irq20=$irq20 carrier=$carrier rf=$rf br_eth=$br_eth br_2g=$br_2g br_5g=$br_5g radio2g=$radio2g mem_available_kb=$mem_available cpu_user=$cpu_user cpu_nice=$cpu_nice cpu_system=$cpu_system cpu_idle=$cpu_idle cpu_iowait=$cpu_iowait cpu_irq=$cpu_irq cpu_softirq=$cpu_softirq emac_irq_count=$emac_irq_count emac_napi_polls=$emac_napi_polls emac_napi_work=$emac_napi_work emac_napi_budget=$emac_napi_budget emac_rx_owned=$emac_rx_owned emac_cpu_owned=$emac_cpu_owned emac_no_desc=$emac_no_desc emac_rx_stopped=$emac_rx_stopped emac_rx_missed=$emac_rx_missed emac_restarts=$emac_restarts emac_restart_no_desc=$emac_restart_no_desc emac_restart_stopped=$emac_restart_stopped emac_restart_missed=$emac_restart_missed emac_restart_stagnant=$emac_restart_stagnant fatal=0"
  i=$((i + 1))
  [ "$i" -gt {samples} ] || sleep {interval}
done
'''


def parse_line(line: str) -> dict[str, int] | None:
    line = line.strip()
    if not line.startswith("OMSTREAM "):
        return None
    parsed: dict[str, int] = {}
    for item in line.split()[1:]:
        if "=" not in item:
            return None
        key, value = item.split("=", 1)
        try:
            parsed[key] = int(value)
        except ValueError:
            return None
    if not REQUIRED_FIELDS.issubset(parsed):
        return None
    return parsed


def tcp_open(host: str, port: int = 22, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def fatal_count(ssh: Path, key: Path, host: str) -> int | None:
    command = (
        "dmesg | grep -Eic 'MuC:.*exception|MuC exception|MuC has halted|"
        "forcing reboot|Kernel panic|Oops|BUG:|Unable to handle|EV_TLB|EV_ProtV|"
        "Misaligned Access|Misaligned r/w|Invalid Read|Invalid Write' || true"
    )
    try:
        result = subprocess.run(
            [
                str(ssh), "-i", str(key),
                "-o", "IdentitiesOnly=yes",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=5",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=NUL",
                "-o", "HostKeyAlgorithms=+ssh-rsa",
                "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
                "-o", "LogLevel=ERROR",
                f"root@{host}", command,
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=15,
            check=False,
        )
        return int(result.stdout.strip()) if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--seconds", type=int, default=180)
    parser.add_argument("--interval", type=int, default=1)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-client-traffic", action="store_true")
    parser.add_argument("--isolated-l3", action="store_true")
    parser.add_argument(
        "--hostapd-log",
        default="/run/openmitrastar/radio5g/hostapd.log",
    )
    parser.add_argument("--lightweight", action="store_true")
    parser.add_argument("--buffered", action="store_true")
    args = parser.parse_args()
    if not 10 <= args.seconds <= 900:
        raise SystemExit("--seconds must be 10..900")
    if not 1 <= args.interval <= 10:
        raise SystemExit("--interval must be 1..10")
    if not re.fullmatch(r"/run/openmitrastar/[A-Za-z0-9_./-]+", args.hostapd_log):
        raise SystemExit("--hostapd-log must be a safe /run/openmitrastar path")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    samples: list[dict[str, int]] = []
    error = ""
    started = time.monotonic()
    ssh = Path(os.environ.get("WINDIR", r"C:\Windows")) / "System32/OpenSSH/ssh.exe"
    key = Path.home() / ".ssh/id_ed25519"
    process: subprocess.Popen[str] | None = None
    with args.output.open("w", encoding="utf-8", buffering=1) as stream:
        try:
            ssh_args = [
                str(ssh), "-i", str(key),
                "-o", "IdentitiesOnly=yes",
                "-o", "BatchMode=yes",
                "-o", "ConnectTimeout=8",
                "-o", "StrictHostKeyChecking=no",
                "-o", "UserKnownHostsFile=NUL",
                "-o", "HostKeyAlgorithms=+ssh-rsa",
                "-o", "PubkeyAcceptedAlgorithms=+ssh-rsa",
                "-o", "LogLevel=ERROR",
                f"root@{args.host}", "sh", "-s",
            ]
            command_bytes = remote_command(
                args.seconds, args.interval, args.hostapd_log, args.lightweight
            ).encode("ascii")
            if args.buffered:
                completed = subprocess.run(
                    ssh_args,
                    cwd=ROOT,
                    input=command_bytes,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    timeout=args.seconds + 180,
                    check=False,
                )
                decoded = completed.stdout.decode("utf-8", "replace")
                stream.write(decoded)
                for line in decoded.splitlines():
                    parsed = parse_line(line)
                    if parsed:
                        samples.append(parsed)
                if completed.returncode:
                    error = completed.stderr.decode("utf-8", "replace")[:512] or f"ssh-exit-{completed.returncode}"
            else:
                process = subprocess.Popen(
                    ssh_args,
                    cwd=ROOT,
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=False,
                    bufsize=0,
                )
                assert process.stdin and process.stdout and process.stderr
                process.stdin.write(command_bytes)
                process.stdin.close()
                local_deadline = started + args.seconds + 150
                last_sample_at = time.monotonic()
                stdout_queue: queue.Queue[bytes | None] = queue.Queue()

                def read_stdout() -> None:
                    assert process and process.stdout
                    for raw_line in iter(process.stdout.readline, b""):
                        stdout_queue.put(raw_line)
                    stdout_queue.put(None)

                reader = threading.Thread(target=read_stdout, daemon=True)
                reader.start()
                while True:
                    now = time.monotonic()
                    if now >= local_deadline:
                        error = "local-deadline-exceeded"
                        break
                    if now - last_sample_at > max(90, args.interval * 30):
                        error = "remote-sample-heartbeat-timeout"
                        break
                    try:
                        raw = stdout_queue.get(timeout=0.5)
                    except queue.Empty:
                        if process.poll() is not None:
                            break
                        continue
                    if raw is None:
                        break
                    if raw:
                        line = raw.decode("utf-8", "replace")
                        stream.write(line)
                        parsed = parse_line(line)
                        if parsed:
                            samples.append(parsed)
                            last_sample_at = time.monotonic()
                            print(line.rstrip("\r\n"), flush=True)
                        continue
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                err = process.stderr.read().decode("utf-8", "replace").strip()
                if err:
                    error = err[:512]
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"[:512]
        finally:
            if process is not None and process.poll() is None:
                process.kill()

    first = samples[0] if samples else {}
    last = samples[-1] if samples else {}
    expected = args.seconds // args.interval + 1
    tcp22_after = tcp_open(args.host)
    post_fatal = fatal_count(ssh, key, args.host) if tcp22_after else None
    health_fields = ("control", "carrier", "rf", "br_eth", "br_2g", "radio2g")
    expected_br5 = 0 if args.isolated_l3 else 1
    health_failure = any(
        row.get("fatal", 0) != 0 or
        row.get("br_5g", -1) != expected_br5 or
        any(row.get(key, 0) != 1 for key in health_fields)
        for row in samples
    ) or (post_fatal not in (None, 0))
    result = {
        "schema": "openmitrastar.q3-client-single-session/v1",
        "host": args.host,
        "duration_requested_seconds": args.seconds,
        "duration_observed_seconds": round(time.monotonic() - started, 3),
        "samples_expected": expected,
        "samples_observed": len(samples),
        "complete": len(samples) == expected and not error,
        "connection_error": error or None,
        "management_lost": not tcp22_after,
        "tcp22_after": tcp22_after,
        "post_fatal_count": post_fatal,
        "health_failure": health_failure,
        "isolated_l3": args.isolated_l3,
        "br_5g_expected": expected_br5,
        "association_observed": any(row["assoc"] > 0 for row in samples),
        "wifi_rx_delta": last.get("wifi_rx", 0) - first.get("wifi_rx", 0),
        "wifi_tx_delta": last.get("wifi_tx", 0) - first.get("wifi_tx", 0),
        "eth_rx_delta": last.get("eth_rx", 0) - first.get("eth_rx", 0),
        "eth_tx_delta": last.get("eth_tx", 0) - first.get("eth_tx", 0),
        "irq8_delta": last.get("irq8", 0) - first.get("irq8", 0),
        "irq20_delta": last.get("irq20", 0) - first.get("irq20", 0),
        "br_rx_delta": last.get("br_rx", 0) - first.get("br_rx", 0),
        "br_tx_delta": last.get("br_tx", 0) - first.get("br_tx", 0),
        "tqe_rx_delta": last.get("tqe_rx", 0) - first.get("tqe_rx", 0),
        "tqe_tx_delta": last.get("tqe_tx", 0) - first.get("tqe_tx", 0),
        "emac_delta": {
            key: last.get(key, 0) - first.get(key, 0)
            for key in (
                "emac_irq_count", "emac_napi_polls", "emac_napi_work",
                "emac_napi_budget", "emac_rx_owned", "emac_cpu_owned",
                "emac_no_desc", "emac_rx_stopped", "emac_rx_missed",
                "emac_restarts", "emac_restart_no_desc",
                "emac_restart_stopped", "emac_restart_missed",
                "emac_restart_stagnant",
            )
        },
        "memory_available_kb": {
            "first": first.get("mem_available_kb"),
            "last": last.get("mem_available_kb"),
            "minimum": min((row.get("mem_available_kb", 0) for row in samples), default=0),
        },
        "last_sample": last or None,
        "raw_log": str(args.output),
        "flash": False,
        "mutations": False,
        "lightweight": args.lightweight,
        "buffered": args.buffered,
        "hostapd_log": args.hostapd_log,
    }
    summary = args.output.with_suffix(args.output.suffix + ".json")
    summary.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if not result["complete"] or health_failure:
        return 1
    if args.require_client_traffic and not (
        result["association_observed"] and result["wifi_rx_delta"] > 0 and
        result["wifi_tx_delta"] > 0 and result["irq8_delta"] > 0 and
        result["irq20_delta"] > 0
    ):
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
