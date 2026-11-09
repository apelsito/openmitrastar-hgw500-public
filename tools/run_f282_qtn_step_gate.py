#!/usr/bin/env python3
"""Run one F282 Quantenna same-value probe with UART and SSH evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import socket
import subprocess
import sys
import threading
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work/pydeps"))

import serial  # type: ignore  # vendored dependency


STEPS = (
    "rf-write-same",
    "interface-up-same",
    "mode-write-same",
    "ssid-write-same",
    "channel-write-same",
    "txpower-init-same",
    "doth-write-same",
    "tpc-write-same",
    "tpc-interval-same",
    "hostapd-restart-same",
    "post-rearm-same",
)
LOW_RISK = {"rf-write-same", "interface-up-same"}
REQUIRED_ACK = "OPENMITRASTAR_F282_QTN_STEP_PHYSICAL"
EXPECTED_VERSION = "lyoko-foundation-6.3.6-f282-qtn-hostapd-restart-fix-device"
DEFAULT_KNOWN_HOSTS = (
    Path.home()
    / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f282-device-bound/known_hosts.f282"
)
FATAL_PATTERN = r"Misaligned Access|kernel panic|Oops:|BUG:|QDRV.*fatal|MuC.*fatal|DMA.*fatal"


def tcp_open(host: str, port: int = 22, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def ssh_command(ssh_base: list[str], command: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ssh_base, command],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def snapshot(ssh_base: list[str]) -> tuple[dict[str, Any] | None, subprocess.CompletedProcess[str]]:
    command = f"""set +e
printf 'RADIO2='; /usr/sbin/om-radioctl status 2g
printf 'RADIO5='; /usr/sbin/om-radioctl status 5g
printf 'QTN_MODE='; /usr/sbin/om-qtnctl get mode
fatal_count=$(dmesg | grep -Eic '{FATAL_PATTERN}' || true)
printf 'FATAL_COUNT=%s\\n' \"$fatal_count\"
exit 0
"""
    proc = ssh_command(ssh_base, command)
    if proc.returncode != 0:
        return None, proc
    values: dict[str, Any] = {}
    for line in proc.stdout.splitlines():
        if line.startswith("RADIO2="):
            values["radio2"] = json.loads(line.removeprefix("RADIO2="))
        elif line.startswith("RADIO5="):
            values["radio5"] = json.loads(line.removeprefix("RADIO5="))
        elif line.startswith("QTN_MODE="):
            values["qtn_mode"] = line.removeprefix("QTN_MODE=").strip()
        elif line.startswith("FATAL_COUNT="):
            values["fatal_count"] = int(line.removeprefix("FATAL_COUNT="))
    required = {"radio2", "radio5", "qtn_mode", "fatal_count"}
    return (values if required <= values.keys() else None), proc


def stable_radio_view(value: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value.get(key)
        for key in (
            "id", "lifecycle", "state", "interface", "ssid", "channel",
            "bandwidth", "tx_power_dbm", "region", "security",
        )
    }


def state_preserved(before: dict[str, Any], after: dict[str, Any] | None) -> bool:
    return bool(
        after
        and stable_radio_view(before["radio2"]) == stable_radio_view(after["radio2"])
        and stable_radio_view(before["radio5"]) == stable_radio_view(after["radio5"])
        and before["qtn_mode"] == after["qtn_mode"]
        and before["fatal_count"] == after["fatal_count"]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--step", choices=STEPS, required=True)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--allow-management-loss", action="store_true")
    parser.add_argument("--physical-recovery-ready", action="store_true")
    parser.add_argument("--host", default="192.168.1.90")
    parser.add_argument("--port", default="COM3")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--known-hosts", type=Path, default=DEFAULT_KNOWN_HOSTS)
    parser.add_argument("--settle-seconds", type=int, default=20)
    parser.add_argument("--settle-interval-seconds", type=int, default=2)
    args = parser.parse_args()
    if not 2 <= args.settle_seconds <= 60:
        raise SystemExit("--settle-seconds must be 2..60")
    if not 1 <= args.settle_interval_seconds <= 10:
        raise SystemExit("--settle-interval-seconds must be 1..10")

    preview = {
        "schema": "openmitrastar.f282-qtn-step-gate-plan/v1",
        "mode": "execute" if args.execute else "dry-run",
        "step": args.step,
        "risk": "low" if args.step in LOW_RISK else "management-loss-possible",
        "router": args.host,
        "uart": args.port,
        "expected_version": EXPECTED_VERSION,
        "flash": False,
        "writes_mtd": False,
        "requires_physical_recovery": args.step not in LOW_RISK,
    }
    print(json.dumps(preview, indent=2))
    if not args.execute:
        return 0
    if args.ack != REQUIRED_ACK:
        raise SystemExit("exact --ack is required")
    if args.step not in LOW_RISK and not args.allow_management_loss:
        raise SystemExit("--allow-management-loss is required for this step")
    if args.step not in LOW_RISK and not args.physical_recovery_ready:
        raise SystemExit("--physical-recovery-ready is required for this step")
    if not tcp_open(args.host):
        raise SystemExit("router SSH is unavailable")
    if not args.known_hosts.is_file():
        raise SystemExit("pinned F282 known_hosts is unavailable")

    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    ssh_base = [
        ssh,
        "-i", str(Path.home() / ".ssh/id_ed25519"),
        "-o", "IdentitiesOnly=yes",
        "-o", "BatchMode=yes",
        "-o", "ConnectTimeout=8",
        "-o", "ServerAliveInterval=3",
        "-o", "ServerAliveCountMax=2",
        "-o", "StrictHostKeyChecking=yes",
        "-o", f"UserKnownHostsFile={args.known_hosts}",
        "-o", "LogLevel=ERROR",
        f"root@{args.host}",
    ]
    version = ssh_command(
        ssh_base,
        "sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release",
        timeout=15,
    )
    if version.returncode != 0 or version.stdout.strip() != EXPECTED_VERSION:
        raise SystemExit(f"expected F282 runtime, got {version.stdout.strip() or 'unavailable'}")

    before, before_proc = snapshot(ssh_base)
    if before is None:
        raise SystemExit(f"pre-step snapshot failed: {before_proc.stderr.strip() or 'invalid output'}")
    if before["radio2"].get("lifecycle") != "ap-ready" or before["radio5"].get("lifecycle") != "ap-ready":
        raise SystemExit("both radios must be ap-ready before the probe")
    if not str(before["qtn_mode"]).startswith("11ac"):
        raise SystemExit("live Quantenna mode is unavailable")

    out = (
        args.output_dir
        or ROOT / "outputs/postflash" / f"f282-qtn-step-{args.step}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    ).resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "before.json").write_text(json.dumps(before, indent=2) + "\n", encoding="ascii")

    stop = threading.Event()
    uart_chunks: list[bytes] = []
    uart = serial.Serial(args.port, 115200, timeout=0.1, write_timeout=2)

    def reader() -> None:
        while not stop.is_set():
            data = uart.read(4096)
            if data:
                uart_chunks.append(data)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    command = f"OM_QTN_STEP_ACK=OPENMITRASTAR_QTN_STEP_V1 /usr/sbin/om-qtn-step probe {args.step}"
    try:
        proc = ssh_command(ssh_base, command, timeout=25)
    except subprocess.TimeoutExpired as exc:
        proc = subprocess.CompletedProcess(exc.cmd, 124, exc.stdout or "", exc.stderr or "timeout")
    time.sleep(2)
    stop.set()
    thread.join(timeout=2)
    uart.close()

    uart_text = b"".join(uart_chunks).decode("utf-8", errors="replace")
    uart_text = re.sub(r"(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}", "[mac-redacted]", uart_text)
    (out / "uart.log").write_text(uart_text, encoding="utf-8")
    (out / "ssh.stdout.log").write_text(proc.stdout or "", encoding="utf-8")
    (out / "ssh.stderr.log").write_text(proc.stderr or "", encoding="utf-8")

    ssh_after = tcp_open(args.host)
    after = None
    after_proc = None
    after_samples: list[dict[str, Any]] = []
    settle_started = time.monotonic()
    if ssh_after:
        settle_deadline = settle_started + args.settle_seconds
        while True:
            candidate, candidate_proc = snapshot(ssh_base)
            after_proc = candidate_proc
            if candidate is not None:
                after = candidate
                after_samples.append({
                    "elapsed_seconds": round(time.monotonic() - settle_started, 3),
                    "state_preserved": state_preserved(before, candidate),
                    "snapshot": candidate,
                })
                if state_preserved(before, candidate):
                    break
            if time.monotonic() >= settle_deadline:
                break
            time.sleep(args.settle_interval_seconds)
        if after is not None:
            (out / "after.json").write_text(json.dumps(after, indent=2) + "\n", encoding="ascii")
    (out / "after-samples.json").write_text(json.dumps(after_samples, indent=2) + "\n", encoding="ascii")

    marker_text = (proc.stdout or "") + "\n" + uart_text
    preserved = state_preserved(before, after)
    transient_state_observed = any(not sample["state_preserved"] for sample in after_samples)
    passed = bool(
        proc.returncode == 0
        and f"OMQTNSTEP pass step={args.step}" in marker_text
        and ssh_after
        and preserved
    )
    result = {
        "schema": "openmitrastar.f282-qtn-step-gate/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "firmware": EXPECTED_VERSION,
        "step": args.step,
        "ssh_returncode": proc.returncode,
        "ssh_after": ssh_after,
        "after_snapshot_available": after is not None,
        "after_snapshot_error": "" if after_proc is None else after_proc.stderr.strip(),
        "begin_marker": f"OMQTNSTEP begin step={args.step}" in marker_text,
        "pass_marker": f"OMQTNSTEP pass step={args.step}" in marker_text,
        "fail_marker": f"OMQTNSTEP fail step={args.step}" in marker_text,
        "state_preserved": preserved,
        "transient_state_observed": transient_state_observed,
        "settle_samples": len(after_samples),
        "settle_elapsed_seconds": round(time.monotonic() - settle_started, 3),
        "fatal_count_before": before["fatal_count"],
        "fatal_count_after": None if after is None else after["fatal_count"],
        "qtn_mode_before": before["qtn_mode"],
        "qtn_mode_after": None if after is None else after["qtn_mode"],
        "status": "PASS" if passed else "FAIL",
        "flash": False,
        "mtd_writes": False,
        "automatic_retry": False,
        "automatic_recovery": False,
        "uart_log": str(out / "uart.log"),
    }
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
