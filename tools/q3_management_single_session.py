#!/usr/bin/env python3
"""Observe Q3 management health over one persistent SSH connection.

The remote command is read-only.  Unlike q3_client_gate_readonly.py, this tool
does not create a new SSH transport for every sample, so the measurement cannot
hide a Dropbear/process leak behind dozens of reconnects.
"""
from __future__ import annotations

import argparse
import ipaddress
import io
import json
from pathlib import Path
import re
import subprocess
import sys
import threading
import time


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
import paramiko  # noqa: E402


BEGIN = "__OMMGMT_SAMPLE_BEGIN__"
END = "__OMMGMT_SAMPLE_END__"
NUMBER_KEYS = {
    "UPTIME", "MEM_FREE_KB", "MEM_AVAILABLE_KB", "SLAB_KB", "SRECLAIMABLE_KB",
    "SUNRECLAIM_KB", "PROC_COUNT", "ZOMBIE_COUNT", "DROPBEAR_COUNT", "FILE_ALLOC",
    "SOCKETS_USED", "ETH_RX_PACKETS", "ETH_TX_PACKETS", "ETH_RX_BYTES", "ETH_TX_BYTES",
    "ETH_RX_DROPPED", "ETH_TX_DROPPED", "ETH_RX_ERRORS", "ETH_TX_ERRORS", "IRQ20",
    "IRQ8", "IRQ10", "BR_ETH_MEMBER", "BR_WIFI_MEMBER", "MUC_FATAL_COUNT",
}


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


def remote_command(samples: int, interval: int, peer_ip: str) -> str:
    return rf'''set +e
i=0
while [ "$i" -lt {samples} ]; do
  echo "{BEGIN} $i"
  echo UPTIME=$(cut -d. -f1 /proc/uptime 2>/dev/null)
  echo MEM_FREE_KB=$(awk '/^MemFree:/ {{print $2}}' /proc/meminfo)
  echo MEM_AVAILABLE_KB=$(awk '/^MemAvailable:/ {{print $2}}' /proc/meminfo)
  echo SLAB_KB=$(awk '/^Slab:/ {{print $2}}' /proc/meminfo)
  echo SRECLAIMABLE_KB=$(awk '/^SReclaimable:/ {{print $2}}' /proc/meminfo)
  echo SUNRECLAIM_KB=$(awk '/^SUnreclaim:/ {{print $2}}' /proc/meminfo)
  echo PROC_COUNT=$(ps | awk 'NR > 1 {{n++}} END {{print n + 0}}')
  echo ZOMBIE_COUNT=$(ps | awk 'NR > 1 && $4 ~ /^Z/ {{n++}} END {{print n + 0}}')
  echo DROPBEAR_COUNT=$(ps | awk 'NR > 1 && $5 ~ /dropbearmulti/ {{n++}} END {{print n + 0}}')
  echo FILE_ALLOC=$(awk '{{print $1}}' /proc/sys/fs/file-nr)
  echo SOCKETS_USED=$(awk '$1 == "sockets:" {{print $3}}' /proc/net/sockstat)
  echo ETH_CARRIER=$(cat /sys/class/net/eth0/carrier 2>/dev/null)
  echo ETH_OPERSTATE=$(cat /sys/class/net/eth0/operstate 2>/dev/null)
  echo ETH_RX_PACKETS=$(cat /sys/class/net/eth0/statistics/rx_packets 2>/dev/null)
  echo ETH_TX_PACKETS=$(cat /sys/class/net/eth0/statistics/tx_packets 2>/dev/null)
  echo ETH_RX_BYTES=$(cat /sys/class/net/eth0/statistics/rx_bytes 2>/dev/null)
  echo ETH_TX_BYTES=$(cat /sys/class/net/eth0/statistics/tx_bytes 2>/dev/null)
  echo ETH_RX_DROPPED=$(cat /sys/class/net/eth0/statistics/rx_dropped 2>/dev/null)
  echo ETH_TX_DROPPED=$(cat /sys/class/net/eth0/statistics/tx_dropped 2>/dev/null)
  echo ETH_RX_ERRORS=$(cat /sys/class/net/eth0/statistics/rx_errors 2>/dev/null)
  echo ETH_TX_ERRORS=$(cat /sys/class/net/eth0/statistics/tx_errors 2>/dev/null)
  echo IRQ20=$(grep -E '^[[:space:]]*20:' /proc/interrupts | awk '{{print $2}}')
  echo IRQ8=$(grep -E '^[[:space:]]*8:' /proc/interrupts | awk '{{print $2}}')
  echo IRQ10=$(grep -E '^[[:space:]]*10:' /proc/interrupts | awk '{{print $2}}')
  [ -e /sys/class/net/br0/brif/eth0 ] && echo BR_ETH_MEMBER=1 || echo BR_ETH_MEMBER=0
  [ -e /sys/class/net/br0/brif/wifi0 ] && echo BR_WIFI_MEMBER=1 || echo BR_WIFI_MEMBER=0
  echo BR_ETH_STATE=$(cat /sys/class/net/br0/brif/eth0/state 2>/dev/null)
  arp_line=$(grep '^{re.escape(peer_ip)}[[:space:]]' /proc/net/arp 2>/dev/null | head -n1)
  [ -n "$arp_line" ] && echo ARP_PEER="$arp_line" || echo ARP_PEER=absent
  echo MUC_FATAL_COUNT=$(dmesg | grep -Ec 'MuC exception|MuC has halted|forcing reboot|EV_TLB|EV_ProtV')
  echo EMAC_TICK_LINE=$(dmesg | grep 'OMEMAC poll tick=' | tail -n1)
  echo EMAC_PROGRESS_LINE=$(dmesg | grep 'OMEMAC poll progress' | tail -n1)
  echo "{END} $i"
  i=$((i + 1))
  [ "$i" -ge {samples} ] || sleep {interval}
done
'''


def parse_remote(text: str) -> list[dict[str, object]]:
    samples: list[dict[str, object]] = []
    current: dict[str, object] | None = None
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith(BEGIN + " "):
            current = {"index": int(line.rsplit(" ", 1)[1])}
        elif line.startswith(END + " "):
            if current is not None:
                samples.append(current)
            current = None
        elif current is not None and "=" in line:
            key, value = line.split("=", 1)
            if key in NUMBER_KEYS:
                match = re.match(r"-?\d+", value)
                current[key.lower()] = int(match.group(0)) if match else 0
            else:
                current[key.lower()] = value
    return samples


def local_probe(host: str) -> dict[str, object]:
    ping = subprocess.run(
        ["ping", "-n", "1", "-w", "1000", host],
        text=True,
        capture_output=True,
        timeout=4,
    )
    arp = subprocess.run(["arp", "-a"], text=True, capture_output=True, timeout=4)
    return {
        "elapsed_seconds": None,
        "ping": ping.returncode == 0,
        "arp_present": host in (arp.stdout + arp.stderr),
    }


def classify(remote: list[dict[str, object]], local: list[dict[str, object]], error: str | None) -> str:
    if not remote:
        return "NO_REMOTE_SAMPLE"
    first, last = remote[0], remote[-1]
    if int(last.get("muc_fatal_count", 0)) > int(first.get("muc_fatal_count", 0)) or int(last.get("irq10", 0)) > 0:
        return "MUC_FATAL"
    if int(last.get("br_eth_member", 0)) == 0 or str(last.get("eth_carrier", "")) != "1":
        return "ETH_LINK_OR_BRIDGE_LOST"
    if len(remote) >= 3:
        tail = remote[-3:]
        if len({int(x.get("eth_rx_packets", 0)) for x in tail}) == 1 and len({int(x.get("irq20", 0)) for x in tail}) == 1:
            return "EMAC_RX_AND_IRQ20_STALLED"
    proc_growth = int(last.get("proc_count", 0)) - int(first.get("proc_count", 0))
    dropbear_growth = int(last.get("dropbear_count", 0)) - int(first.get("dropbear_count", 0))
    zombie_growth = int(last.get("zombie_count", 0)) - int(first.get("zombie_count", 0))
    slab_growth = int(last.get("sunreclaim_kb", 0)) - int(first.get("sunreclaim_kb", 0))
    if dropbear_growth > 2 or zombie_growth > 2 or proc_growth > 8 or slab_growth > 4096:
        return "PROCESS_OR_KERNEL_RESOURCE_GROWTH"
    if error and local and not any(bool(x["ping"]) for x in local[-3:]):
        return "MANAGEMENT_PATH_LOST_NEEDS_UART_CORRELATION"
    if local and not any(bool(x["ping"]) for x in local[-3:]):
        return "ICMP_OR_HOST_PATH_LOST_WHILE_SSH_SESSION_SURVIVED"
    return "SINGLE_SESSION_MANAGEMENT_STABLE"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--peer-ip", default="192.168.1.43")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("--interval-seconds", type=int, default=5)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if not 10 <= args.seconds <= 3600:
        raise SystemExit("--seconds must be 10..3600")
    if not 1 <= args.interval_seconds <= 60:
        raise SystemExit("--interval-seconds must be 1..60")
    ipaddress.ip_address(args.host)
    ipaddress.ip_address(args.peer_ip)
    samples = (args.seconds + args.interval_seconds - 1) // args.interval_seconds + 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    raw_output = args.output.with_suffix(args.output.suffix + ".remote.log")
    raw_output.write_bytes(b"")

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    local_samples: list[dict[str, object]] = []
    stop = threading.Event()
    started = time.monotonic()

    def local_loop() -> None:
        while not stop.is_set():
            sample = local_probe(args.host)
            sample["elapsed_seconds"] = round(time.monotonic() - started, 3)
            local_samples.append(sample)
            stop.wait(args.interval_seconds)

    raw = bytearray()
    error: str | None = None

    def checkpoint(state: str) -> None:
        partial = parse_remote(raw.decode("utf-8", "replace"))
        payload = {
            "schema": "openmitrastar.q3-management-single-session-checkpoint/v1",
            "state": state,
            "host": args.host,
            "ssh_transport_connections": 1,
            "remote_samples_expected": samples,
            "remote_samples_observed": len(partial),
            "remote_samples": partial,
            "local_samples": list(local_samples),
            "flash": False,
            "remote_mutations": False,
        }
        temporary = args.output.with_suffix(args.output.suffix + ".tmp")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.replace(args.output)
    try:
        client.connect(
            args.host, username="root", pkey=load_private_key(), look_for_keys=False,
            allow_agent=False, timeout=5, banner_timeout=8, auth_timeout=8,
        )
        transport = client.get_transport()
        if transport is None:
            raise RuntimeError("SSH transport unavailable")
        channel = transport.open_session(timeout=8)
        channel.exec_command(remote_command(samples, args.interval_seconds, args.peer_ip))
        thread = threading.Thread(target=local_loop, daemon=True)
        thread.start()
        deadline = started + args.seconds + args.interval_seconds + 30
        while time.monotonic() < deadline:
            if channel.recv_ready():
                block = channel.recv(65536)
                raw.extend(block)
                with raw_output.open("ab") as stream:
                    stream.write(block)
                checkpoint("running")
            if channel.recv_stderr_ready():
                block = channel.recv_stderr(65536)
                raw.extend(block)
                with raw_output.open("ab") as stream:
                    stream.write(block)
                checkpoint("running")
            if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                break
            time.sleep(0.05)
        else:
            error = "persistent-session-timeout"
            channel.close()
        stop.set()
        thread.join(timeout=5)
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"[:512]
        stop.set()
    finally:
        client.close()

    remote_samples = parse_remote(raw.decode("utf-8", "replace"))
    result = {
        "schema": "openmitrastar.q3-management-single-session/v1",
        "host": args.host,
        "seconds_requested": args.seconds,
        "interval_seconds": args.interval_seconds,
        "ssh_transport_connections": 1,
        "remote_samples_expected": samples,
        "remote_samples_observed": len(remote_samples),
        "classification": classify(remote_samples, local_samples, error),
        "connection_error": error,
        "remote_samples": remote_samples,
        "local_samples": local_samples,
        "flash": False,
        "remote_mutations": False,
    }
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not error else 1


if __name__ == "__main__":
    raise SystemExit(main())
