#!/usr/bin/env python3
"""Collect one read-only W2 2.4 GHz client-gate evidence snapshot.

This tool does not change router state. It only reads hostapd, station, bridge,
netdev, interrupt, and dmesg state through the existing RAM SSH channel and
emits JSON compatible with tools/evaluate_w2_2g_client_gate.py.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "work" / "pydeps"))

import paramiko  # noqa: E402
from ramssh_exec import load_private_key  # noqa: E402


CTRL = "/run/openmitrastar/radio2g/ctrl"
IMAGE_PATH = "work/tftp/omvl/linux510-w2-2g-parity-tx3-v1-RAM-TEST-NO-FLASH.bin"
IMAGE_SHA256 = "38930e350c2da27c00d5a3dff693dfab967c8cff1255904ebfc4897314bd203e"
IMAGE_BYTES = 4_330_620
IMAGE_VARIANT = "TX3"


def remote_command(irq_window: int) -> str:
    return f"""set +e
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
echo OM_IW_STATION_BEGIN
iw dev wlan0 station dump 2>/dev/null
echo OM_IW_STATION_END
echo OM_BRIF_BEGIN
ls /sys/class/net/br0/brif 2>/dev/null
echo OM_BRIF_END
echo OM_NETDEV_BEGIN
cat /proc/net/dev
echo OM_NETDEV_END
echo OM_INTERRUPTS_BEFORE_BEGIN
cat /proc/interrupts | grep -E 'rtl|eth0| 20:| 28:' 2>/dev/null
echo OM_INTERRUPTS_BEFORE_END
sleep {irq_window}
echo OM_INTERRUPTS_AFTER_BEGIN
cat /proc/interrupts | grep -E 'rtl|eth0| 20:| 28:' 2>/dev/null
echo OM_INTERRUPTS_AFTER_END
echo OM_DMESG_SAFETY_BEGIN
dmesg | grep -i oops 2>/dev/null
dmesg | grep -i 'kernel panic' 2>/dev/null
dmesg | grep -i 'kernel bug' 2>/dev/null
echo OM_DMESG_SAFETY_END
echo OM_TXBD_BEGIN
dmesg | grep -i txbd 2>/dev/null
echo OM_TXBD_END
"""


def run_remote(host: str, timeout: int, irq_window: int) -> str:
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
        _, stdout, stderr = client.exec_command(remote_command(irq_window), timeout=timeout)
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
    values: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def parse_netdev(text: str) -> dict[str, dict[str, int]]:
    out: dict[str, dict[str, int]] = {}
    for line in text.splitlines():
        if ":" not in line or line.lstrip().startswith("Inter-") or line.lstrip().startswith("face"):
            continue
        iface, rest = line.split(":", 1)
        parts = rest.split()
        if len(parts) < 16:
            continue
        out[iface.strip()] = {
            "rx_bytes": int(parts[0]),
            "rx_packets": int(parts[1]),
            "rx_errors": int(parts[2]),
            "rx_dropped": int(parts[3]),
            "tx_bytes": int(parts[8]),
            "tx_packets": int(parts[9]),
            "tx_errors": int(parts[10]),
            "tx_dropped": int(parts[11]),
        }
    return out


def parse_interrupts(text: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for line in text.splitlines():
        match = re.match(r"\s*(?P<irq>\d+):\s+(?P<count>\d+)\b.*?(?P<name>eth0|rtl_pci)\s*$", line)
        if match:
            out[match.group("name")] = int(match.group("count"))
            out[f"irq{match.group('irq')}"] = int(match.group("count"))
    return out


def has_authorized_station(all_sta: str) -> bool:
    return bool(
        re.search(r"^[0-9a-f]{2}(?::[0-9a-f]{2}){5}$", all_sta, re.IGNORECASE | re.MULTILINE)
        and re.search(r"AUTHORIZED", all_sta, re.IGNORECASE)
    )


def txbd_layout(txbd: str) -> dict[str, str]:
    layout: dict[str, str] = {}
    for q, stride, compact in re.findall(r"q=(\d+)\s+stride=(\d+)\s+compact=(\d+)", txbd):
        role = "data" if q in {"0", "1", "2", "3"} else "preserved"
        if q == "4":
            role = "beacon"
        layout[f"q{q}"] = f"stride{stride} {role} compact={compact}"
    return layout


def safety_findings(dmesg_safety: str) -> list[str]:
    findings: list[str] = []
    for line in dmesg_safety.splitlines():
        text = line.strip()
        if not text:
            continue
        if "Kernel command line:" in text:
            continue
        findings.append(text)
    return findings


def build_evidence(
    raw: str,
    *,
    duration_seconds: int,
    download_mbps: float,
    upload_mbps: float,
    be_queue_max: int,
    dhcp_lease: bool,
    dns_ok: bool,
    internet_https_ok: bool,
    image_path: str = IMAGE_PATH,
    image_sha256: str = IMAGE_SHA256,
    image_bytes: int = IMAGE_BYTES,
    image_variant: str = IMAGE_VARIANT,
) -> dict:
    status = parse_kv(section(raw, "HOSTAPD_STATUS"))
    all_sta = section(raw, "HOSTAPD_ALL_STA")
    iw_station = section(raw, "IW_STATION")
    brif = sorted(line.strip() for line in section(raw, "BRIF").splitlines() if line.strip())
    netdev = parse_netdev(section(raw, "NETDEV"))
    irq_before = parse_interrupts(section(raw, "INTERRUPTS_BEFORE"))
    irq_after = parse_interrupts(section(raw, "INTERRUPTS_AFTER"))
    dmesg_safety = section(raw, "DMESG_SAFETY")
    safety = safety_findings(dmesg_safety)
    txbd = section(raw, "TXBD")

    num_sta = int(status.get("num_sta[0]", "0") or "0")
    associated = num_sta > 0 or bool(iw_station.strip())
    authorized = has_authorized_station(all_sta)
    if associated and not all_sta.strip() and iw_station.strip():
        authorized = False

    wlan = netdev.get("wlan0", {})
    eth = netdev.get("eth0", {})
    br0 = netdev.get("br0", {})
    netdev_error_total = sum(
        iface.get(key, 0)
        for iface in (wlan, eth, br0)
        for key in ("rx_errors", "tx_errors")
    )

    irq28_progress = irq_after.get("irq28", 0) > irq_before.get("irq28", 0)
    irq20_progress = irq_after.get("irq20", 0) > irq_before.get("irq20", 0)
    bridge_eth0_wlan0 = "eth0" in brif and "wlan0" in brif
    hostapd_stable = section(raw, "RADIO_STATE").strip() == "ready" and status.get("state") == "ENABLED"

    return {
        "schema": "openmitrastar.w2-2g-client-evidence/v1",
        "classification": f"RAM-ONLY-{image_variant}-LIVE-CLIENT-GATE-NO-FLASH",
        "image": {
            "path": image_path,
            "sha256": image_sha256,
            "bytes": image_bytes,
        },
        "associated": associated,
        "authorized": authorized,
        "dhcp_lease": dhcp_lease,
        "dns_ok": dns_ok,
        "internet_https_ok": internet_https_ok,
        "bridge_eth0_wlan0": bridge_eth0_wlan0,
        "irq28_progress": irq28_progress,
        "hostapd_stable": hostapd_stable,
        "no_kernel_oops": not safety,
        "duration_seconds": duration_seconds,
        "download_mbps": download_mbps,
        "upload_mbps": upload_mbps,
        "be_queue_max": be_queue_max,
        "disconnects": 0,
        "netdev_errors_delta": netdev_error_total,
        "observed": {
            "boot_state": section(raw, "BOOT_STATE").strip(),
            "radio_state": section(raw, "RADIO_STATE").strip(),
            "hostapd_state": status.get("state"),
            "ssid": status.get("ssid[0]"),
            "channel": int(status.get("channel", "0") or "0"),
            "num_sta": num_sta,
            "bridge_members": brif,
            "irq20_progress": irq20_progress,
            "irq28_before": irq_before.get("irq28", 0),
            "irq28_after": irq_after.get("irq28", 0),
            "irq20_before": irq_before.get("irq20", 0),
            "irq20_after": irq_after.get("irq20", 0),
            "wlan0_rx_packets": wlan.get("rx_packets", 0),
            "wlan0_tx_packets": wlan.get("tx_packets", 0),
            "wlan0_rx_errors": wlan.get("rx_errors", 0),
            "wlan0_tx_errors": wlan.get("tx_errors", 0),
            "eth0_rx_packets": eth.get("rx_packets", 0),
            "eth0_tx_packets": eth.get("tx_packets", 0),
            "br0_rx_packets": br0.get("rx_packets", 0),
            "br0_tx_packets": br0.get("tx_packets", 0),
            "txbd_layout": txbd_layout(txbd),
            "safety_findings": safety,
        },
        "next_gate": (
            "authorized client present; capture DHCP/DNS/HTTPS and one measured Speedtest"
            if associated and authorized
            else "physical client association on OpenMitraStar-2G-DIAG; do not run Speedtest until associated and authorized"
        ),
        "mutations": False,
        "flash": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--input-raw", type=Path, help="Parse a previously captured raw snapshot.")
    source.add_argument("--host", default="192.168.1.90", help="RAM SSH host to query.")
    parser.add_argument("--timeout", type=int, default=30)
    parser.add_argument("--irq-window", type=int, default=2)
    parser.add_argument("--duration-seconds", type=int, default=0)
    parser.add_argument("--download-mbps", type=float, default=0.0)
    parser.add_argument("--upload-mbps", type=float, default=0.0)
    parser.add_argument("--be-queue-max", type=int, default=512)
    parser.add_argument("--dhcp-lease", action="store_true")
    parser.add_argument("--dns-ok", action="store_true")
    parser.add_argument("--internet-https-ok", action="store_true")
    parser.add_argument("--image-path", default=IMAGE_PATH)
    parser.add_argument("--image-sha256", default=IMAGE_SHA256)
    parser.add_argument("--image-bytes", type=int, default=IMAGE_BYTES)
    parser.add_argument("--image-variant", default=IMAGE_VARIANT)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path)
    parser.add_argument("--evaluate", action="store_true", help="Run evaluate_w2_2g_client_gate.py after writing evidence.")
    args = parser.parse_args()

    if args.input_raw:
        raw = args.input_raw.read_text(encoding="utf-8", errors="replace")
    else:
        raw = run_remote(args.host, args.timeout, args.irq_window)
    if args.raw_output:
        args.raw_output.parent.mkdir(parents=True, exist_ok=True)
        args.raw_output.write_text(raw, encoding="utf-8", newline="\n")

    evidence = build_evidence(
        raw,
        duration_seconds=args.duration_seconds,
        download_mbps=args.download_mbps,
        upload_mbps=args.upload_mbps,
        be_queue_max=args.be_queue_max,
        dhcp_lease=args.dhcp_lease,
        dns_ok=args.dns_ok,
        internet_https_ok=args.internet_https_ok,
        image_path=args.image_path,
        image_sha256=args.image_sha256,
        image_bytes=args.image_bytes,
        image_variant=args.image_variant,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rendered = json.dumps(evidence, indent=2, sort_keys=True) + "\n"
    args.output.write_text(rendered, encoding="utf-8", newline="\n")
    print(rendered, end="")

    if args.evaluate:
        result_path = args.output.with_suffix(args.output.suffix + ".result.json")
        proc = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tools" / "evaluate_w2_2g_client_gate.py"),
                str(args.output),
                "--output",
                str(result_path),
            ],
            text=True,
            capture_output=True,
            check=False,
        )
        if proc.stdout:
            sys.stdout.write(proc.stdout)
        if proc.stderr:
            sys.stderr.write(proc.stderr)
        return proc.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
