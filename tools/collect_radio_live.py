#!/usr/bin/env python3
"""Collect read-only radio telemetry from the authorized legacy repeater."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "work" / "pydeps"))
from winpty import PtyProcess  # noqa: E402


def credentials() -> tuple[str, str]:
    for raw in (ROOT / "Accesos.txt").read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and ":" in line:
            user, password = line.split(":", 1)
            return user.strip(), password.strip()
    raise RuntimeError("No usable SSH credential found")


def read_until(proc: PtyProcess, marker: str, timeout: int = 30) -> str:
    deadline = time.monotonic() + timeout
    chunks: list[str] = []
    while time.monotonic() < deadline:
        try:
            chunk = proc.read(8192)
        except EOFError:
            break
        if chunk:
            chunks.append(chunk)
            joined = "".join(chunks)
            if marker.lower() in joined.lower():
                return joined
        else:
            time.sleep(0.05)
    raise TimeoutError(marker)


def run(proc: PtyProcess, command: str, marker: str) -> str:
    proc.write(command + f"; echo {marker}\r\n")
    output = read_until(proc, marker, 45)
    return output.replace("\r", "")


def main() -> int:
    user, password = credentials()
    ssh = os.path.join(os.environ["WINDIR"], "System32", "OpenSSH", "ssh.exe")
    args = [
        ssh, "-tt", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=NUL",
        "-o", "HostKeyAlgorithms=+ssh-rsa", "-o", "KexAlgorithms=+diffie-hellman-group1-sha1",
        "-o", "Ciphers=+aes128-cbc,3des-cbc", "-o", "MACs=+hmac-sha1,hmac-md5",
        f"{user}@192.168.1.90",
    ]
    proc = PtyProcess.spawn(args, cwd=str(ROOT))
    read_until(proc, "password:", 20)
    proc.write(password + "\r\n")
    read_until(proc, "# ", 20)
    proc.write("stty -echo\r\n")
    read_until(proc, "# ", 10)

    commands = [
        ("release", "cat /etc/openmitrastar-release; uptime; grep -E 'MemTotal|MemFree|Buffers|Cached' /proc/meminfo"),
        ("paths", "find /proc /sys/devices/qdrv -maxdepth 2 -type f 2>/dev/null | grep -E 'qdrv|muc|hbm|packet|dev64|wireless|rssi|temp' | sort"),
        ("netdev64", "cat /proc/net/dev64 2>/dev/null; cat /proc/net/packets64 2>/dev/null"),
        ("qdrvdata", "head -c 4096 /proc/qdrvdata 2>/dev/null"),
        ("wireless", "cat /proc/net/wireless 2>/dev/null; cat /sys/devices/qdrv/rssi_phy_stats 2>/dev/null"),
        ("noise", "call_qcsapi -u get_noise wifi0"),
        ("chains", "for i in 0 1 2 3; do echo chain=$i; call_qcsapi -u get_rssi_by_chain wifi0 $i; done"),
        ("congestion", "call_qcsapi -u get_congestion_index wifi0"),
        ("associations", "call_qcsapi -u get_count_associations wifi0"),
        ("interfaces", "ifconfig wifi0; ifconfig wlan0"),
    ]
    sections: list[str] = []
    for index, (name, command) in enumerate(commands):
        marker = f"__OM07_{index}__"
        output = run(proc, command, marker)
        output = output.split(marker, 1)[0].strip("\n# ")
        sections.append(f"## {name}\n\n```text\n{output}\n```\n")
    proc.write("exit\r\n")

    destination = ROOT / "outputs" / "radio-re" / "live-telemetry.md"
    destination.write_text("# OpenMitraStar live radio telemetry\n\n" + "\n".join(sections), encoding="utf-8")
    print(destination)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
