#!/usr/bin/env python3
"""File-only F366 campaign plan and diagnostic-transcript reviewer.

No SSH, AELITA, UART, socket, process launch, radio control or flash path exists
in this tool. A successful transcript review is not independent RF evidence.
The hardware owner executes the bound acquisition/recovery runner separately.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from f301_dfs_es_plan import classify_channel


ROOT = Path(__file__).resolve().parents[1]
STATUS_PREFIX = "OMF366_STATUS "
COMPLETE = re.compile(
    r"^OMF366_DIAGNOSTIC_COMPLETE observations=(\d+) jobs_delta=(\d+) "
    r"authority=0 hardware_quiesced=0 reboot_required=1$"
)
ZERO_FIELDS = (
    "callbacks", "engine_fault_latched", "job_timeouts", "protocol_errors",
    "hardware_errors", "last_error", "diagnostic_stopped",
)
NUMERIC_FIELDS = (
    *ZERO_FIELDS, "channel", "hardware_enabled", "hardware_ready",
    "hardware_dirty", "started", "ready", "polls", "jobs_completed",
    "postfilter_applied", "ipc_session", "ipc_sequence", "ipc_generation",
    "pm_active", "pm_acquisitions", "pm_releases", "max_job_latency_ms",
)


def sha(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def strict_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate_json_key:" + key)
        result[key] = value
    return result


def read_object(text: str) -> dict[str, Any]:
    value = json.loads(text, object_pairs_hook=strict_object)
    if not isinstance(value, dict):
        raise ValueError("json_object_required")
    return value


def channel_case(name: str, channel: int, width: int) -> dict[str, Any]:
    return {"id": name, **classify_channel(channel, width)}


def plan() -> dict[str, Any]:
    """Reuse only the existing pure occupied-block classifier and timers."""
    return {
        "schema": "openmitrastar.f366-dfs-campaign-plan/v1",
        "mode": "OFFLINE_PLAN_NO_HARDWARE_EXECUTOR",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "target": {"device": "hgw500bna-qcv2-a2-primary", "host": "192.168.1.90"},
        "artifact_binding": None,
        "binding_note": "Bind actual F366 image/manifest/installer and current F365 fallback evidence after they exist. No guessed hash or build seal.",
        "first_gate": {
            "id": "F366_NONDFS_ACQUISITION",
            "target": channel_case("acquisition", 36, 80),
            "authority": 0,
            "watchdog_session_ms": 180000,
            "activation_command_for_guarded_owner_only": "/usr/sbin/om-f366-diagnostic activate TOKEN32",
            "status_command": "/usr/sbin/om-f366-status",
            "required_observations": 20,
            "stdout_sample_contract": "OMF366_STATUS index=N json={numeric allowlisted status}",
            "prerequisites": [
                "Actual F366 full-image acceptance and exact source/image bindings, with native provider coherent with current F365 kernel/DT and qdrv peers.",
                "Root sole hardware owner; qualified watchdog/recovery plan and current accepted fallback evidence.",
                "Fresh boot with 5 GHz pending and native acquisition off; do not unload/replace an already dirty qdrv/provider.",
                "F366 2.4 GHz, Ethernet, SSH, store and protected partition gates pass before activation.",
                "Host transcript capture must begin before ARM and preserve each observation before CEASE resets /run.",
            ],
            "pass_scope": "Real FIFO/ZC acquisition, userspace preprocess/classifier and GPL postfilter progress; no callback or DFS transmission authority.",
            "completion": "STOP_DIAGNOSTIC software drain, retain dirty module, CEASE and verified watchdog reset/management return under the root runner.",
            "client_required": False,
            "client_note": "AELITA is not needed to prove acquisition; independent wired AELITA discovery may proceed before the later client gate.",
        },
        "later_dfs_steps": [
            {
                "id": "DFS_AUTHORITY_CANDIDATE",
                "status": "BLOCKED_BY_F366_COMPILED_AUTHORITY_ZERO",
                "requirements": [
                    "Physically accepted acquisition result; then a new coherent versioned candidate with reviewed callback authority and current recovery binding.",
                    "Live ES/EU/DOTH/TPC and driver regulatory/DFS lists for the selected width; reject a missing subchannel or active NOP.",
                    "TX-off, CAC status, radar generation and channel-availability readbacks; external beacon/RF observation for the complete occupied block.",
                    "A reviewed supervisor lifetime covering full 600-second CAC and 1800-second NOP; F366's 180-second diagnostic session is insufficient.",
                    "No CAC/NOP shortening, region spoof, detector bypass, same-boot provider reload or global route changes.",
                ],
            },
            {
                "id": "FIRST_DFS_SERVICE",
                "target": channel_case("first-dfs", 100, 20),
                "sequence": [
                    "Verify the exact channel block and empty NOP, then use the reviewed DFS-aware apply path once.",
                    "Observe detector continuity and TX/beacon suppression for full CAC plus 15-second observation margin.",
                    "After verified CAC_DONE, associate AELITA with WPA2/CCMP; prove expected BSSID locally, channel, AUTH/ASSOC/AUTHORIZED.",
                    "Prove 32 MiB each direction with matching hashes, bound to AELITA Wi-Fi; keep 120 seconds of useful traffic/monitoring.",
                    "Probe an explicit HTTPS endpoint bound to Wi-Fi, retaining wired SSH; verify source/interface/route and Wi-Fi counters.",
                    "Verify management/2.4 GHz and absence of new fatal markers, then restore captured radio and client state.",
                ],
            },
            {
                "id": "CHANNEL_WIDTH_BRANCH_COVERAGE",
                "status": "LATER_CANDIDATE_ONLY",
                "cases": [
                    channel_case("lower-dfs-80", 52, 80),
                    channel_case("upper-dfs-80", 100, 80),
                    channel_case("weather-secondary-intersection-80", 116, 80),
                    channel_case("upper-tail-40", 132, 40),
                    channel_case("upper-edge-20", 140, 20),
                ],
                "scope": "Minimal distinct policy/block branches, not certification of every advertised primary channel or every radar waveform.",
                "ordering": "Finish all width changes before injecting radar. While any NOP is active, preserve bandwidth because the inherited NOP expiry expands using current width.",
            },
            {
                "id": "SOFTWARE_RADAR_CSA_NOP",
                "status": "CONTROL_PLANE_ONLY_FUTURE_ADAPTER_REQUIRED",
                "target": channel_case("software-radar", 100, 80),
                "sequence": [
                    "Confirm successful CAC and in-service traffic, target 100/80, and available non-DFS escape 36/80.",
                    "Use only the candidate's reviewed software-radar hook; label origin SOFTWARE_INJECTION throughout the evidence.",
                    "Observe TX stop and actual CSA/channel move, client reassociation/traffic and NOP on all 100/104/108/112 subchannels.",
                    "Attempted re-selection must be rejected through NOP. Keep width80, ES and the same boot; never clear NOP or reboot to evade it.",
                    "Record monotonic elapsed >=1800 seconds and expiry to CAC_REQUIRED; channel reuse must perform a fresh full CAC.",
                ],
                "does_not_prove": "RF radar acquisition sensitivity, waveform classification or calibrated detector conformity.",
            },
            {
                "id": "REAL_RF_RADAR",
                "status": "CALIBRATED_RADAR_SOURCE_AND_CAPTURE_NOT_BOUND",
                "sequence": [
                    "Bind authorized calibrated RF source, controlled coupling/attenuation and exact waveform/timing evidence.",
                    "Observe real RF radar through the acquisition/classifier/callback chain during CAC and in-service operation.",
                    "Measure TX cessation/evacuation and complete occupied-block NOP with an independent RF observer.",
                    "Retain true RF event identity separately from software injection, simulation and math-oracle evidence.",
                ],
            },
        ],
        "aelita_contract": {
            "management_address": None,
            "management_interface_index": None,
            "wifi_interface_index": None,
            "original_wifi_profile": None,
            "requirements": [
                "Discover current AELITA host, pinned SSH key, wired management address/interface and Wi-Fi adapter; do not assume historical .63 or alias Wi-Fi.",
                "Capture addresses/routes/metrics/profile privately; preserve the interface and route carrying SSH for the whole test.",
                "Bind local payload sockets/HTTPS to Wi-Fi source/interface and verify Wi-Fi counters; wired internet success is not Wi-Fi internet evidence.",
                "If source binding selects wired egress, report BLOCKED_WIFI_PATH_UNPROVEN rather than changing global route priority.",
                "Restore the exact captured Wi-Fi profile and scoped test resources even if association/traffic fails; keep PSKs/MACs out of public outputs.",
            ],
            "reuse": [
                "tools/aelita_ssh_policy.py pinned mode for host-key verification",
                "tools/run_f293_5g_aelita_traffic.py transfer_view, association and secret-free transfer helpers only after F366/current identity adaptation",
                "tools/run_f301_multicast_igmp_physical.py oracle connection/restoration patterns, not its F301 execution entrypoint",
            ],
        },
        "never_infer": [
            "Acquisition activity or empty classification windows do not establish positive RF radar detection.",
            "Passive client non-observation alone is not a calibrated proof of CAC RF silence.",
            "Diagnostic completion is not reset/recovery, client, traffic, DFS or release PASS.",
            "A local evidence parser does not grant hardware authority or independently authenticate supplied observations.",
        ],
    }


def review_transcript(text: str) -> dict[str, Any]:
    samples: list[dict[str, Any]] = []
    failures: list[str] = []
    complete: list[tuple[int, int]] = []
    for line in text.splitlines():
        if line.startswith(STATUS_PREFIX):
            match = re.fullmatch(r"OMF366_STATUS index=(\d+) json=(\{.*\})", line)
            if not match:
                failures.append("malformed_status_line")
                continue
            index = int(match.group(1))
            if index != len(samples):
                failures.append("nonsequential_or_duplicate_status_index")
            try:
                status = read_object(match.group(2))
            except (ValueError, json.JSONDecodeError):
                failures.append("invalid_or_duplicate_status_json")
                continue
            samples.append(status)
        elif line.startswith("OMF366_DIAGNOSTIC_COMPLETE"):
            match = COMPLETE.fullmatch(line)
            if not match:
                failures.append("invalid_diagnostic_complete_marker")
            else:
                complete.append((int(match.group(1)), int(match.group(2))))
        elif line.startswith(("OMF366_NATIVE_FAILED", "OMF366_ERROR ")):
            failures.append("native_start_failed")
    if len(samples) != 20:
        failures.append("expected_exactly_20_observations")
    if len(complete) != 1 or (complete and (complete[0][0] != 20 or complete[0][1] <= 0)):
        failures.append("diagnostic_completion_not_proven")
    numeric_valid = True
    for index, status in enumerate(samples):
        if status.get("schema") != "openmitrastar.f366-status/v1" or status.get("provider_present") is not True:
            failures.append(f"sample_{index}_provider_schema")
        for key in NUMERIC_FIELDS:
            value = status.get(key)
            if type(value) is not int or (value < 0 and key != "last_error"):
                failures.append(f"sample_{index}_invalid_{key}")
                numeric_valid = False
        for key in ZERO_FIELDS:
            if status.get(key) != 0:
                failures.append(f"sample_{index}_nonzero_{key}")
        for key in ("hardware_enabled", "hardware_ready", "hardware_dirty", "started"):
            if status.get(key) != 1:
                failures.append(f"sample_{index}_not_one_{key}")
        if status.get("channel") != 36:
            failures.append(f"sample_{index}_not_channel36")
    progress = None
    if samples and numeric_valid:
        if samples[-1]['postfilter_applied'] != 1:
            failures.append('final_postfilter_not_applied')
        for older, newer in zip(samples, samples[1:]):
            for key in ("jobs_completed", "polls", "ipc_sequence", "pm_acquisitions", "pm_releases"):
                if newer[key] < older[key]:
                    failures.append("counter_regressed_" + key)
            if newer["ipc_session"] != older["ipc_session"]:
                failures.append("service_session_changed")
        progress = samples[-1]["jobs_completed"] - samples[0]["jobs_completed"]
        if progress <= 0:
            failures.append("jobs_did_not_progress")
        if complete and progress > complete[0][1]:
            failures.append("completion_delta_inconsistent_with_samples")
    return {
        "schema": "openmitrastar.f366-diagnostic-transcript-review/v1",
        "status": "PASS_CAPTURED_DIAGNOSTIC_TELEMETRY" if not failures else "FAIL_CAPTURED_DIAGNOSTIC_TELEMETRY",
        "mode": "LOCAL_FILE_REVIEW",
        "sample_count": len(samples),
        "observed_jobs_delta": progress,
        "failures": sorted(set(failures)),
        "hardware_execution": False,
        "physical_evidence_authenticated": False,
        "requires_external_bindings": ["exact candidate/source pins", "physical boot identity", "watchdog ARM/CEASE trace", "actual reset and management recovery"],
        "dfs_authority": False,
        "rf_detection_pass": False,
        "client_pass": False,
        "traffic_pass": False,
        "release_pass": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("plan", "review-transcript"):
        command = sub.add_parser(name, allow_abbrev=False)
        command.add_argument("--output-dir", type=Path, required=True)
        if name == "review-transcript":
            command.add_argument("--transcript", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    if output.exists():
        parser.error("output directory already exists; preserve immutable prior evidence")
    if args.command == "plan":
        result = plan()
        filename = "plan.json"
    else:
        transcript = args.transcript.resolve(strict=True)
        result = review_transcript(transcript.read_text(encoding="utf-8", errors="strict"))
        result["transcript"] = {"path": str(transcript), "bytes": transcript.stat().st_size, "sha256": sha(transcript)}
        filename = "result.json"
    result["local_source_bindings"] = {
        str(path.relative_to(ROOT)): sha(path)
        for path in (Path(__file__).resolve(), ROOT / "tools/f301_dfs_es_plan.py", ROOT / "docs/LYOKO_CHANNEL_POLICY_ES.md")
    }
    output.mkdir(parents=True, exist_ok=False)
    destination = output / filename
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(destination), "sha256": sha(destination), "status": result.get("status", result["mode"]), "hardware_execution": False}))
    return int(args.command == "review-transcript" and bool(result["failures"]))


if __name__ == "__main__":
    raise SystemExit(main())
