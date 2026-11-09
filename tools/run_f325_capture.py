"""One F325 capture window. Caller must hold the reviewed physical lease.

Stops software sampling only. Full F321 restoration is the parent campaign's
mandatory next phase, even if this process fails. No RF radar PASS is produced.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import time

import f325_execution_contract as contract


def ssh(script: str) -> str:
    known = Path(contract.F325["directory"]) / contract.F325["known_hosts"]
    args = [r"C:\Windows\System32\OpenSSH\ssh.exe", "-i", str(Path.home() / ".ssh/id_ed25519"),
            "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
            "-o", "UserKnownHostsFile=" + str(known), "-o", "ConnectTimeout=5",
            "-o", "ServerAliveInterval=2", "-o", "ServerAliveCountMax=2", "-o", "LogLevel=ERROR",
            "root@192.168.1.90", "sh", "-s"]
    prefix = "set -eu\ngrep -Fqx 'OPENMITRASTAR_PRODUCT_VERSION=" + contract.F325["version"] + "' /etc/openmitrastar/release\n"
    proc = subprocess.run(args, input=(prefix + script).encode(), capture_output=True, timeout=12, check=False)
    if proc.returncode or proc.stderr.strip():
        raise ValueError("bounded pinned SSH command failed")
    return proc.stdout.decode("utf-8", "strict")


def parse_radio_profile(region_output: str, mode_output: str, wireless_output: str) -> dict:
    """Validate the sole capture profile without returning private WEXT output."""
    values = []
    for output, getter in ((region_output, "get_region"), (mode_output, "get_mode")):
        match = re.fullmatch(rf"(?:wifi0[ \t]+)?{getter}[ \t]*:[ \t]*(\S+)", output.strip())
        if match is None:
            raise ValueError("missing, duplicate or invalid radio getter")
        values.append(match.group(1))
    # Count every label, including malformed duplicates, but accept the value
    # only in its WEXT field position. An ESSID must not supply a fake frequency.
    labels = re.findall(r"\bFrequency[ \t]*:", wireless_output)
    frequencies = re.findall(
        r"^[ \t]*(?:Mode:[^\s]+[ \t]+)?Frequency[ \t]*:[ \t]*(\S+)[ \t]+(\S+)",
        wireless_output, re.MULTILINE,
    )
    if values != ["21317", "11ac80Edge+"] or len(labels) != 1 or frequencies != [("5.18", "GHz")]:
        raise ValueError("actual radio must be ES channel 36 / 80 MHz")
    return {"region": "ES", "current_channel": 36, "bandwidth_mhz": 80}


def observe() -> dict:
    text = ssh("printf 'boot_id='; cat /proc/sys/kernel/random/boot_id\n"
               "cat /proc/openmitrastar_radar_f315/status\n"
               "printf 'FATAL_COUNT='; dmesg | grep -Eic 'MuC:.*exception|MuC has halted|Kernel panic|Oops:|BUG:|EV_TLB|EV_ProtV|Misaligned Access' || true\n")
    fields = {}
    for line in text.splitlines():
        if "=" not in line:
            raise ValueError("invalid provider field")
        key, value = line.split("=", 1)
        if key in fields:
            raise ValueError("duplicate provider field")
        fields[key] = value
    fixed = {"lifecycle": "f325-single-boot-reset-required", "channel": "36", "bandwidth": "80",
             "backend_ready": "0", "callback_invocations": "0", "dfs_enable": "0", "FATAL_COUNT": "0",
             "sample_window_ms": "20000", "hardware_restored": "0"}
    if any(fields.get(k) != v for k, v in fixed.items()) or not re.fullmatch(r"[0-9a-f-]{36}", fields.get("boot_id", "")):
        raise ValueError("provider identity, authority or health failed")
    numeric = ("once_phase", "hardware_dirty", "reboot_required", "shadow_arm", "configured", "polling",
               "poll_runs", "poll_empty", "poll_unstable", "mmio_writes", "config_attempts", "config_failures",
               "mmio_write_refusals", "map_failures", "stop_reason", "shadow_candidate_batches")
    if any(not re.fullmatch(r"[0-9]{1,16}", fields.get(k, "")) for k in numeric):
        raise ValueError("missing or invalid counter")
    return {"boot_id": fields["boot_id"], **{k: int(fields[k]) for k in numeric}}


def validate_deadline_stop(row: dict) -> None:
    if (row["once_phase"] != 2 or row["shadow_arm"] or row["polling"] or
            row["hardware_dirty"] != 1 or row["reboot_required"] != 1 or row["config_attempts"] != 1 or
            row["stop_reason"] != 2):
        raise ValueError("automatic deadline stop/dirty-state contract failed")


def validate_stopped(rows: list[dict]) -> dict:
    if len(rows) < 3 or len({r["boot_id"] for r in rows}) != 1:
        raise ValueError("capture continuity not proven")
    for row in rows:
        if any(row[k] for k in ("config_failures", "mmio_write_refusals", "map_failures")):
            raise ValueError("acquisition error")
    last, previous = rows[-1], rows[-2]
    for row in (previous, last):
        validate_deadline_stop(row)
    if not last["poll_runs"] or last["poll_runs"] != previous["poll_runs"] or last["mmio_writes"] != previous["mmio_writes"]:
        raise ValueError("polling did not progress and then cease")
    if any(b["poll_runs"] < a["poll_runs"] for a, b in zip(rows, rows[1:])):
        raise ValueError("counter reset")
    nonempty = last["poll_runs"] - last["poll_empty"]
    if nonempty < 0:
        raise ValueError("invalid empty count")
    return {"status": "CAPTURE_ACTIVITY_OBSERVED" if nonempty else "INCONCLUSIVE_NO_PULSES",
            "nonempty_batches": nonempty, "software_polling_stopped": True,
            "hardware_restore_proven": False, "physical_radar_detection_proven": False,
            "mandatory_next_phase": "EXACT_F321_RESTORE"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    contract.validate_sealed_inputs()
    if not args.execute:
        print(json.dumps({"status": "OFFLINE_PLAN_ONLY", "radio_mutation": False}))
        return 0
    out = args.output_dir.resolve(); out.mkdir(parents=True, exist_ok=False)
    report = {"schema": "openmitrastar.f325-capture/v1", "generated_at_utc": datetime.now(timezone.utc).isoformat(),
              "expected_version": contract.F325["version"], "candidate_sha256": contract.F325["sha256"],
              "status": "FAIL_CAPTURE", "arm_attempted": False, "hardware_restore_proven": False,
              "physical_radar_detection_proven": False, "mandatory_next_phase": "EXACT_F321_RESTORE"}
    rows = []
    try:
        check = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                                str(contract.ROOT / "tools/f325_assert_physical_context.ps1"),
                                "-CandidateSha256", contract.F325["sha256"], "-Direction", "promote"],
                               capture_output=True, timeout=20, check=False)
        if check.returncode or not os.environ.get("OM_F325_PHYSICAL_CONTEXT"):
            raise ValueError("live parent lease/binding required")
        first = observe()
        if any(first[k] for k in ("once_phase", "hardware_dirty", "shadow_arm", "configured", "poll_runs", "mmio_writes")):
            raise ValueError("capture requires a pristine boot")
        report["radio_profile"] = parse_radio_profile(
            ssh("/usr/sbin/iwpriv-qtn wifi0 get_region\n"),
            ssh("/usr/sbin/iwpriv-qtn wifi0 get_mode\n"),
            ssh("/usr/sbin/iwconfig-qtn wifi0\n"),
        )
        rows.append(first)
        report["arm_attempted"] = True
        ssh("OM_F325_CAPTURE_ACK=OPENMITRASTAR_F325_CAPTURE_ONCE_20S /usr/sbin/om-radar-once arm >/dev/null\n")
        until = time.monotonic() + 23
        while time.monotonic() < until:
            rows.append(observe()); time.sleep(2)
        rows.append(observe())
        # An explicit stop would hide a broken automatic deadline. It is only
        # a best-effort error cleanup below and can never produce success.
        validate_deadline_stop(rows[-1])
        time.sleep(1)
        rows.append(observe())
        report.update(validate_stopped(rows))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        report["error_type"] = type(error).__name__
        if report["arm_attempted"]:
            try:
                ssh("/usr/sbin/om-radar-once stop >/dev/null\n")
                report["stop_command_completed"] = True
            except (ValueError, OSError, subprocess.SubprocessError):
                report["stop_command_completed"] = False
    (out / "observations.json").write_text(json.dumps(rows, indent=2) + "\n", encoding="ascii")
    (out / "result.json").write_text(json.dumps(report, indent=2) + "\n", encoding="ascii")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] != "FAIL_CAPTURE" else 2


if __name__ == "__main__":
    raise SystemExit(main())
