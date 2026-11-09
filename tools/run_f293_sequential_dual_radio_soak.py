#!/usr/bin/env python3
"""Run a resumable long F293 soak using one AELITA client sequentially."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import statistics
import subprocess
import sys
import time


ROOT = Path(__file__).resolve().parents[1]
DEVICE = "hgw500bna-qcv2-a2-primary"
BUILD = Path.home() / f".openmitrastar/devices/{DEVICE}/firmware/f293-device-bound"
KNOWN_HOSTS = BUILD / "known_hosts.f293"
MANIFEST = BUILD / "manifest.json"
EXPECTED_VERSION = "lyoko-foundation-6.5.1-f293-emac-hw-rx-demand-device"
EXPECTED_SHA256 = "76f07b7d868fe878fe032bf302b2c75340498cd0186537bf75fc3ef9066ddc37"
ACK = "OPENMITRASTAR_F293_SEQUENTIAL_DUAL_RADIO_SOAK"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def tcp_open(host: str, port: int = 22, timeout: float = 1.5) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def bounded_hours(value: str) -> float:
    parsed = float(value)
    if not 0.25 <= parsed <= 24:
        raise argparse.ArgumentTypeError("duration must be 0.25..24 hours")
    return parsed


def router_snapshot(host: str) -> dict[str, object]:
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    remote = r'''set -eu
printf 'FIRMWARE='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'MEMAVAILABLE_KB='; awk '/^MemAvailable:/ {print $2;exit}' /proc/meminfo
printf 'UPTIME='; cut -d' ' -f1 /proc/uptime
printf 'FATAL='; dmesg | grep -Eic 'kernel panic|Oops:|BUG:|Misaligned Access|watchdog.*reset|qdrv.*fatal|muc.*fatal|auc.*fatal' || true
printf 'RADIO2='; /usr/sbin/om-radioctl status 2g
printf 'RADIO5='; /usr/sbin/om-radioctl status 5g
'''
    proc = subprocess.run(
        [
            ssh,
            "-i", str(Path.home() / ".ssh/id_ed25519"),
            "-o", "IdentitiesOnly=yes",
            "-o", "BatchMode=yes",
            "-o", "ConnectTimeout=8",
            "-o", "StrictHostKeyChecking=yes",
            "-o", f"UserKnownHostsFile={KNOWN_HOSTS}",
            "-o", "LogLevel=ERROR",
            f"root@{host}", remote,
        ],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if proc.returncode:
        raise RuntimeError(f"router snapshot failed: {proc.stderr[:200]}")
    result: dict[str, object] = {}
    for line in proc.stdout.splitlines():
        key, separator, value = line.partition("=")
        if not separator:
            continue
        if key in {"RADIO2", "RADIO5"}:
            result[key.lower()] = json.loads(value)
        elif key in {"MEMAVAILABLE_KB", "FATAL"}:
            result[key.lower()] = int(value or 0)
        elif key == "UPTIME":
            result["uptime_seconds"] = float(value or 0)
        elif key == "FIRMWARE":
            result["firmware"] = value
    return result


def run_logged(command: list[str], log: Path, timeout: int) -> int:
    proc = subprocess.run(
        command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=timeout,
        check=False,
    )
    log.write_text(proc.stdout or "", encoding="utf-8")
    return proc.returncode


def latest_result(directory: Path, pattern: str) -> Path:
    files = list(directory.glob(pattern))
    if not files:
        raise RuntimeError(f"missing result in {directory}")
    return max(files, key=lambda path: path.stat().st_mtime)


def mbps(item: dict[str, object]) -> float:
    return float(item.get("speed_Bps") or 0) * 8 / 1_000_000


def compact_cycle(index: int, radio2: dict[str, object], radio5: dict[str, object], router: dict[str, object]) -> dict[str, object]:
    radio2_ok = bool(
        radio2.get("controller_download", {}).get("pass") is True
        and radio2.get("controller_upload", {}).get("pass") is True
        and radio2.get("router_health_gate", {}).get("pass") is True
        and radio2.get("execution_error") is None
    )
    radio5_ok = bool(
        radio5.get("status") == "PASS"
        and radio5.get("download", {}).get("pass") is True
        and radio5.get("upload", {}).get("pass") is True
        and int(radio5.get("soak", {}).get("disconnects") or 0) == 0
        and radio5.get("router", {}).get("status") == "PASS"
    )
    router_ok = bool(
        router.get("firmware") == EXPECTED_VERSION
        and int(router.get("fatal") or 0) == 0
        and int(router.get("memavailable_kb") or 0) >= 8192
        and router.get("radio2", {}).get("lifecycle") in {"ap-ready", "traffic-ready"}
        and router.get("radio5", {}).get("lifecycle") in {"ap-ready", "traffic-ready"}
    )
    return {
        "cycle": index,
        "status": "PASS" if radio2_ok and radio5_ok and router_ok else "FAIL",
        "radio2": {
            "download_mbps": round(mbps(radio2.get("controller_download", {})), 3),
            "upload_mbps": round(mbps(radio2.get("controller_upload", {})), 3),
            "router_health": radio2_ok,
            "rx_restarts": int(radio2.get("emac_stats_delta", {}).get("rx_restart_total") or 0),
        },
        "radio5": {
            "download_mbps": float(radio5.get("download", {}).get("mbps") or 0),
            "upload_mbps": float(radio5.get("upload", {}).get("mbps") or 0),
            "disconnects": int(radio5.get("soak", {}).get("disconnects") or 0),
        },
        "router": {
            "memavailable_kb": int(router.get("memavailable_kb") or 0),
            "uptime_seconds": float(router.get("uptime_seconds") or 0),
            "fatal": int(router.get("fatal") or 0),
        },
    }


def summarize(cycles: list[dict[str, object]], started: datetime, finished: datetime) -> dict[str, object]:
    passed = bool(cycles) and all(cycle.get("status") == "PASS" for cycle in cycles)
    radio2_down = [float(cycle["radio2"]["download_mbps"]) for cycle in cycles]
    radio2_up = [float(cycle["radio2"]["upload_mbps"]) for cycle in cycles]
    radio5_down = [float(cycle["radio5"]["download_mbps"]) for cycle in cycles]
    radio5_up = [float(cycle["radio5"]["upload_mbps"]) for cycle in cycles]
    return {
        "schema": "openmitrastar.f293-sequential-dual-radio-soak/v1",
        "status": "PASS" if passed else "FAIL",
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "elapsed_seconds": round((finished - started).total_seconds(), 3),
        "cycles_completed": len(cycles),
        "all_cycles_passed": passed,
        "median_mbps": {
            "radio2_down": round(statistics.median(radio2_down), 3) if radio2_down else 0,
            "radio2_up": round(statistics.median(radio2_up), 3) if radio2_up else 0,
            "radio5_down": round(statistics.median(radio5_down), 3) if radio5_down else 0,
            "radio5_up": round(statistics.median(radio5_up), 3) if radio5_up else 0,
        },
        "radio5_disconnects": sum(int(cycle["radio5"]["disconnects"]) for cycle in cycles),
        "rx_restarts": sum(int(cycle["radio2"]["rx_restarts"]) for cycle in cycles),
        "minimum_memavailable_kb": min((int(cycle["router"]["memavailable_kb"]) for cycle in cycles), default=0),
        "client_mode": "single-AELITA-sequential",
        "simultaneous_dual_radio": False,
        "flash": False,
        "mtd_writes": False,
    }


def load_completed_cycles(output_dir: Path) -> list[dict[str, object]]:
    cycles: list[dict[str, object]] = []
    for expected, directory in enumerate(sorted(output_dir.glob("cycle-[0-9][0-9][0-9]")), start=1):
        if directory.name != f"cycle-{expected:03d}":
            raise RuntimeError("soak cycle directories are not contiguous")
        result_path = directory / "cycle.json"
        if not result_path.is_file():
            raise RuntimeError(f"missing completed cycle result: {result_path}")
        result = json.loads(result_path.read_text(encoding="ascii"))
        if result.get("cycle") != expected or result.get("status") != "PASS":
            raise RuntimeError(f"resume refused for incomplete or failed cycle {expected}")
        cycles.append(result)
    return cycles


def resume_started_at(output_dir: Path) -> datetime:
    checkpoint = output_dir / "checkpoint.json"
    if not checkpoint.is_file():
        raise RuntimeError("resume requires checkpoint.json")
    payload = json.loads(checkpoint.read_text(encoding="ascii"))
    started = datetime.fromisoformat(str(payload.get("started_at") or ""))
    if started.tzinfo is None:
        raise RuntimeError("checkpoint started_at must include a timezone")
    return started


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    parser.add_argument("--router-host", default="192.168.1.90")
    parser.add_argument("--oracle-host", default="192.168.1.63")
    parser.add_argument("--oracle-user", default="AELITA")
    parser.add_argument("--controller-url", default="http://192.168.1.43:8008/speed.bin")
    parser.add_argument("--duration-hours", type=bounded_hours, default=6.0)
    parser.add_argument("--soak-seconds", type=int, default=120)
    parser.add_argument("--cycle-pause-seconds", type=int, default=30)
    parser.add_argument("--max-cycles", type=int, default=0)
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    if not 120 <= args.soak_seconds <= 600:
        raise SystemExit("--soak-seconds must be 120..600")
    manifest = json.loads(MANIFEST.read_text(encoding="ascii"))
    candidate = BUILD / manifest["artifacts"]["webformat"]["file"]
    candidate_hash = sha256(candidate)
    if args.output_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        args.output_dir = ROOT / f"outputs/soak/f293-sequential-dual-radio-{stamp}"
    args.output_dir = args.output_dir.resolve()
    if args.resume:
        if not args.output_dir.is_dir():
            raise SystemExit("--resume requires an existing output directory")
        previous_plan = json.loads((args.output_dir / "plan.json").read_text(encoding="ascii"))
        if previous_plan.get("candidate_sha256") != EXPECTED_SHA256:
            raise SystemExit("resume candidate hash mismatch")
        if float(previous_plan.get("duration_hours") or 0) != args.duration_hours:
            raise SystemExit("resume duration mismatch")
        if int(previous_plan.get("soak_seconds_per_band") or 0) != args.soak_seconds:
            raise SystemExit("resume per-band soak mismatch")
        completed_cycles = load_completed_cycles(args.output_dir)
    else:
        if args.output_dir.exists() and any(args.output_dir.iterdir()):
            raise SystemExit("refusing to overwrite existing soak evidence; use --resume")
        completed_cycles = []
    plan = {
        "schema": "openmitrastar.f293-sequential-dual-radio-soak-plan/v1",
        "mode": "execute" if args.execute else "dry-run",
        "required_firmware": EXPECTED_VERSION,
        "candidate_sha256": candidate_hash,
        "candidate_matches": candidate_hash == EXPECTED_SHA256,
        "router_ssh": tcp_open(args.router_host),
        "oracle_ssh": tcp_open(args.oracle_host),
        "duration_hours": args.duration_hours,
        "soak_seconds_per_band": args.soak_seconds,
        "cycle_pause_seconds": args.cycle_pause_seconds,
        "resume": args.resume,
        "completed_cycles": len(completed_cycles),
        "next_cycle": len(completed_cycles) + 1,
        "client_mode": "single-AELITA-sequential",
        "simultaneous_dual_radio": False,
        "restore_ssid": "MOVISTAR-WIFI6-A348",
        "flash": False,
        "mtd_writes": False,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "plan.json").write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(plan, indent=2, sort_keys=True))
    if not args.execute:
        return 0
    if args.ack != ACK:
        raise SystemExit("exact --ack is required")
    if not plan["candidate_matches"] or not plan["router_ssh"] or not plan["oracle_ssh"]:
        raise SystemExit("F293 soak preflight failed")
    before = router_snapshot(args.router_host)
    if before.get("firmware") != EXPECTED_VERSION:
        raise SystemExit(f"expected F293 runtime, got {before.get('firmware')!r}")

    started = resume_started_at(args.output_dir) if args.resume else datetime.now(timezone.utc)
    elapsed = max(0.0, (datetime.now(timezone.utc) - started).total_seconds())
    remaining = max(0.0, args.duration_hours * 3600 - elapsed)
    deadline = time.monotonic() + remaining
    cycles = list(completed_cycles)
    checkpoint_path = args.output_dir / "checkpoint.json"
    checkpoint = summarize(cycles, started, datetime.now(timezone.utc))
    checkpoint["status"] = "IN_PROGRESS"
    checkpoint["target_duration_hours"] = args.duration_hours
    checkpoint_path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="ascii")
    server = ROOT / "tools/ensure_lyoko_speed_server.ps1"
    subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(server), "-Action", "Ensure", "-Port", "8008", "-PayloadMiB", "32", "-AllowedClient", args.oracle_host],
        cwd=ROOT, check=True,
    )
    try:
        index = len(cycles) + 1
        while time.monotonic() < deadline and (args.max_cycles <= 0 or index <= args.max_cycles):
            cycle_dir = args.output_dir / f"cycle-{index:03d}"
            radio2_dir = cycle_dir / "radio2"
            radio5_dir = cycle_dir / "radio5"
            cycle_dir.mkdir(parents=True, exist_ok=True)
            rc2 = run_logged(
                [
                    sys.executable, str(ROOT / "tools/run_aelita_2g_wpa2_speed_router_probe.py"),
                    "--router-host", args.router_host,
                    "--router-known-hosts", str(KNOWN_HOSTS),
                    "--oracle-host", args.oracle_host,
                    "--oracle-user", args.oracle_user,
                    "--controller-url", args.controller_url,
                    "--traffic-direction", "both",
                    "--interval", "3",
                    "--wait-result", str(args.soak_seconds + 240),
                    "--child-timeout", str(args.soak_seconds + 180),
                    "--recovery-window", "120",
                    "--restore-watchdog-minutes", "5",
                    "--soak-seconds", str(args.soak_seconds),
                    "--output-dir", str(radio2_dir),
                ],
                cycle_dir / "radio2.log",
                args.soak_seconds + 420,
            )
            if rc2:
                raise RuntimeError(f"cycle {index} 2.4 GHz failed")
            radio2 = json.loads((radio2_dir / "summary.json").read_text(encoding="utf-8"))

            rc5 = run_logged(
                [
                    sys.executable, str(ROOT / "tools/run_f293_5g_aelita_traffic.py"),
                    "--execute", "--ack", "OPENMITRASTAR_F293_5G_AELITA_TRAFFIC",
                    "--router-host", args.router_host,
                    "--oracle-host", args.oracle_host,
                    "--oracle-user", args.oracle_user,
                    "--controller-url", args.controller_url,
                    "--soak-seconds", str(args.soak_seconds),
                    "--output-dir", str(radio5_dir),
                ],
                cycle_dir / "radio5.log",
                args.soak_seconds + 420,
            )
            if rc5:
                raise RuntimeError(f"cycle {index} 5 GHz failed")
            radio5 = json.loads(latest_result(radio5_dir, "result-*.json").read_text(encoding="utf-8"))
            cycle = compact_cycle(index, radio2, radio5, router_snapshot(args.router_host))
            cycles.append(cycle)
            (cycle_dir / "cycle.json").write_text(json.dumps(cycle, indent=2, sort_keys=True) + "\n", encoding="ascii")
            checkpoint = summarize(cycles, started, datetime.now(timezone.utc))
            checkpoint["status"] = "IN_PROGRESS"
            checkpoint["target_duration_hours"] = args.duration_hours
            checkpoint_path.write_text(json.dumps(checkpoint, indent=2, sort_keys=True) + "\n", encoding="ascii")
            if cycle["status"] != "PASS":
                raise RuntimeError(f"cycle {index} health gate failed")
            index += 1
            if time.monotonic() < deadline:
                time.sleep(max(0, args.cycle_pause_seconds))
    finally:
        subprocess.run(
            ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(server), "-Action", "Stop", "-Port", "8008", "-AllowedClient", args.oracle_host],
            cwd=ROOT, check=False,
        )

    result = summarize(cycles, started, datetime.now(timezone.utc))
    (args.output_dir / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
