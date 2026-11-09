#!/usr/bin/env python3
"""Fail-closed RAM-equivalence gate for the F5 management foundation.

The default invocation is a local-only dry run.  ``--execute`` observes an
already RAM-booted router and never boots, reboots, writes flash, changes
Bootbase state, or starts a radio.  The resulting attestation is accepted by
``F5_FOUNDATION_FLASH_CANDIDATE_INPUT_CONTRACT.json`` only after every runtime
gate passes.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import socket
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = ROOT / "work" / "mission-state" / "f5-foundation-flash-candidate"
DEFAULT_CANDIDATE = CANDIDATE_DIR / "openmitrastar-linux510-f5-foundation-webformat.bin"
DEFAULT_MANIFEST = CANDIDATE_DIR / "manifest.json"
DEFAULT_RAM_IMAGE = ROOT / "work" / "tftp" / "omvl" / "linux510-foundation-oem-parity-nowdt-v1-RAM-ONLY.bin"
DEFAULT_UART_LOG = ROOT / "outputs" / "uart-live" / "ramssh-cycle-20260820-190705.log"
DEFAULT_OUTPUT = CANDIDATE_DIR / "ram-equivalence.json"
EXPECTED_SHA256 = "4bca4d3c97e0d7d76f6599bc9c87d02dc571c027971b2cdf7cbfa9639000e081"
EXPECTED_BYTES = 6_774_784
RAM_BOOT_NAME = "linux510-foundation-oem-parity-nowdt-v1-RAM-ONLY.bin"
DEFAULT_HOST = "192.168.1.90"
ACK = "OPENMITRASTAR_F5_FOUNDATION_RAM_EQUIVALENCE"
MIN_DURATION_S = 180
PROFILE = "F5_FOUNDATION"
SCOPE = "MANAGEMENT-ONLY"
RUNNER_SCHEMA = "openmitrastar.f5-foundation-ram-equivalence-runner/v1"
PASS_MARKER_PREFIX = "OM_F5_FOUNDATION_RAM_EQ"
EXPECTED_DEGRADED_SERVICES = ("S50-radio-ap",)

FATAL_RE = re.compile(
    r"Kernel panic|\bOops\b|BUG:|use-after-free|KASAN|nobody cared|"
    r"Unable to handle kernel|hard LOCKUP|soft lockup|watchdog.*reset|"
    r"descriptor.*error|DMA.*error|EV_TLB|MuC exception|forcing reboot",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative(path: Path) -> str:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except ValueError:
        return str(path.resolve())


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def evidence_entries(status: str, paths: list[Path]) -> list[dict[str, str]]:
    """Return hash-bearing evidence only for a complete PASS."""
    if status != "PASS":
        return []
    return [{"path": relative(path), "sha256": sha256(path)} for path in paths]


def parse_kv(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in text.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if re.fullmatch(r"[A-Z0-9_]+", key):
            result[key] = value.strip()
    return result


def integer_series(samples: list[dict[str, Any]], key: str) -> list[int]:
    return [sample[key] for sample in samples if isinstance(sample.get(key), int)]


def overall_progress(values: list[int]) -> bool:
    return len(values) >= 2 and values[-1] > values[0] and all(b >= a for a, b in zip(values, values[1:]))


def evaluate_samples(
    samples: list[dict[str, Any]], duration_observed: float, duration_required: int
) -> tuple[dict[str, Any], list[str]]:
    summary: dict[str, Any] = {
        "duration_required_s": duration_required,
        "duration_observed_s": round(duration_observed, 3),
        "sample_count": len(samples),
        "all_local_ping": bool(samples) and all(sample.get("local_ping") is True for sample in samples),
        "all_ssh_primary": bool(samples) and all(sample.get("ssh_primary") is True for sample in samples),
        "all_ssh_fresh": bool(samples) and all(sample.get("ssh_fresh") is True for sample in samples),
        "all_http80_cgi_executed": bool(samples)
        and all(sample.get("http80_cgi_executed") is True for sample in samples),
        "all_http8080_closed": bool(samples)
        and all(sample.get("http8080_closed") is True for sample in samples),
        "all_product_degraded_as_expected": bool(samples)
        and all(sample.get("boot_degraded") == 1 for sample in samples),
        "all_web_alive": bool(samples) and all(sample.get("minihttpd_alive") == 1 for sample in samples),
        "all_radio2g_fail_closed": bool(samples)
        and all(sample.get("wlan0_closed") == 1 and sample.get("radio2g_refused_no_psk") == 1 for sample in samples),
        "all_radio5g_fail_closed": bool(samples) and all(sample.get("wifi0_closed") == 1 for sample in samples),
        "all_hostapd_absent": bool(samples) and all(sample.get("hostapd_absent") == 1 for sample in samples),
        "all_br0_absent": bool(samples) and all(sample.get("br0_absent") == 1 for sample in samples),
        "all_expected_degraded_marker": bool(samples)
        and all(sample.get("only_radio_degraded") == 1 for sample in samples),
        "all_eth0_error_free": bool(samples)
        and all(sample.get("eth0_rx_errors") == 0 and sample.get("eth0_tx_errors") == 0 for sample in samples),
    }
    for key in ("uptime_s", "eth0_rx_bytes", "eth0_rx_packets", "eth0_tx_bytes", "eth0_tx_packets", "irq20"):
        series = integer_series(samples, key)
        summary[f"{key}_start"] = series[0] if series else None
        summary[f"{key}_end"] = series[-1] if series else None
        summary[f"{key}_progress"] = overall_progress(series)

    checks = [
        (len(samples) >= 2, "insufficient_samples"),
        (duration_observed >= duration_required, "duration_short"),
        (summary["all_local_ping"], "management_icmp_failure"),
        (summary["all_ssh_primary"], "ssh_primary_failure"),
        (summary["all_ssh_fresh"], "ssh_fresh_failure"),
        (summary["all_http80_cgi_executed"], "http80_cgi_not_executed"),
        (summary["all_http8080_closed"], "diagnostic_port_8080_open"),
        (summary["all_product_degraded_as_expected"], "unexpected_boot_state"),
        (summary["all_web_alive"], "minihttpd_not_alive"),
        (summary["all_radio2g_fail_closed"], "radio2g_not_fail_closed"),
        (summary["all_radio5g_fail_closed"], "radio5g_not_fail_closed"),
        (summary["all_hostapd_absent"], "hostapd_running"),
        (summary["all_br0_absent"], "br0_present"),
        (summary["all_expected_degraded_marker"], "unexpected_degraded_service"),
        (summary["all_eth0_error_free"], "eth0_errors_nonzero"),
    ]
    for key in ("uptime_s", "eth0_rx_bytes", "eth0_rx_packets", "eth0_tx_bytes", "eth0_tx_packets", "irq20"):
        checks.append((bool(summary[f"{key}_progress"]), f"{key}_no_progress"))
    failures = [reason for passed, reason in checks if not passed]
    summary["fail_reasons"] = failures
    summary["pass"] = not failures
    return summary, failures


def uart_gate(path: Path) -> tuple[bool, dict[str, bool]]:
    text = path.read_bytes().replace(b"\x00", b"").decode("utf-8", "replace")
    markers = {
        "bootbase_prompt": "topaz>" in text,
        "tftp_recovery_path": "TFTP from server" in text,
        "candidate_tftp_name": f"Filename '{RAM_BOOT_NAME}'." in text,
        "candidate_byte_count": f"Bytes transferred = {EXPECTED_BYTES}" in text,
        "bootm_handoff": "bootm 0x83000000" in text,
        "linux_5_10": "Linux version 5.10.260-openmitrastar-radiohw" in text,
        "network_ready": "OMNETWORK_READY profile=oem-videobridge interface=eth0 ipv4=192.168.1.90" in text,
        "ssh_key_only_ready": "OMSSH_READY port=22 auth=ed25519-key-only" in text,
        "product_management_only": "OMPRODUCT_READY state=degraded schema=1" in text,
        "radio_ap_failed_closed": all(
            f"OMINIT_SERVICE_END name={service} rc=1" in text
            for service in EXPECTED_DEGRADED_SERVICES
        ),
        "fatal_absent": FATAL_RE.search(text) is None,
    }
    return all(markers.values()), markers


def run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
        check=False,
    )


def local_ping(host: str) -> bool:
    return run(["ping.exe", "-n", "2", "-w", "1000", host], timeout=8).returncode == 0


def ssh(host: str, command: str, timeout: int = 25) -> subprocess.CompletedProcess[str]:
    return run(
        [
            sys.executable,
            str(ROOT / "tools" / "ramssh_exec.py"),
            command,
            "--host",
            host,
            "--timeout",
            str(timeout),
        ],
        timeout=timeout + 15,
    )


def cgi_executes_on_port_80(host: str) -> bool:
    conn = http.client.HTTPConnection(host, 80, timeout=5)
    try:
        conn.request("GET", "/index.cgi", headers={"Connection": "close"})
        response = conn.getresponse()
        body = response.read(128 * 1024).decode("utf-8", "replace")
        content_type = response.getheader("Content-Type", "").lower()
        return (
            response.status == 200
            and "text/html" in content_type
            and "OpenMitraStar" in body
            and "Acceso" in body
            and "#!/bin/ash" not in body
            and "OM_WEB_DISPATCHER" not in body
            and "exec \"${OM_WEB_DISPATCHER" not in body
        )
    except OSError:
        return False
    finally:
        conn.close()


def port_8080_refused(host: str) -> bool:
    try:
        with socket.create_connection((host, 8080), timeout=3):
            return False
    except ConnectionRefusedError:
        return True
    except OSError as exc:
        # Windows uses WSAECONNREFUSED=10061; a timeout is not proof of closure.
        return getattr(exc, "winerror", None) == 10061 or getattr(exc, "errno", None) in {61, 111, 10061}


def remote_snapshot_command() -> str:
    # Aggregate-only telemetry: no cookies, keys, credentials or station data.
    expected_count = len(EXPECTED_DEGRADED_SERVICES)
    expected_terms = " ".join(
        f'$1 == "{service}" && $2 == "1" {{ seen_{index}++ }}'
        for index, service in enumerate(EXPECTED_DEGRADED_SERVICES)
    )
    expected_final = " && ".join(
        f"seen_{index} == 1" for index, _service in enumerate(EXPECTED_DEGRADED_SERVICES)
    )
    script = r'''set -u
devstat() { awk -v dev="$1" '$1 == dev":" {print $2, $3, $4, $10, $11, $12}' /proc/net/dev; }
irqsum() { awk -v irq="$1:" '$1 == irq {s=0; for(i=2;i<=NF;i++){if($i ~ /^[0-9]+$/) s+=$i; else break}; print s; found=1} END{if(!found) print -1}' /proc/interrupts; }
closed_if() { if [ ! -e "/sys/class/net/$1" ]; then echo 1; else state=$(cat "/sys/class/net/$1/operstate" 2>/dev/null || echo unknown); [ "$state" = down ] && echo 1 || echo 0; fi; }
set -- $(devstat eth0); echo ETH0_RX_BYTES=${1:--1}; echo ETH0_RX_PACKETS=${2:--1}; echo ETH0_RX_ERRORS=${3:--1}; echo ETH0_TX_BYTES=${4:--1}; echo ETH0_TX_PACKETS=${5:--1}; echo ETH0_TX_ERRORS=${6:--1}
echo UPTIME_S=$(cut -d. -f1 /proc/uptime)
echo IRQ20=$(irqsum 20)
test "$(cat /run/openmitrastar/boot-state 2>/dev/null)" = degraded && echo BOOT_DEGRADED=1 || echo BOOT_DEGRADED=0
pid=$(cat /run/openmitrastar/web/mini_httpd.pid 2>/dev/null || true); case "$pid" in ''|*[!0-9]*) echo MINIHTTPD_ALIVE=0;; *) kill -0 "$pid" 2>/dev/null && echo MINIHTTPD_ALIVE=1 || echo MINIHTTPD_ALIVE=0;; esac
echo WLAN0_CLOSED=$(closed_if wlan0)
echo WIFI0_CLOSED=$(closed_if wifi0)
test "$(cat /run/openmitrastar/radio2g/state 2>/dev/null)" = refused-no-psk && echo RADIO2G_REFUSED_NO_PSK=1 || echo RADIO2G_REFUSED_NO_PSK=0
hostapd=0; for p in /proc/[0-9]*/comm; do [ -r "$p" ] || continue; grep -q '^hostapd' "$p" 2>/dev/null && hostapd=1; done; [ "$hostapd" = 0 ] && echo HOSTAPD_ABSENT=1 || echo HOSTAPD_ABSENT=0
test ! -e /sys/class/net/br0 && echo BR0_ABSENT=1 || echo BR0_ABSENT=0
[ "$(awk '__EXPECTED_TERMS__ NF {n++} END {print (n == __EXPECTED_COUNT__ && __EXPECTED_FINAL__) ? 1 : 0}' /run/openmitrastar/degraded 2>/dev/null)" = 1 ] && echo ONLY_RADIO_DEGRADED=1 || echo ONLY_RADIO_DEGRADED=0
'''
    return script.replace("__EXPECTED_TERMS__", expected_terms).replace(
        "__EXPECTED_COUNT__", str(expected_count)
    ).replace("__EXPECTED_FINAL__", expected_final)


def collect_sample(host: str, elapsed: float) -> dict[str, Any]:
    sample: dict[str, Any] = {
        "elapsed_s": round(elapsed, 3),
        "local_ping": local_ping(host),
        "ssh_primary": False,
        "ssh_fresh": False,
        "http80_cgi_executed": False,
        "http8080_closed": False,
    }
    primary = ssh(host, remote_snapshot_command())
    sample["ssh_primary"] = primary.returncode == 0
    if primary.returncode == 0:
        values = parse_kv(primary.stdout)
        mapping = {
            "UPTIME_S": "uptime_s",
            "IRQ20": "irq20",
            "ETH0_RX_BYTES": "eth0_rx_bytes",
            "ETH0_RX_PACKETS": "eth0_rx_packets",
            "ETH0_RX_ERRORS": "eth0_rx_errors",
            "ETH0_TX_BYTES": "eth0_tx_bytes",
            "ETH0_TX_PACKETS": "eth0_tx_packets",
            "ETH0_TX_ERRORS": "eth0_tx_errors",
            "BOOT_DEGRADED": "boot_degraded",
            "MINIHTTPD_ALIVE": "minihttpd_alive",
            "WLAN0_CLOSED": "wlan0_closed",
            "WIFI0_CLOSED": "wifi0_closed",
            "RADIO2G_REFUSED_NO_PSK": "radio2g_refused_no_psk",
            "HOSTAPD_ABSENT": "hostapd_absent",
            "BR0_ABSENT": "br0_absent",
            "ONLY_RADIO_DEGRADED": "only_radio_degraded",
        }
        for source, target in mapping.items():
            try:
                sample[target] = int(values.get(source, "-1"))
            except ValueError:
                sample[target] = -1
    # A distinct second connection is mandatory for every sample.
    sample["ssh_fresh"] = ssh(host, "true", timeout=10).returncode == 0
    sample["http80_cgi_executed"] = cgi_executes_on_port_80(host)
    sample["http8080_closed"] = port_8080_refused(host)
    return sample


def static_checks(candidate: Path, manifest_path: Path, ram_image: Path, uart_log: Path) -> tuple[dict[str, bool], dict[str, bool]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    candidate_sha = sha256(candidate)
    ram_sha = sha256(ram_image)
    uart_ok, uart_markers = uart_gate(uart_log)
    checks = {
        "candidate_sha256_pinned": candidate_sha == EXPECTED_SHA256,
        "candidate_size_pinned": candidate.stat().st_size == EXPECTED_BYTES,
        "ram_image_sha256_pinned": ram_sha == EXPECTED_SHA256,
        "ram_image_size_pinned": ram_image.stat().st_size == EXPECTED_BYTES,
        "candidate_ram_byte_identical": candidate_sha == ram_sha and candidate.stat().st_size == ram_image.stat().st_size,
        "manifest_candidate": manifest.get("artifact", {}).get("sha256") == candidate_sha
        and manifest.get("artifact", {}).get("size") == candidate.stat().st_size,
        "manifest_profile": manifest.get("profile") == PROFILE and manifest.get("scope") == SCOPE,
        "manifest_target": manifest.get("target", {})
        == {"hardware_revision": "A2", "model": "HGW-500BNA-QCv2", "slot": "linux_live"},
        "manifest_eligible_not_ready": manifest.get("candidate_eligible") is True and manifest.get("flash_ready") is False,
        "uart_exact_ram_boot": uart_ok,
    }
    return checks, uart_markers


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ram-image", type=Path, default=DEFAULT_RAM_IMAGE)
    parser.add_argument("--uart-log", type=Path, default=DEFAULT_UART_LOG)
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--duration", type=int, default=MIN_DURATION_S)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    args = parser.parse_args(argv)

    candidate = args.candidate.resolve()
    manifest_path = args.manifest.resolve()
    ram_image = args.ram_image.resolve()
    uart_log = args.uart_log.resolve()
    missing = [str(path) for path in (candidate, manifest_path, ram_image, uart_log) if not path.is_file()]
    if missing:
        raise SystemExit("missing required local input: " + ", ".join(missing))

    checks, uart_markers = static_checks(candidate, manifest_path, ram_image, uart_log)
    plan = {
        "schema": RUNNER_SCHEMA,
        "mode": "EXECUTE_READ_ONLY_OBSERVATION" if args.execute else "DRY_RUN_LOCAL_ONLY",
        "profile": PROFILE,
        "scope": SCOPE,
        "host": args.host,
        "candidate": relative(candidate),
        "candidate_sha256": sha256(candidate),
        "ram_image": relative(ram_image),
        "uart_log": relative(uart_log),
        "duration_s": args.duration,
        "interval_s": args.interval,
        "ssh_operations_per_sample": 2,
        "runtime_checks": [
            "exact candidate and RAM image are byte-identical and UART-attested",
            "at least 180 seconds continuous management observation",
            "ICMP plus two independent key-only SSH operations per sample",
            "HTTP port 80 executes index.cgi and never serves its source",
            "diagnostic port 8080 refuses connections",
            "eth0 RX/TX bytes+packets and IRQ20 progress without errors",
            "wlan0/wifi0, hostapd and br0 remain fail-closed",
            "no fatal UART or dmesg marker",
            "Bootbase prompt, TFTP transfer and bootm recovery path are present",
        ],
        "static_checks": checks,
        "uart_markers": uart_markers,
        "hardware_actions": False if not args.execute else "read-only runtime observation",
        "flash_actions": False,
        "secrets_logged": False,
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    if not all(checks.values()):
        print(f"{PASS_MARKER_PREFIX}_STATIC_FAIL", file=sys.stderr)
        return 2
    if not args.execute:
        print(f"{PASS_MARKER_PREFIX}_DRY_RUN_PASS=1")
        return 0

    if args.ack != ACK:
        raise SystemExit(f"--execute requires --ack {ACK}")
    if args.host != DEFAULT_HOST:
        raise SystemExit(f"execute mode is pinned to --host {DEFAULT_HOST}")
    if args.duration < MIN_DURATION_S or not 5 <= args.interval <= 30:
        raise SystemExit(f"execute mode requires duration>={MIN_DURATION_S} and 5<=interval<=30")

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = (
        args.evidence_dir.resolve()
        if args.evidence_dir
        else CANDIDATE_DIR / f"ram-equivalence-{stamp}"
    )
    evidence_dir.mkdir(parents=True, exist_ok=False)
    samples_path = evidence_dir / "samples.jsonl"
    summary_path = evidence_dir / "summary.json"
    dmesg_before_path = evidence_dir / "dmesg-before.log"
    dmesg_final_path = evidence_dir / "dmesg-final.log"
    uart_attestation_path = evidence_dir / "uart-attestation.json"
    write_json(
        uart_attestation_path,
        {"path": relative(uart_log), "markers": uart_markers, "pass": all(uart_markers.values())},
    )

    dmesg_before = ssh(args.host, "dmesg", timeout=30)
    if dmesg_before.returncode != 0:
        raise SystemExit("cannot capture initial dmesg over key-only SSH")
    dmesg_before_path.write_text(dmesg_before.stdout, encoding="utf-8")

    start = time.monotonic()
    samples: list[dict[str, Any]] = []
    while True:
        elapsed = time.monotonic() - start
        sample = collect_sample(args.host, elapsed)
        samples.append(sample)
        with samples_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(sample, sort_keys=True) + "\n")
        print(
            "OM_F5_FOUNDATION_SAMPLE "
            f"n={len(samples)} t={sample['elapsed_s']} ping={int(bool(sample.get('local_ping')))} "
            f"ssh={int(bool(sample.get('ssh_primary')))}+{int(bool(sample.get('ssh_fresh')))} "
            f"cgi80={int(bool(sample.get('http80_cgi_executed')))} "
            f"closed8080={int(bool(sample.get('http8080_closed')))} "
            f"radio_closed={sample.get('wlan0_closed', -1)}+{sample.get('wifi0_closed', -1)} "
            f"hostapd_absent={sample.get('hostapd_absent', -1)} br0_absent={sample.get('br0_absent', -1)}",
            flush=True,
        )
        remaining = args.duration - (time.monotonic() - start)
        if remaining <= 0:
            break
        time.sleep(min(args.interval, remaining))
    duration_observed = time.monotonic() - start

    dmesg_final = ssh(args.host, "dmesg", timeout=30)
    final_text = dmesg_final.stdout if dmesg_final.returncode == 0 else "DMESG_FETCH_FAILED\n"
    dmesg_final_path.write_text(final_text, encoding="utf-8")
    summary, failures = evaluate_samples(samples, duration_observed, args.duration)
    summary["uart_gate"] = all(uart_markers.values())
    summary["fatal_dmesg_full"] = bool(FATAL_RE.search(final_text))
    if dmesg_final.returncode != 0:
        failures.append("final_dmesg_fetch_failed")
    if summary["fatal_dmesg_full"]:
        failures.append("fatal_dmesg_marker")
    summary["fail_reasons"] = sorted(set(failures))
    summary["pass"] = not summary["fail_reasons"]
    write_json(summary_path, summary)

    checks_out = {
        "boot": "PASS" if all(uart_markers.values()) else "FAIL",
        "product_rootfs": "PASS" if summary.get("all_product_degraded_as_expected") and summary.get("all_web_alive") else "FAIL",
        "ethernet": "PASS" if summary.get("all_local_ping") and summary.get("eth0_rx_packets_progress") and summary.get("eth0_tx_packets_progress") and summary.get("irq20_progress") else "FAIL",
        "ssh_key_only": "PASS" if summary.get("all_ssh_primary") and summary.get("all_ssh_fresh") else "FAIL",
        "management_stability": "PASS" if summary.get("pass") else "FAIL",
        "cgi_execution": "PASS" if summary.get("all_http80_cgi_executed") and summary.get("all_http8080_closed") else "FAIL",
        "radio_fail_closed": "PASS" if summary.get("all_radio2g_fail_closed") and summary.get("all_radio5g_fail_closed") and summary.get("all_hostapd_absent") and summary.get("all_br0_absent") else "FAIL",
        "no_fatal_exception": "PASS" if not summary.get("fatal_dmesg_full") and uart_markers.get("fatal_absent") else "FAIL",
        "reboot_or_recovery": "PASS" if uart_markers.get("bootbase_prompt") and uart_markers.get("tftp_recovery_path") and uart_markers.get("bootm_handoff") else "FAIL",
    }
    status = "PASS" if summary["pass"] and all(value == "PASS" for value in checks_out.values()) else "FAIL"
    artifacts = [samples_path, summary_path, dmesg_before_path, dmesg_final_path, uart_attestation_path, uart_log]
    result = {
        "schema": "openmitrastar.ram-equivalence/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": PROFILE,
        "scope": SCOPE,
        "candidate_sha256": sha256(candidate),
        "status": status,
        "checks": checks_out,
        # Hash-bearing evidence is deliberately emitted only for a complete PASS.
        "evidence": evidence_entries(status, artifacts),
        "diagnostic_artifacts": ([] if status == "PASS" else [relative(path) for path in artifacts]),
        "summary": summary,
        "hardware_actions": "read-only runtime observation",
        "flash_actions": False,
        "secret_values_recorded": False,
    }
    write_json(args.output.resolve(), result)
    print(
        f"{PASS_MARKER_PREFIX}_{status} output={relative(args.output.resolve())} "
        f"failures={','.join(summary['fail_reasons']) or 'none'}"
    )
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
