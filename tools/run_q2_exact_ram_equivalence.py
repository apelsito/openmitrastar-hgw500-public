#!/usr/bin/env python3
"""Read-only exact-image RAM-equivalence gate for Q2.

The runner observes an already RAM-booted router.  It never opens UART, boots,
reboots, provisions secrets, starts radios or writes flash.  Execute mode
requires a newly captured UART log supplied explicitly for this Q2 boot.
"""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import re
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CANDIDATE_DIR = ROOT / "work/mission-state/f2-q2-integrated-flash-candidate"
DEFAULT_CANDIDATE = CANDIDATE_DIR / "openmitrastar-linux510-q2-integrated-webformat.bin"
DEFAULT_MANIFEST = CANDIDATE_DIR / "manifest.json"
DEFAULT_RAM_IMAGE = ROOT / "work/tftp/omvl/linux510-q2-parity-v1-LZMA-RAM-TEST-NO-FLASH.bin"
DEFAULT_SOURCE_MANIFEST = ROOT / "work/mission-state/q2-integrated-lzma-candidate/build/manifest.json"
DEFAULT_OUTPUT = CANDIDATE_DIR / "ram-equivalence.json"
EXPECTED_SHA256 = "cbe904ab7a807838fa12077fab924c79ce3c112a5ef40727cbaf9ec98f638cf1"
EXPECTED_BYTES = 4_157_772
RAM_BOOT_NAME = "linux510-q2-parity-v1-LZMA-RAM-TEST-NO-FLASH.bin"
DEFAULT_HOST = "192.168.1.90"
MIN_DURATION_S = 180
DEFAULT_MAX_UART_AGE_S = 3600
DEFAULT_MAX_BOOT_UPTIME_S = 3600
ACK = "OPENMITRASTAR_Q2_EXACT_RAM_EQUIVALENCE"
PROFILE = "Q2_PARITY_INTEGRATED"
SCOPE = "MANAGEMENT-BASELINE-PLUS-INTEGRATED-PAYLOADS"
RUNNER_SCHEMA = "openmitrastar.q2-exact-ram-equivalence-runner/v1"
RESULT_SCHEMA = "openmitrastar.ram-equivalence/v1"
PASS_PREFIX = "OM_Q2_EXACT_RAM_EQ"
EXPECTED_DEGRADED_SERVICES = ("S35-radio-modules", "S50-radio-ap")
REMOTE_HTTPS_PEM = "/run/openmitrastar/secrets/https.pem"

FATAL_RE = re.compile(
    r"Kernel panic|\bOops\b|BUG:|use-after-free|KASAN|nobody cared|"
    r"Unable to handle kernel|hard LOCKUP|soft lockup|watchdog.*reset|"
    r"descriptor.*error|DMA.*error|EV_TLB|MuC exception|forcing reboot",
    re.IGNORECASE,
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
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


def local_pem_valid(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size > 1024 * 1024:
        return False
    blob = path.read_bytes()
    return b"-----BEGIN CERTIFICATE-----" in blob and any(
        marker in blob
        for marker in (b"-----BEGIN PRIVATE KEY-----", b"-----BEGIN RSA PRIVATE KEY-----", b"-----BEGIN EC PRIVATE KEY-----")
    )


def uart_gate(path: Path, *, now_epoch: float | None = None, max_age_s: int = DEFAULT_MAX_UART_AGE_S) -> tuple[bool, dict[str, bool]]:
    now_epoch = time.time() if now_epoch is None else now_epoch
    text = path.read_bytes().replace(b"\x00", b"").decode("utf-8", "replace")
    age = now_epoch - path.stat().st_mtime
    markers = {
        "dynamic_log_fresh": -60 <= age <= max_age_s,
        "bootbase_prompt": "topaz>" in text,
        "tftp_recovery_path": "TFTP from server" in text,
        "candidate_tftp_name": f"Filename '{RAM_BOOT_NAME}'." in text,
        "candidate_byte_count": f"Bytes transferred = {EXPECTED_BYTES}" in text,
        "bootm_handoff": "bootm 0x83000000" in text,
        "linux_5_10": "Linux version 5.10.260-openmitrastar-radiohw" in text,
        "network_ready": "OMNETWORK_READY profile=oem-videobridge interface=eth0 ipv4=192.168.1.90" in text,
        "ssh_key_only_ready": "OMSSH_READY port=22 auth=ed25519-key-only" in text,
        # S44's wrapper result is the boot-time UART contract.  The 180-second
        # runtime samples independently execute HTTP 80 and getinfo 16667, so
        # requiring an internal daemon printf here would add no safety and is
        # vulnerable to init stdout routing.
        "http_getinfo_ready": "OMINIT_SERVICE_END name=S44-oem-web rc=0" in text,
        "radio_services_failed_closed": all(
            f"OMINIT_SERVICE_END name={service} rc=1" in text for service in EXPECTED_DEGRADED_SERVICES
        ),
        "fatal_absent": FATAL_RE.search(text) is None,
    }
    return all(markers.values()), markers


def static_checks(candidate: Path, manifest_path: Path, ram_image: Path, source_manifest_path: Path) -> dict[str, bool]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = json.loads(source_manifest_path.read_text(encoding="utf-8"))
    candidate_sha = sha256(candidate)
    ram_sha = sha256(ram_image)
    capabilities = manifest.get("capabilities", {})
    security = manifest.get("security", {})
    return {
        "candidate_sha256_pinned": candidate_sha == EXPECTED_SHA256,
        "candidate_size_pinned": candidate.stat().st_size == EXPECTED_BYTES,
        "ram_image_sha256_pinned": ram_sha == EXPECTED_SHA256,
        "ram_image_size_pinned": ram_image.stat().st_size == EXPECTED_BYTES,
        "candidate_ram_byte_identical": candidate_sha == ram_sha and candidate.stat().st_size == ram_image.stat().st_size,
        "q2_manifest_identity": manifest.get("profile") == PROFILE and manifest.get("scope") == SCOPE,
        "q2_manifest_candidate": manifest.get("artifact", {}).get("sha256") == candidate_sha
        and manifest.get("artifact", {}).get("size") == candidate.stat().st_size,
        "q2_manifest_separate_lane": manifest_path.parent.resolve() == CANDIDATE_DIR.resolve(),
        "q2_candidate_eligible_not_ready": manifest.get("candidate_eligible") is True and manifest.get("flash_ready") is False,
        "q2_prior_attestations_not_copied": manifest.get("attestations_copied_from_prior_candidates") is False,
        "q2_source_manifest_pinned": sha256(source_manifest_path) == manifest.get("components", {}).get("q2_source_manifest_sha256"),
        "q2_source_hardware_pending": source.get("candidate_eligible") is False
        and source.get("flash_supported") is False and source.get("hardware_actions") is False,
        "http80_declared": capabilities.get("http_80") is True,
        "getinfo16667_declared": capabilities.get("getinfo_16667") is True,
        "https_external_pem_only": capabilities.get("https_443_optional_external_pem") is True
        and security.get("https_pem_bundled") is False,
        "radio_baseline_fail_closed": capabilities.get("w3_autostart") is False
        and security.get("psk_bundled") is False,
        "ioss_reset_forbidden": security.get("ioss_reset_pulse_forbidden") is True,
    }


def run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout, check=False)


def local_ping(host: str) -> bool:
    return run(["ping.exe", "-n", "2", "-w", "1000", host], timeout=8).returncode == 0


def ssh(host: str, command: str, timeout: int = 25) -> subprocess.CompletedProcess[str]:
    return run(
        [sys.executable, str(ROOT / "tools/ramssh_exec.py"), command, "--host", host, "--timeout", str(timeout)],
        timeout=timeout + 15,
    )


def http80_executes(host: str) -> bool:
    conn = http.client.HTTPConnection(host, 80, timeout=5)
    try:
        conn.request("GET", "/index.cgi", headers={"Connection": "close"})
        response = conn.getresponse()
        body = response.read(128 * 1024).decode("utf-8", "replace")
        return (
            response.status == 200
            and "text/html" in response.getheader("Content-Type", "").lower()
            and "OpenMitraStar" in body
            and "Acceso" in body
            and "#!/bin/ash" not in body
            and "OM_WEB_DISPATCHER" not in body
        )
    except OSError:
        return False
    finally:
        conn.close()


def getinfo16667_executes(host: str) -> bool:
    conn = http.client.HTTPConnection(host, 16667, timeout=5)
    try:
        conn.request("GET", "/getinfo.cgi", headers={"Connection": "close"})
        response = conn.getresponse()
        body = response.read(64 * 1024).decode("utf-8", "replace")
        value = json.loads(body)
        data = value.get("resultData", {})
        return (
            response.status == 200
            and "application/json" in response.getheader("Content-Type", "").lower()
            and value.get("resultCode") == 0
            and "HGW-500BNA-QCv2" in str(data.get("model", ""))
            and value.get("resultText") == "Operation successful"
        )
    except (OSError, ValueError, json.JSONDecodeError):
        return False
    finally:
        conn.close()


def https443_executes(host: str) -> bool:
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    conn = http.client.HTTPSConnection(host, 443, timeout=5, context=context)
    try:
        conn.request("GET", "/index.cgi", headers={"Connection": "close"})
        response = conn.getresponse()
        body = response.read(128 * 1024).decode("utf-8", "replace")
        return response.status == 200 and "OpenMitraStar" in body and "#!/bin/ash" not in body
    except (OSError, ssl.SSLError):
        return False
    finally:
        conn.close()


def port_refused(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=3):
            return False
    except ConnectionRefusedError:
        return True
    except OSError as exc:
        return getattr(exc, "winerror", None) == 10061 or getattr(exc, "errno", None) in {61, 111, 10061}


def remote_snapshot_command(expected_pem_sha256: str | None) -> str:
    expected_count = len(EXPECTED_DEGRADED_SERVICES)
    expected_terms = " ".join(
        f'$1 == "{service}" && $2 == "1" {{ seen_{index}++ }}'
        for index, service in enumerate(EXPECTED_DEGRADED_SERVICES)
    )
    expected_final = " && ".join(f"seen_{index} == 1" for index, _ in enumerate(EXPECTED_DEGRADED_SERVICES))
    expected_pem = expected_pem_sha256 or "NONE"
    script = r'''set -u
devstat() { awk -v dev="$1" '$1 == dev":" {print $2, $3, $4, $10, $11, $12}' /proc/net/dev; }
irqsum() { awk -v irq="$1:" '$1 == irq {s=0; for(i=2;i<=NF;i++){if($i ~ /^[0-9]+$/) s+=$i; else break}; print s; found=1} END{if(!found) print -1}' /proc/interrupts; }
closed_if() { if [ ! -e "/sys/class/net/$1" ]; then echo 1; else state=$(cat "/sys/class/net/$1/operstate" 2>/dev/null || echo unknown); [ "$state" = down ] && echo 1 || echo 0; fi; }
pid_alive() { file=$1; pid=$(cat "$file" 2>/dev/null || true); case "$pid" in ''|*[!0-9]*) echo 0;; *) kill -0 "$pid" 2>/dev/null && echo 1 || echo 0;; esac; }
set -- $(devstat eth0); echo ETH0_RX_BYTES=${1:--1}; echo ETH0_RX_PACKETS=${2:--1}; echo ETH0_RX_ERRORS=${3:--1}; echo ETH0_TX_BYTES=${4:--1}; echo ETH0_TX_PACKETS=${5:--1}; echo ETH0_TX_ERRORS=${6:--1}
echo UPTIME_S=$(cut -d. -f1 /proc/uptime)
echo BOOT_ID=$(cat /proc/sys/kernel/random/boot_id 2>/dev/null || echo unavailable)
echo IRQ20=$(irqsum 20)
echo HTTP_PID_ALIVE=$(pid_alive /run/openmitrastar/web/mini_httpd.pid)
echo GETINFO_PID_ALIVE=$(pid_alive /run/openmitrastar/web/mini_httpd-getinfo.pid)
echo HTTPS_PID_ALIVE=$(pid_alive /run/openmitrastar/web/mini_httpd-https.pid)
[ -f /run/openmitrastar/web/https.ready ] && echo HTTPS_READY=1 || echo HTTPS_READY=0
[ -f __REMOTE_PEM__ ] && echo HTTPS_PEM_PRESENT=1 || echo HTTPS_PEM_PRESENT=0
pem_safe=0
if [ -f __REMOTE_PEM__ ]; then
  metadata=$(ls -ln __REMOTE_PEM__ 2>/dev/null || true)
  mode=$(printf '%s\n' "$metadata" | awk '{print $1}'); owner=$(printf '%s\n' "$metadata" | awk '{print $3}')
  observed=$(sha256sum __REMOTE_PEM__ 2>/dev/null | cut -d ' ' -f 1)
  [ "$mode" = -rw------- ] && [ "$owner" = 0 ] && [ "__EXPECTED_PEM__" != NONE ] && [ "$observed" = "__EXPECTED_PEM__" ] && pem_safe=1
fi
echo HTTPS_PEM_SAFE=$pem_safe
echo WLAN0_CLOSED=$(closed_if wlan0)
echo WIFI0_CLOSED=$(closed_if wifi0)
hostapd=0; for p in /proc/[0-9]*/comm; do [ -r "$p" ] || continue; grep -q '^hostapd' "$p" 2>/dev/null && hostapd=1; done; [ "$hostapd" = 0 ] && echo HOSTAPD_ABSENT=1 || echo HOSTAPD_ABSENT=0
test ! -e /sys/class/net/br0 && echo BR0_ABSENT=1 || echo BR0_ABSENT=0
[ "$(awk '__EXPECTED_TERMS__ NF {n++} END {print (n == __EXPECTED_COUNT__ && __EXPECTED_FINAL__) ? 1 : 0}' /run/openmitrastar/degraded 2>/dev/null)" = 1 ] && echo ONLY_RADIO_DEGRADED=1 || echo ONLY_RADIO_DEGRADED=0
'''
    return (
        script.replace("__REMOTE_PEM__", REMOTE_HTTPS_PEM)
        .replace("__EXPECTED_PEM__", expected_pem)
        .replace("__EXPECTED_TERMS__", expected_terms)
        .replace("__EXPECTED_COUNT__", str(expected_count))
        .replace("__EXPECTED_FINAL__", expected_final)
    )


def collect_sample(host: str, elapsed: float, expected_pem_sha256: str | None) -> dict[str, Any]:
    expect_https = expected_pem_sha256 is not None
    sample: dict[str, Any] = {
        "elapsed_s": round(elapsed, 3),
        "local_ping": local_ping(host),
        "ssh_primary": False,
        "ssh_fresh": False,
        "http80_cgi_executed": False,
        "getinfo16667_executed": False,
        "https443_executed": False,
        "https443_closed": False,
    }
    primary = ssh(host, remote_snapshot_command(expected_pem_sha256))
    sample["ssh_primary"] = primary.returncode == 0
    if primary.returncode == 0:
        values = parse_kv(primary.stdout)
        integer_mapping = {
            "UPTIME_S": "uptime_s", "IRQ20": "irq20",
            "ETH0_RX_BYTES": "eth0_rx_bytes", "ETH0_RX_PACKETS": "eth0_rx_packets",
            "ETH0_RX_ERRORS": "eth0_rx_errors", "ETH0_TX_BYTES": "eth0_tx_bytes",
            "ETH0_TX_PACKETS": "eth0_tx_packets", "ETH0_TX_ERRORS": "eth0_tx_errors",
            "HTTP_PID_ALIVE": "http_pid_alive", "GETINFO_PID_ALIVE": "getinfo_pid_alive",
            "HTTPS_PID_ALIVE": "https_pid_alive", "HTTPS_READY": "https_ready",
            "HTTPS_PEM_PRESENT": "https_pem_present", "HTTPS_PEM_SAFE": "https_pem_safe",
            "WLAN0_CLOSED": "wlan0_closed", "WIFI0_CLOSED": "wifi0_closed",
            "HOSTAPD_ABSENT": "hostapd_absent", "BR0_ABSENT": "br0_absent",
            "ONLY_RADIO_DEGRADED": "only_radio_degraded",
        }
        for source, target in integer_mapping.items():
            try:
                sample[target] = int(values.get(source, "-1"))
            except ValueError:
                sample[target] = -1
        sample["boot_id"] = values.get("BOOT_ID", "")
    sample["ssh_fresh"] = ssh(host, "true", timeout=10).returncode == 0
    sample["http80_cgi_executed"] = http80_executes(host)
    sample["getinfo16667_executed"] = getinfo16667_executes(host)
    if expect_https:
        sample["https443_executed"] = https443_executes(host)
    else:
        sample["https443_closed"] = port_refused(host, 443)
    return sample


def evaluate_samples(
    samples: list[dict[str, Any]], duration_observed: float, duration_required: int,
    expect_https: bool, max_boot_uptime_s: int,
) -> tuple[dict[str, Any], list[str]]:
    summary: dict[str, Any] = {
        "duration_required_s": duration_required,
        "duration_observed_s": round(duration_observed, 3),
        "sample_count": len(samples),
        "all_local_ping": bool(samples) and all(s.get("local_ping") is True for s in samples),
        "all_ssh_primary": bool(samples) and all(s.get("ssh_primary") is True for s in samples),
        "all_ssh_fresh": bool(samples) and all(s.get("ssh_fresh") is True for s in samples),
        "all_http80": bool(samples) and all(s.get("http80_cgi_executed") is True for s in samples),
        "all_getinfo16667": bool(samples) and all(s.get("getinfo16667_executed") is True for s in samples),
        "all_web_pids": bool(samples) and all(s.get("http_pid_alive") == 1 and s.get("getinfo_pid_alive") == 1 for s in samples),
        "all_radio_fail_closed": bool(samples) and all(
            s.get("wlan0_closed") == 1 and s.get("wifi0_closed") == 1
            and s.get("hostapd_absent") == 1 and s.get("br0_absent") == 1
            and s.get("only_radio_degraded") == 1 for s in samples
        ),
        "all_eth0_error_free": bool(samples) and all(s.get("eth0_rx_errors") == 0 and s.get("eth0_tx_errors") == 0 for s in samples),
        "https_policy": "external-pem-required" if expect_https else "closed-without-external-pem",
    }
    boot_ids = {str(s.get("boot_id", "")) for s in samples}
    summary["single_boot_id"] = len(boot_ids) == 1 and "" not in boot_ids and "unavailable" not in boot_ids
    summary["https_policy_pass"] = bool(samples) and (
        all(
            s.get("https443_executed") is True and s.get("https_pid_alive") == 1
            and s.get("https_ready") == 1 and s.get("https_pem_present") == 1
            and s.get("https_pem_safe") == 1 for s in samples
        ) if expect_https else all(
            s.get("https443_closed") is True and s.get("https_pid_alive") == 0
            and s.get("https_ready") == 0 and s.get("https_pem_present") == 0 for s in samples
        )
    )
    for key in ("uptime_s", "eth0_rx_bytes", "eth0_rx_packets", "eth0_tx_bytes", "eth0_tx_packets", "irq20"):
        series = integer_series(samples, key)
        summary[f"{key}_start"] = series[0] if series else None
        summary[f"{key}_end"] = series[-1] if series else None
        summary[f"{key}_progress"] = overall_progress(series)
    summary["boot_uptime_within_limit"] = isinstance(summary["uptime_s_start"], int) and summary["uptime_s_start"] <= max_boot_uptime_s

    checks = [
        (len(samples) >= 2, "insufficient_samples"),
        (duration_observed >= duration_required, "duration_short"),
        (summary["all_local_ping"], "management_icmp_failure"),
        (summary["all_ssh_primary"], "ssh_primary_failure"),
        (summary["all_ssh_fresh"], "ssh_fresh_failure"),
        (summary["all_http80"], "http80_failure"),
        (summary["all_getinfo16667"], "getinfo16667_failure"),
        (summary["all_web_pids"], "web_daemon_failure"),
        (summary["https_policy_pass"], "https_external_pem_policy_failure"),
        (summary["all_radio_fail_closed"], "radio_baseline_not_fail_closed"),
        (summary["all_eth0_error_free"], "eth0_errors_nonzero"),
        (summary["single_boot_id"], "boot_id_changed_or_unavailable"),
        (summary["boot_uptime_within_limit"], "boot_too_old_for_dynamic_q2_gate"),
    ]
    for key in ("uptime_s", "eth0_rx_bytes", "eth0_rx_packets", "eth0_tx_bytes", "eth0_tx_packets", "irq20"):
        checks.append((bool(summary[f"{key}_progress"]), f"{key}_no_progress"))
    failures = [reason for passed, reason in checks if not passed]
    summary["fail_reasons"] = failures
    summary["pass"] = not failures
    return summary, failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate", type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--ram-image", type=Path, default=DEFAULT_RAM_IMAGE)
    parser.add_argument("--source-manifest", type=Path, default=DEFAULT_SOURCE_MANIFEST)
    parser.add_argument("--uart-log", type=Path, help="new UART capture for this exact Q2 boot; mandatory with --execute")
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--duration", type=int, default=MIN_DURATION_S)
    parser.add_argument("--interval", type=int, default=10)
    parser.add_argument("--max-uart-age", type=int, default=DEFAULT_MAX_UART_AGE_S)
    parser.add_argument("--max-boot-uptime", type=int, default=DEFAULT_MAX_BOOT_UPTIME_S)
    parser.add_argument("--external-https-pem", type=Path, help="PEM already provisioned at the fixed runtime path; never uploaded")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--ack", default="")
    args = parser.parse_args(argv)

    candidate = args.candidate.resolve()
    manifest = args.manifest.resolve()
    ram_image = args.ram_image.resolve()
    source_manifest = args.source_manifest.resolve()
    missing = [str(path) for path in (candidate, manifest, ram_image, source_manifest) if not path.is_file()]
    if missing:
        raise SystemExit("missing required local input: " + ", ".join(missing))
    checks = static_checks(candidate, manifest, ram_image, source_manifest)
    external_pem = args.external_https_pem.resolve() if args.external_https_pem else None
    if external_pem is not None and not local_pem_valid(external_pem):
        raise SystemExit("external HTTPS PEM is missing or lacks certificate/private-key blocks")
    plan = {
        "schema": RUNNER_SCHEMA,
        "mode": "EXECUTE_READ_ONLY_OBSERVATION" if args.execute else "DRY_RUN_LOCAL_ONLY",
        "profile": PROFILE,
        "scope": SCOPE,
        "candidate": relative(candidate),
        "candidate_sha256": sha256(candidate),
        "candidate_bytes": candidate.stat().st_size,
        "ram_image": relative(ram_image),
        "uart_log": relative(args.uart_log.resolve()) if args.uart_log else None,
        "uart_log_must_be_dynamic": True,
        "duration_s": args.duration,
        "interval_s": args.interval,
        "host": args.host,
        "https_external_pem_provided": external_pem is not None,
        "https_policy": "require-safe-external-runtime-pem-and-443" if external_pem else "require-443-closed-and-no-runtime-pem",
        "runtime_checks": [
            "same exact Q2 bytes in candidate and RAM TFTP image",
            "explicit fresh UART log names and transfers this exact Q2 image",
            "UART epoch binds to the single observed boot_id and uptime",
            "at least 180 seconds ICMP plus two key-only SSH operations per sample",
            "HTTP 80 executes index.cgi and getinfo 16667 returns OEM-compatible JSON",
            "HTTPS 443 is closed unless an external PEM is explicitly supplied and safely installed in RAM",
            "eth0 RX/TX and IRQ20 progress without errors",
            "2.4/5 GHz interfaces, hostapd and br0 remain fail-closed",
            "no fatal UART or dmesg marker",
        ],
        "static_checks": checks,
        "hardware_actions": False if not args.execute else "read-only runtime observation",
        "uart_opened_by_runner": False,
        "flash_actions": False,
        "secrets_logged": False,
    }
    print(json.dumps(plan, indent=2, sort_keys=True))
    if not all(checks.values()):
        print(f"{PASS_PREFIX}_STATIC_FAIL", file=sys.stderr)
        return 2
    if not args.execute:
        print(f"{PASS_PREFIX}_DRY_RUN_PASS=1 runtime_pending=1 uart_required_for_execute=1")
        return 0

    if args.ack != ACK:
        raise SystemExit(f"--execute requires --ack {ACK}")
    if args.host != DEFAULT_HOST:
        raise SystemExit(f"execute mode is pinned to --host {DEFAULT_HOST}")
    if args.uart_log is None:
        raise SystemExit("--execute requires an explicit --uart-log captured for this Q2 boot")
    uart_log = args.uart_log.resolve()
    if not uart_log.is_file():
        raise SystemExit(f"missing Q2 UART log: {uart_log}")
    if args.duration < MIN_DURATION_S or not 5 <= args.interval <= 30:
        raise SystemExit(f"execute mode requires duration>={MIN_DURATION_S} and 5<=interval<=30")
    if args.max_uart_age < MIN_DURATION_S or args.max_boot_uptime < MIN_DURATION_S:
        raise SystemExit("dynamic boot limits must be at least the 180-second soak")
    uart_ok, uart_markers = uart_gate(uart_log, max_age_s=args.max_uart_age)
    if not uart_ok:
        raise SystemExit("explicit Q2 UART log failed exact-image/freshness markers: " + json.dumps(uart_markers, sort_keys=True))

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evidence_dir = args.evidence_dir.resolve() if args.evidence_dir else CANDIDATE_DIR / f"ram-equivalence-{stamp}"
    evidence_dir.mkdir(parents=True, exist_ok=False)
    samples_path = evidence_dir / "samples.jsonl"
    summary_path = evidence_dir / "summary.json"
    dmesg_before_path = evidence_dir / "dmesg-before.log"
    dmesg_final_path = evidence_dir / "dmesg-final.log"
    uart_attestation_path = evidence_dir / "uart-attestation.json"
    write_json(uart_attestation_path, {
        "schema": "openmitrastar.q2-dynamic-uart-attestation/v1",
        "path": relative(uart_log), "sha256": sha256(uart_log), "markers": uart_markers,
        "source": "explicit-current-run-input", "copied_from_prior_candidate": False,
    })

    dmesg_before = ssh(args.host, "dmesg", timeout=30)
    if dmesg_before.returncode != 0:
        raise SystemExit("cannot capture initial dmesg over key-only SSH")
    dmesg_before_path.write_text(dmesg_before.stdout, encoding="utf-8")
    expected_pem_sha = sha256(external_pem) if external_pem else None
    start = time.monotonic()
    wall_start = time.time()
    samples: list[dict[str, Any]] = []
    while True:
        elapsed = time.monotonic() - start
        sample = collect_sample(args.host, elapsed, expected_pem_sha)
        samples.append(sample)
        with samples_path.open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(sample, sort_keys=True) + "\n")
        print(
            "OM_Q2_SAMPLE "
            f"n={len(samples)} t={sample['elapsed_s']} ping={int(bool(sample.get('local_ping')))} "
            f"ssh={int(bool(sample.get('ssh_primary')))}+{int(bool(sample.get('ssh_fresh')))} "
            f"http80={int(bool(sample.get('http80_cgi_executed')))} "
            f"getinfo16667={int(bool(sample.get('getinfo16667_executed')))} "
            f"https={'ready' if sample.get('https443_executed') else ('closed' if sample.get('https443_closed') else 'fail')} "
            f"radio_closed={sample.get('wlan0_closed', -1)}+{sample.get('wifi0_closed', -1)}",
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
    summary, failures = evaluate_samples(
        samples, duration_observed, args.duration, external_pem is not None, args.max_boot_uptime
    )
    first_uptime = summary.get("uptime_s_start")
    boot_epoch_estimate = wall_start - first_uptime if isinstance(first_uptime, int) else None
    summary["uart_mtime_after_boot_epoch"] = bool(
        boot_epoch_estimate is not None and uart_log.stat().st_mtime >= boot_epoch_estimate - 60
        and uart_log.stat().st_mtime <= time.time() + 60
    )
    summary["uart_gate"] = uart_ok
    summary["fatal_dmesg_full"] = bool(FATAL_RE.search(final_text))
    if not summary["uart_mtime_after_boot_epoch"]:
        failures.append("uart_log_not_bound_to_observed_boot_epoch")
    if dmesg_final.returncode != 0:
        failures.append("final_dmesg_fetch_failed")
    if summary["fatal_dmesg_full"]:
        failures.append("fatal_dmesg_marker")
    summary["fail_reasons"] = sorted(set(failures))
    summary["pass"] = not summary["fail_reasons"]
    write_json(summary_path, summary)

    checks_out = {
        "boot": "PASS" if uart_ok and summary["uart_mtime_after_boot_epoch"] and summary["single_boot_id"] else "FAIL",
        "product_rootfs": "PASS" if summary["all_web_pids"] and summary["all_http80"] and summary["all_getinfo16667"] else "FAIL",
        "ethernet": "PASS" if summary["all_local_ping"] and summary["eth0_rx_packets_progress"] and summary["eth0_tx_packets_progress"] and summary["irq20_progress"] else "FAIL",
        "ssh_key_only": "PASS" if summary["all_ssh_primary"] and summary["all_ssh_fresh"] else "FAIL",
        "management_stability": "PASS" if summary["pass"] else "FAIL",
        "http80": "PASS" if summary["all_http80"] else "FAIL",
        "getinfo16667": "PASS" if summary["all_getinfo16667"] else "FAIL",
        "https_external_pem_policy": "PASS" if summary["https_policy_pass"] else "FAIL",
        "radio_fail_closed": "PASS" if summary["all_radio_fail_closed"] else "FAIL",
        "no_fatal_exception": "PASS" if not summary["fatal_dmesg_full"] and uart_markers["fatal_absent"] else "FAIL",
        "reboot_or_recovery": "PASS" if uart_markers["bootbase_prompt"] and uart_markers["tftp_recovery_path"] and uart_markers["bootm_handoff"] else "FAIL",
    }
    status = "PASS" if summary["pass"] and all(value == "PASS" for value in checks_out.values()) else "FAIL"
    artifacts = [samples_path, summary_path, dmesg_before_path, dmesg_final_path, uart_attestation_path, uart_log]
    result = {
        "schema": RESULT_SCHEMA,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "profile": PROFILE,
        "scope": SCOPE,
        "candidate_sha256": sha256(candidate),
        "status": status,
        "checks": checks_out,
        "evidence": evidence_entries(status, artifacts),
        "diagnostic_artifacts": [] if status == "PASS" else [relative(path) for path in artifacts],
        "summary": summary,
        "uart_attestation_origin": "new-q2-exact-image-boot",
        "prior_candidate_attestation_reused": False,
        "https_external_pem_provided": external_pem is not None,
        "hardware_actions": "read-only runtime observation",
        "uart_opened_by_runner": False,
        "flash_actions": False,
        "secret_values_recorded": False,
    }
    write_json(args.output.resolve(), result)
    print(f"{PASS_PREFIX}_{status} output={relative(args.output.resolve())} failures={','.join(summary['fail_reasons']) or 'none'}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
