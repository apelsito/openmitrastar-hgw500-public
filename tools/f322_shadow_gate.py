"""Pure evidence validation for F322 unarmed baseline and temporal fixtures.

No device, subprocess or network API exists in this module. F322 cannot safely
restore its acquisition registers, so temporal acquisition is a simulator-only
contract. Stopping polling must never be reported as hardware restoration.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]
DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f322-f321-shadow-device-bound"
HOST = "192.168.1.90"
VERSION = "lyoko-foundation-6.9.1-f322-shadow-f321-device"
BUILD_ID = "e480f419df74f5c6"
KERNEL = "5.10.260-openmitrastar-radiohw"
CANDIDATE_SHA = "55145f55f904beb342dd67b39578a79fbc8a4d0bc68bae944402cab80e5f7f1a"
MANIFEST_SHA = "e53a3b5e7224a57c26ce0ae8bf149ffe427bc259957402dd093791a6f902d48b"
KNOWN_HOSTS_SHA = "020d570ac4a811268852fa973f93ad614005646e3ee7e8a8e5419a74283ac845"
INVENTORY_SHA = "33da391c780e50edbf1d2668709d67081ee16befb60dc27c217c3d5d3d99c232"
DONOR_SOURCE_SHA = "4844a097957ceb8e735de223e57c7843bc34c36247a68b6289c2a59367f09d33"
ACK = "OPENMITRASTAR_F322_SHADOW_TEMPORAL_55145F55"
PROVIDER_SCHEMA = "openmitrastar.radar-shadow-f315/v1"
BLOCKER = "NO_GO_ARM_CLEANUP_CONTRACT"
BLOCKER_REASON = (
    "The sealed F315 provider only stops software polling when shadow_arm=0; "
    "it neither disables hardware capture nor restores acquisition registers/SRAM. "
    "Its BB reader reference does not provide exclusive producer ownership."
)
STATUS_FIXED = {
    "schema": PROVIDER_SCHEMA, "provider": "native-linux-5.10", "oem_runtime_dependency": 0,
    "backend_ready": 0, "fail_closed": 1, "dfs_enable": 0, "tx_authorization": "denied",
    "radar_get_status": 0, "callback_storage": 0, "callback_invocations": 0,
    "shadow_enable": 1, "maps_ready": 1, "bb_mutex_ready": 1, "region": "eu", "channel": 36,
    "bandwidth": 80, "poll_interval_ms": 50, "sample_limit": 18,
    "classification": "SHADOW_HEURISTIC_NO_CALLBACK", "chronology_proven": 0, "physical_rf_detection_proven": 0,
}
STATUS_VARIABLE = frozenset(("shadow_arm", "configured", "polling", "poll_runs", "poll_empty", "poll_unstable",
    "config_attempts", "config_failures", "mmio_writes", "mmio_write_refusals", "callback_refusals",
    "shadow_candidate_batches", "map_failures"))
ERROR_COUNTERS = ("config_failures", "mmio_write_refusals", "map_failures", "poll_unstable")
MONOTONIC_COUNTERS = ("poll_runs", "poll_empty", "poll_unstable", "config_attempts", "config_failures",
    "mmio_writes", "mmio_write_refusals", "callback_refusals", "shadow_candidate_batches", "map_failures")
SNAPSHOT_FIXED = {"schema": PROVIDER_SCHEMA, "authoritative": 0, "callback_allowed": 0}
SNAPSHOT_VARIABLE = frozenset(("sequence", "registers_stable", "raw_count", "processed_count", "zc_count"))
INTEGER_FIELDS = {key for key, value in STATUS_FIXED.items() if type(value) is int} | set(STATUS_VARIABLE) | set(SNAPSHOT_VARIABLE) | {"authoritative", "callback_allowed"}


def require(condition: bool, code: str) -> None:
    if not condition:
        raise ValueError(code)


def exact_json(text: str) -> dict:
    def pairs(items):
        value = {}
        for key, item in items:
            require(key not in value, "duplicate-json-key")
            value[key] = item
        return value
    value = json.loads(text, object_pairs_hook=pairs)
    require(isinstance(value, dict), "json-object-required")
    return value


def pinned(path: Path, sha: str) -> bytes:
    data = path.read_bytes()
    require(hashlib.sha256(data).hexdigest() == sha, "sealed-input-hash-mismatch:" + path.name)
    return data


def sealed_inputs(device: Path = DEVICE) -> dict[str, str]:
    manifest = exact_json(pinned(device / "manifest.json", MANIFEST_SHA).decode("ascii"))
    require(manifest.get("product_version") == VERSION and manifest.get("firmware_build_id") == BUILD_ID,
            "wrong-F322-identity")
    require(all(manifest.get(key) is False for key in ("candidate_eligible", "flash_supported", "release_eligible")),
            "sealed-eligibility-changed")
    shadow = manifest["shadow"]
    require(shadow["shadow_arm_on_boot"] is False and shadow["automatic_arm"] is False
            and shadow["authoritative_enable"] is False and shadow["radar_get_status"] is False
            and shadow["radar_start"] is False and shadow["dfs_tx_authorized"] is False and shadow["callbacks"] == 0,
            "shadow-authority-contract-changed")
    image = manifest["artifacts"]["webformat"]
    require(image["sha256"] == CANDIDATE_SHA and image["bytes"] == 5320704
            and re.fullmatch(r"[A-Za-z0-9_.-]+", image["file"]) is not None, "wrong-F322-image-contract")
    require(len(pinned(device / image["file"], CANDIDATE_SHA)) == 5320704, "wrong-F322-image-size")
    pinned(device / "known_hosts.f322", KNOWN_HOSTS_SHA)
    inventory = exact_json(pinned(device / "rootfs-inventory.json", INVENTORY_SHA).decode("ascii"))
    files = {"/" + path: row["sha256"] for path, row in inventory["expected_changes"].items()}
    require(len(files) == 9 and all(re.fullmatch(r"/[A-Za-z0-9_./-]+", key)
            and ".." not in Path(key).parts and re.fullmatch(r"[0-9a-f]{64}", value) for key, value in files.items()),
            "unsafe-installed-file-contract")
    pinned(ROOT / "work/kernel-port/modules/f315_radar_shadow/qtn_radar_shadow_f315_main.c", DONOR_SOURCE_SHA)
    return files


def parse_kv(text: str, expected: set) -> dict:
    parsed = {}
    for line in text.splitlines():
        require("=" in line, "malformed-provider-line")
        key, value = line.split("=", 1)
        require(key in expected and key not in parsed, "unknown-or-duplicate-provider-field")
        if key in INTEGER_FIELDS:
            require(re.fullmatch(r"[0-9]{1,15}", value) is not None, "invalid-provider-integer:" + key)
            parsed[key] = int(value)
        else:
            require(re.fullmatch(r"[A-Za-z0-9_./-]+", value) is not None, "invalid-provider-token:" + key)
            parsed[key] = value
    require(set(parsed) == expected, "incomplete-provider-observables")
    return parsed


def parse_observation(text: str, expected_files: dict, elapsed_seconds: float) -> dict:
    """Consume only framed, allowlisted fields; never persist raw SSH output."""
    require(len(text) <= 50000, "oversized-observation")
    text = text.replace("\r\n", "\n")
    parts = re.findall(r"(?ms)^OMF322_([A-Z_]+)_BEGIN\n(.*?)^OMF322_\1_END\n?", text)
    expected_sections = ("IDENTITY", "FILES", "STATUS_BEFORE", "SNAPSHOT", "RUNTIME", "STATUS_AFTER")
    require(tuple(name for name, _ in parts) == expected_sections, "missing-duplicate-or-reordered-sections")
    # No unframed output, including shell diagnostics or raw pulse samples.
    remainder = re.sub(r"(?ms)^OMF322_([A-Z_]+)_BEGIN\n(.*?)^OMF322_\1_END\n?", "", text)
    require(not remainder.strip(), "unframed-observation-data")
    sections = dict(parts)
    identity = {}
    for line in sections["IDENTITY"].splitlines():
        require("=" in line, "malformed-identity")
        key, value = line.split("=", 1)
        require(key not in identity, "duplicate-identity")
        identity[key] = value
    require(set(identity) == {"version", "build", "kernel", "boot_id", "fatal_count", "boot_ready", "radio2_ready", "radio5_ready", "bridge_ready"}, "incomplete-identity")
    require(identity["version"] == VERSION and identity["build"] == BUILD_ID and identity["kernel"] == KERNEL,
            "installed-F322-identity-mismatch")
    require(re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", identity["boot_id"]) is not None, "boot-id-unavailable")
    require(identity["fatal_count"] == "0" and all(identity[key] == "1" for key in ("boot_ready", "radio2_ready", "radio5_ready", "bridge_ready")), "fatal-or-management-regression")
    rows = re.findall(r"(?m)^([0-9a-f]{64})\s+(/[^\n]+)$", sections["FILES"])
    require(len(rows) == len(expected_files) and {path: sha for sha, path in rows} == expected_files, "installed-file-hash-mismatch")
    require(len(sections["FILES"].splitlines()) == len(rows), "unexpected-file-hash-data")
    status_fields = set(STATUS_FIXED) | set(STATUS_VARIABLE)
    before = parse_kv(sections["STATUS_BEFORE"], status_fields)
    after = parse_kv(sections["STATUS_AFTER"], status_fields)
    snapshot = parse_kv(sections["SNAPSHOT"], set(SNAPSHOT_FIXED) | set(SNAPSHOT_VARIABLE))
    runtime = exact_json(sections["RUNTIME"])
    for key in ("ok", "available", "observation_only"):
        require(runtime.get(key) is True, "runtime-observation-unavailable")
    require(runtime.get("schema") == "lyoko.radio.dfs-observation/v1" and runtime.get("mode") == "shadow"
            and runtime.get("current_channel") == 36 and runtime.get("channel") == 36
            and runtime.get("bandwidth_mhz") == 80 and runtime.get("region") == "ES"
            and runtime.get("current_channel_dfs") is False and runtime.get("backend_ready") is False
            and runtime.get("dfs_tx_authorized") is None and runtime.get("tx", {}).get("authorized") is None
            and runtime.get("detector", {}).get("running") is False
            and runtime.get("controls") == {"apply": False, "bypass": False}, "runtime-channel-domain-or-authority-mismatch")
    require(type(runtime.get("doth")) is bool, "missing-doth-observation")
    require(runtime.get("cac", {}).get("state") == "not-required"
            and runtime.get("channel_availability", {}).get("code") == 2, "non-DFS-availability-unverified")
    require(type(runtime.get("observed_at_uptime_seconds")) is int, "missing-uptime-observation")
    observation = {"elapsed_seconds": elapsed_seconds, "boot_id": identity["boot_id"], "version": VERSION,
        "status_before": before, "snapshot": snapshot, "status_after": after,
        "runtime": {"channel": 36, "bandwidth": 80, "region": "ES", "doth": runtime["doth"],
                    "uptime_seconds": runtime["observed_at_uptime_seconds"], "backend_ready": False,
                    "dfs_tx_authorized": None, "cac_state": "not-required", "availability": 2},
        "fatal_count": 0, "management_ready": True, "installed_file_hashes": expected_files}
    validate_observation(observation)
    return observation


def validate_observation(row: dict) -> None:
    require(type(row.get("elapsed_seconds")) in (int, float) and 0 <= row["elapsed_seconds"] <= 300,
            "invalid-observation-time")
    require(row.get("version") == VERSION and type(row.get("fatal_count")) is int and row["fatal_count"] == 0 and row.get("management_ready") is True,
            "fatal-or-management-regression")
    require(re.fullmatch(r"[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}", row.get("boot_id", "")) is not None,
            "invalid-boot-identity")
    runtime = row["runtime"]
    require(set(runtime) == {"channel", "bandwidth", "region", "doth", "uptime_seconds", "backend_ready", "dfs_tx_authorized", "cac_state", "availability"}
            and type(runtime["channel"]) is int and runtime["channel"] == 36
            and type(runtime["bandwidth"]) is int and runtime["bandwidth"] == 80 and runtime["region"] == "ES"
            and type(runtime["doth"]) is bool and type(runtime["uptime_seconds"]) is int
            and runtime["uptime_seconds"] >= 0 and runtime["backend_ready"] is False
            and runtime["dfs_tx_authorized"] is None and runtime["cac_state"] == "not-required"
            and type(runtime["availability"]) is int and runtime["availability"] == 2, "invalid-runtime-observables")
    require(len(row["installed_file_hashes"]) == 9 and all(re.fullmatch(r"/[A-Za-z0-9_./-]+", path)
            and re.fullmatch(r"[0-9a-f]{64}", sha) for path, sha in row["installed_file_hashes"].items()), "invalid-installed-identity")
    before, after, snapshot = row["status_before"], row["status_after"], row["snapshot"]
    for status in (before, after):
        require(set(status) == set(STATUS_FIXED) | set(STATUS_VARIABLE), "incomplete-status")
        for key, expected in STATUS_FIXED.items():
            require(type(status[key]) is type(expected) and status[key] == expected, "provider-contract-mismatch:" + key)
        require(all(type(status[key]) is int and 0 <= status[key] <= 10**15 for key in STATUS_VARIABLE), "invalid-counter")
        require(all(status[key] == 0 for key in ERROR_COUNTERS), "provider-error-counter")
    require(set(snapshot) == set(SNAPSHOT_FIXED) | set(SNAPSHOT_VARIABLE), "incomplete-snapshot")
    for key, expected in SNAPSHOT_FIXED.items():
        require(type(snapshot[key]) is type(expected) and snapshot[key] == expected, "snapshot-authority-mismatch")
    require(all(type(snapshot[key]) is int and 0 <= snapshot[key] <= 0xffffffff for key in SNAPSHOT_VARIABLE), "invalid-snapshot-counter")
    require(snapshot["raw_count"] <= 18 and snapshot["processed_count"] <= snapshot["raw_count"] and snapshot["zc_count"] <= snapshot["raw_count"], "invalid-batch-bound")
    require(all(after[key] >= before[key] for key in MONOTONIC_COUNTERS), "counter-reset-within-observation")
    # poll_runs increments before f315_last_batch is published under its mutex.
    # Permit that one in-flight publication; do not demand non-atomic equality.
    require(max(0, before["poll_runs"] - 1) <= snapshot["sequence"] <= after["poll_runs"], "snapshot-outside-status-bracket")
    require(after["poll_runs"] - before["poll_runs"] <= 400, "observation-window-too-wide")


def validate_baseline(rows: list[dict]) -> dict:
    require(len(rows) == 2 and 1 <= rows[1]["elapsed_seconds"] - rows[0]["elapsed_seconds"] <= 30, "baseline-needs-two-separated-observations")
    for row in rows:
        validate_observation(row)
        for status in (row["status_before"], row["status_after"]):
            require(all(status[key] == 0 for key in ("shadow_arm", "configured", "polling", "poll_runs", "poll_empty", "config_attempts", "mmio_writes", "shadow_candidate_batches")), "baseline-not-pristine-unarmed")
        require(all(row["snapshot"][key] == 0 for key in SNAPSHOT_VARIABLE), "baseline-snapshot-not-empty")
    require(rows[0]["boot_id"] == rows[1]["boot_id"] and rows[0]["installed_file_hashes"] == rows[1]["installed_file_hashes"], "baseline-identity-changed")
    require(rows[0]["runtime"]["doth"] == rows[1]["runtime"]["doth"], "baseline-radio-policy-changed")
    require(rows[0]["status_before"]["callback_refusals"] == rows[1]["status_after"]["callback_refusals"], "concurrent-callback-registration")
    return {"status": "PASS_F322_BASELINE_UNARMED", "samples": 2, "provider_mmio_writes": 0,
            "acquisition_armed": False, "hardware_capture_restoration_proven": False,
            "temporal_acquisition": BLOCKER, "physical_rf_detection_proven": False}


def temporal_fixture(rows: list[dict], cleanup: list[dict]) -> dict:
    """Evaluate simulated temporal samples without an arm or device API.

    Even a fixture showing polling cessation cannot produce physical PASS.
    """
    require(len(rows) >= 31, "temporal-window-needs-at-least-31-samples")
    require(60 <= rows[-1]["elapsed_seconds"] - rows[0]["elapsed_seconds"] <= 65, "temporal-window-not-60-seconds")
    first = rows[0]
    previous = None
    for row in rows:
        validate_observation(row)
        require(row["boot_id"] == first["boot_id"] and row["installed_file_hashes"] == first["installed_file_hashes"], "temporal-identity-changed")
        require({k: v for k, v in row["runtime"].items() if k != "uptime_seconds"}
                == {k: v for k, v in first["runtime"].items() if k != "uptime_seconds"}, "temporal-radio-policy-changed")
        for status in (row["status_before"], row["status_after"]):
            require(all(status[key] == 1 for key in ("shadow_arm", "configured", "polling")), "temporal-acquisition-not-running")
            require(status["config_attempts"] == 1 and status["mmio_writes"] > 0, "configuration-not-single-complete-attempt")
            require(status["callback_refusals"] == first["status_before"]["callback_refusals"], "concurrent-provider-registration")
        require(row["snapshot"]["registers_stable"] == 1, "unstable-capture-registers")
        if previous is not None:
            require(0 < row["elapsed_seconds"] - previous["elapsed_seconds"] <= 3, "temporal-sampling-gap")
            require(row["status_before"]["poll_runs"] > previous["status_after"]["poll_runs"]
                    and row["snapshot"]["sequence"] > previous["snapshot"]["sequence"], "temporal-polling-stalled")
            require(all(row["status_before"][key] >= previous["status_after"][key] for key in MONOTONIC_COUNTERS), "temporal-counter-reset")
            require(row["status_after"]["mmio_writes"] == previous["status_after"]["mmio_writes"], "unexpected-MMIO-write-after-configuration")
        previous = row
    require(len(cleanup) >= 2 and cleanup[0]["elapsed_seconds"] > rows[-1]["elapsed_seconds"]
            and cleanup[-1]["elapsed_seconds"] - cleanup[0]["elapsed_seconds"] >= 1, "cleanup-needs-separated-samples")
    for row in cleanup:
        validate_observation(row)
        require(row["boot_id"] == first["boot_id"] and row["installed_file_hashes"] == first["installed_file_hashes"], "cleanup-identity-changed")
        require({k: v for k, v in row["runtime"].items() if k != "uptime_seconds"}
                == {k: v for k, v in first["runtime"].items() if k != "uptime_seconds"}, "cleanup-radio-policy-changed")
        for status in (row["status_before"], row["status_after"]):
            require(status["shadow_arm"] == 0 and status["polling"] == 0 and status["configured"] == 1, "software-polling-cleanup-incomplete")
            require(status["mmio_writes"] == rows[-1]["status_after"]["mmio_writes"]
                    and status["callback_refusals"] == first["status_before"]["callback_refusals"], "cleanup-counter-change")
        require(row["status_before"]["poll_runs"] >= rows[-1]["status_after"]["poll_runs"]
                and row["snapshot"]["sequence"] >= rows[-1]["snapshot"]["sequence"], "cleanup-counter-reset")
        require(row["status_before"]["poll_runs"] == row["status_after"]["poll_runs"] == cleanup[0]["status_before"]["poll_runs"], "polling-continues-after-disarm")
        require(row["snapshot"]["sequence"] == cleanup[0]["snapshot"]["sequence"], "publication-continues-after-disarm")
    return {"status": "PASS_SIMULATED_TEMPORAL_POLLING_ONLY", "simulation": True,
            "seconds": rows[-1]["elapsed_seconds"] - rows[0]["elapsed_seconds"], "samples": len(rows),
            "polling_progress_observed": True, "software_polling_stopped": True,
            "hardware_restoration_proven": False, "physical_rf_detection_proven": False,
            "physical_arming": BLOCKER, "release_eligible": False}
