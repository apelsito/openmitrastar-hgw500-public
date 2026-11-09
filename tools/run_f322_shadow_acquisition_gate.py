"""F322 read-only unarmed baseline; temporal arming is explicitly unavailable.

Default: file-only plan. --execute --baseline-only takes two bounded pinned-SSH
observations and writes sanitized evidence. No code path writes shadow_arm,
changes RF configuration, loads a module, reboots, or flashes the device.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time

import f322_shadow_gate as gate


def observation_script(files: dict) -> bytes:
    if len(files) != 9:
        raise ValueError("exact-nine-file-contract-required")
    # File names originate in the hash-pinned inventory, never user shell input.
    names = " ".join(shlex.quote(name) for name in sorted(files))
    snapshot_keys = "|".join(sorted(set(gate.SNAPSHOT_FIXED) | set(gate.SNAPSHOT_VARIABLE)))
    script = r'''set -eu
export LC_ALL=C
command -v timeout >/dev/null 2>&1 || exit 50
printf 'OMF322_IDENTITY_BEGIN\n'
printf 'version='; sed -n 's/^OPENMITRASTAR_PRODUCT_VERSION=//p' /etc/openmitrastar/release
printf 'build='; sed -n 's/^OPENMITRASTAR_BUILD_ID=//p' /etc/openmitrastar/release
printf 'kernel='; uname -r
printf 'boot_id='; cat /proc/sys/kernel/random/boot_id
kernel_log=$(dmesg) || exit 51
fatal=$(printf '%s\n' "$kernel_log" | grep -Eic 'Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|VFS: Unable to mount root|MuC:.*exception|MuC has halted|QMAC.*fatal|DMA.*fatal|thermal.*fatal|Semaphore hang detected' || true)
printf 'fatal_count=%s\n' "$fatal"
if [ "$(cat /run/openmitrastar/boot-state)" = ready ]; then printf 'boot_ready=1\n'; else printf 'boot_ready=0\n'; fi
radio2=$(timeout 3 /usr/sbin/hostapd_cli -p /run/openmitrastar/radio2g/ctrl -i wlan0 status 2>/dev/null) || exit 52
if [ "$(printf '%s\n' "$radio2" | sed -n 's/^state=//p')" = ENABLED ]; then printf 'radio2_ready=1\n'; else printf 'radio2_ready=0\n'; fi
if [ "$(cat /run/openmitrastar/radio5g/state)" = ready ] && [ "$(cat /run/openmitrastar/radio5g/ready)" = ready ]; then printf 'radio5_ready=1\n'; else printf 'radio5_ready=0\n'; fi
if [ -e /sys/class/net/br0/brif/eth0 ] && [ -e /sys/class/net/br0/brif/wlan0 ] && [ -e /sys/class/net/br0/brif/wifi0 ]; then printf 'bridge_ready=1\n'; else printf 'bridge_ready=0\n'; fi
printf 'OMF322_IDENTITY_END\nOMF322_FILES_BEGIN\n'
sha256sum __FILES__
printf 'OMF322_FILES_END\nOMF322_STATUS_BEFORE_BEGIN\n'
cat /proc/openmitrastar_radar_f315/status
printf 'OMF322_STATUS_BEFORE_END\nOMF322_SNAPSHOT_BEGIN\n'
awk -F= '$1 ~ /^(__SNAPSHOT_KEYS__)$/ { print }' /proc/openmitrastar_radar_f315/snapshot
printf 'OMF322_SNAPSHOT_END\nOMF322_RUNTIME_BEGIN\n'
timeout 15 /usr/sbin/om-dfs-status status
printf 'OMF322_RUNTIME_END\nOMF322_STATUS_AFTER_BEGIN\n'
cat /proc/openmitrastar_radar_f315/status
printf 'OMF322_STATUS_AFTER_END\n'
'''
    return script.replace("__FILES__", names).replace("__SNAPSHOT_KEYS__", snapshot_keys).encode("ascii")


def ssh_observation(files: dict, start: float, runner=subprocess.run, monotonic=time.monotonic) -> dict:
    known_hosts = gate.DEVICE / "known_hosts.f322"
    gate.pinned(known_hosts, gate.KNOWN_HOSTS_SHA)
    ssh = Path.home().drive + r"\Windows\System32\OpenSSH\ssh.exe"
    args = [ssh, "-i", str(Path.home() / ".ssh/id_ed25519"), "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
            "-o", "StrictHostKeyChecking=yes", "-o", "UserKnownHostsFile=" + str(known_hosts),
            "-o", "ConnectTimeout=5", "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=2",
            "-o", "LogLevel=ERROR", "root@" + gate.HOST, "sh", "-s"]
    proc = runner(args, input=observation_script(files), capture_output=True, timeout=25, check=False)
    # Neither stderr nor an invalid stdout is printed or written: either may
    # contain unrelated runtime data after a failed command.
    if proc.returncode != 0 or proc.stderr.strip():
        raise ValueError("pinned-SSH-observation-failed")
    return gate.parse_observation(proc.stdout.decode("utf-8", "strict"), files, monotonic() - start)


def baseline(files: dict, observe=ssh_observation, monotonic=time.monotonic, sleep=time.sleep) -> tuple[dict, list[dict]]:
    start = monotonic()
    rows = [observe(files, start)]
    # Inspect the first sample before taking another. There is no arming or
    # cleanup mutation when a different installation or armed provider appears.
    gate.validate_observation(rows[0])
    for status in (rows[0]["status_before"], rows[0]["status_after"]):
        gate.require(status["shadow_arm"] == status["configured"] == status["polling"] == 0,
                     "baseline-not-pristine-unarmed")
    sleep(1)
    rows.append(observe(files, start))
    return gate.validate_baseline(rows), rows


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--baseline-only", action="store_true")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--ack", default="")
    parser.add_argument("--installation-result", type=Path)
    parser.add_argument("--installation-result-sha256", default="")
    parser.add_argument("--duration-seconds", type=int, choices=(60,), default=60)
    parser.add_argument("--interval-seconds", type=int, choices=(2,), default=2)
    args = parser.parse_args(argv)
    files = gate.sealed_inputs()
    plan = {"schema": "openmitrastar.f322-shadow-gate/v1", "candidate_sha256": gate.CANDIDATE_SHA,
        "target_host": gate.HOST, "expected_version": gate.VERSION,
        "status": "PASS_OFFLINE_F322_UNARMED_GATE_PLAN", "hardware_actions_performed": False,
        "acquisition_armed": False, "shadow_arm_writes": 0, "radio_mutation": False, "flash": False,
        "temporal_acquisition": gate.BLOCKER, "blocker_reason": gate.BLOCKER_REASON,
        "baseline_supported": True, "duration_seconds_planned": 60, "interval_seconds_planned": 2,
        "future_installation_prerequisite": "PASS_F322_BOOT_PLATFORM_UI_UNARMED bound by path and SHA256",
        "future_arm_ack": gate.ACK, "installed_files_expected": files, "release_eligible": False}
    if not args.execute:
        print(json.dumps(plan, indent=2))
        return 0
    # This prohibition is unconditional, including when an ACK or installation
    # PASS is supplied. There is deliberately no unsafe override switch.
    if not args.baseline_only:
        print(json.dumps({**plan, "status": gate.BLOCKER}, indent=2))
        return 2
    if args.output_dir is None:
        parser.error("baseline execution requires a new evidence directory")
    out = args.output_dir.resolve()
    gate.require(not out.is_relative_to(gate.DEVICE.resolve()), "output-cannot-modify-sealed-candidate")
    out.mkdir(parents=True, exist_ok=False)
    report = {**plan, "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "FAIL_F322_BASELINE_UNARMED", "hardware_actions_performed": False,
        "device_read_performed": True, "ssh_host_key_pinned": True,
        "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "validator_sha256": hashlib.sha256(Path(gate.__file__).read_bytes()).hexdigest()}
    try:
        checks, rows = baseline(files)
        report.update(checks)
        # Only sanitized, typed fields survive parse_observation.
        with (out / "observations.json").open("x", encoding="ascii") as stream:
            stream.write(json.dumps(rows, indent=2) + "\n")
        report["observations_sha256"] = hashlib.sha256((out / "observations.json").read_bytes()).hexdigest()
    except (OSError, ValueError, KeyError, TypeError, UnicodeError, subprocess.SubprocessError):
        report["error"] = "baseline-read-or-invariant-failed; no runtime mutation or retry performed"
    with (out / "result.json").open("x", encoding="ascii") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(json.dumps({key: report[key] for key in ("status", "acquisition_armed", "shadow_arm_writes", "radio_mutation", "flash", "temporal_acquisition")}, indent=2))
    return 0 if report["status"] == "PASS_F322_BASELINE_UNARMED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
