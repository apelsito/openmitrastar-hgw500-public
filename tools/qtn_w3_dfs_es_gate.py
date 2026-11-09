#!/usr/bin/env python3
"""Fail-closed offline gate for Quantenna DFS operation in ES at 80 MHz.

This tool never configures hardware.  It validates immutable inputs and a
hash-pinned runtime evidence bundle.  RF/LED permission is emitted only when
the complete ES regulatory, native radar, and CAC chain is proven.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_EVIDENCE = (
    ROOT / "work/mission-state/w3-offline/W3_DFS_ES_80_CURRENT_EVIDENCE.json"
)
PINNED_REGDB_SHA256 = (
    "2263cc2407d6e0d1543aa55bd7d2b9b98598301c59b4d3dca40701132f044365"
)
TARGET_COMPATIBLE = "mitrastar,hgw-500bna-qcv2"
TARGET_COUNTRY = "ES"
TARGET_REGION = "es"
TARGET_PRIMARY = 112
TARGET_CENTER = 106
TARGET_BW_MHZ = 80
TARGET_SUBCHANNELS = {100, 104, 108, 112}
MIN_CAC_SECONDS = 70.0
EU_DFS_RQMT_CODE = 1
COMPAT_MARKER = b"proprietary radar backend is unavailable"
ES_TO_EU_TLV = b"\x02es\x05\x00\x01\xff\x01\x02eu"

REQUIRED_RADAR_SYMBOLS = {
    "radar_register",
    "radar_register_is_dfs_chan",
    "radar_register_is_dfs_weather_chan",
    "radar_disable",
    "radar_enable",
    "radar_start",
    "radar_stop",
    "radar_register_statcb",
    "dfs_rqmt_code",
    "radar_set_shared_params",
    "radar_set_chan",
    "radar_get_chan",
    "sta_dfs_is_region_required",
    "radar_ocac_info_addr_get",
    "radar_record_buffer_pt",
    "radar_get_status",
    "radar_set_bw",
    "detect_drv_sample_loc_get",
}

REQUIRED_RUNTIME_MARKERS = (
    "OMDFS region=es regdb=PASS",
    "OMDFS radar-backend=native start=PASS dfs_rqmt=EU bw=80 channel=112",
    "RADAR: CAC started for channel 112",
    "RADAR: CAC completed for channel 112",
    "OMDFS tx-disabled-during-cac=PASS",
    "OMDFS radar-continuous=PASS",
    "OMDFS subchannels=100,104,108,112 nop=clear",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def resolve_path(value: object) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else ROOT / path


def int_set(value: object) -> set[int]:
    if isinstance(value, str):
        value = value.replace(",", " ").split()
    if not isinstance(value, list):
        return set()
    result: set[int] = set()
    for item in value:
        try:
            result.add(int(item))
        except (TypeError, ValueError):
            continue
    return result


def require(condition: bool, code: str, reasons: list[str]) -> None:
    if not condition:
        reasons.append(code)


def evaluate(evidence: dict[str, Any]) -> dict[str, Any]:
    reasons: list[str] = []
    target = evidence.get("target", {})
    regdb = evidence.get("regdb", {})
    radar = evidence.get("radar", {})
    cac = evidence.get("cac", {})

    require(evidence.get("schema") == "openmitrastar-w3-dfs-es-evidence-v1",
            "SCHEMA_MISMATCH", reasons)
    require(target.get("compatible") == TARGET_COMPATIBLE,
            "TARGET_COMPATIBLE_MISMATCH", reasons)
    require(str(target.get("country", "")).upper() == TARGET_COUNTRY,
            "COUNTRY_NOT_ES", reasons)
    require(str(target.get("region", "")).lower() == TARGET_REGION,
            "REGION_NOT_ES", reasons)
    require(target.get("primary_channel") == TARGET_PRIMARY,
            "PRIMARY_NOT_112", reasons)
    require(target.get("center_channel") == TARGET_CENTER,
            "CENTER_NOT_106", reasons)
    require(target.get("bandwidth_mhz") == TARGET_BW_MHZ,
            "BANDWIDTH_NOT_80", reasons)
    require(int_set(target.get("subchannels")) == TARGET_SUBCHANNELS,
            "SUBCHANNEL_BLOCK_NOT_100_104_108_112", reasons)

    regdb_path = resolve_path(regdb.get("path", ""))
    regdb_ok = regdb_path.is_file()
    require(regdb_ok, "REGDB_MISSING", reasons)
    if regdb_ok:
        actual_regdb_sha = sha256(regdb_path)
        require(actual_regdb_sha == PINNED_REGDB_SHA256,
                "REGDB_SHA256_MISMATCH", reasons)
        require(regdb.get("sha256") == actual_regdb_sha,
                "REGDB_EVIDENCE_SHA256_MISMATCH", reasons)
        # The local TLV contains an explicit ES -> EU mapping.  Runtime list
        # readback is still mandatory; string presence alone is not approval.
        require(ES_TO_EU_TLV in regdb_path.read_bytes(),
                "REGDB_ES_TO_EU_MAPPING_ABSENT", reasons)
    require(regdb.get("version_status") == "PASS",
            "REGDB_VERSION_UNPROVEN", reasons)
    version_output = str(regdb.get("version_output", ""))
    require(bool(version_output) and "error" not in version_output.lower(),
            "REGDB_VERSION_OUTPUT_INVALID", reasons)
    require(regdb.get("reg_is_eu") == 1, "REGDB_ES_NOT_EU", reasons)
    require(regdb.get("set_regulatory_region") == TARGET_REGION,
            "REGULATORY_REGION_NOT_SET_ES", reasons)
    require(regdb.get("option_802_11h") == 1, "80211H_NOT_ENABLED", reasons)
    require(regdb.get("is_channel_dfs") == 1, "CHANNEL_112_NOT_DFS", reasons)
    require(regdb.get("is_weather_channel") == 0,
            "BLOCK_100_112_WEATHER_CLASS_MISMATCH", reasons)
    require(regdb.get("radar_bw_mhz") == TARGET_BW_MHZ,
            "RADAR_BANDWIDTH_NOT_80", reasons)
    require(float(regdb.get("min_cac_seconds", 0) or 0) >= MIN_CAC_SECONDS,
            "MIN_CAC_BELOW_70_SECONDS", reasons)
    require(TARGET_SUBCHANNELS <= int_set(regdb.get("regulatory_channels")),
            "REGDB_80MHZ_BLOCK_NOT_ALLOWED", reasons)
    require(TARGET_SUBCHANNELS <= int_set(regdb.get("dfs_channels_80mhz")),
            "REGDB_80MHZ_BLOCK_NOT_LISTED_DFS", reasons)

    radar_path = resolve_path(radar.get("module_path", ""))
    radar_module_ok = radar_path.is_file()
    require(radar_module_ok, "RADAR_MODULE_MISSING", reasons)
    if radar_module_ok:
        radar_bytes = radar_path.read_bytes()
        actual_radar_sha = hashlib.sha256(radar_bytes).hexdigest()
        require(radar.get("module_sha256") == actual_radar_sha,
                "RADAR_MODULE_SHA256_MISMATCH", reasons)
        require(COMPAT_MARKER not in radar_bytes,
                "RADAR_FAIL_CLOSED_COMPAT_STILL_LINKED", reasons)
    require(radar.get("backend") == "native-linux510",
            "RADAR_BACKEND_NOT_NATIVE_LINUX510", reasons)
    require(REQUIRED_RADAR_SYMBOLS <= set(radar.get("exported_symbols", [])),
            "RADAR_ABI_INCOMPLETE", reasons)
    require(radar.get("module_loaded") is True, "RADAR_MODULE_NOT_LOADED", reasons)
    require(radar.get("start_pass") is True, "RADAR_START_NOT_PROVEN", reasons)
    require(radar.get("dfs_rqmt_code") == EU_DFS_RQMT_CODE,
            "RADAR_DFS_REQUIREMENT_NOT_EU", reasons)
    require(radar.get("callbacks_registered") == 3,
            "RADAR_CALLBACKS_NOT_REGISTERED", reasons)
    require(radar.get("channel") == TARGET_PRIMARY, "RADAR_CHANNEL_NOT_112", reasons)
    require(radar.get("bandwidth_mhz") == TARGET_BW_MHZ,
            "RADAR_RUNTIME_BANDWIDTH_NOT_80", reasons)
    require(radar.get("status_before_cac") is True,
            "RADAR_NOT_ACTIVE_BEFORE_CAC", reasons)
    require(radar.get("status_during_cac") is True,
            "RADAR_NOT_CONTINUOUS_DURING_CAC", reasons)
    require(radar.get("status_after_cac") is True,
            "RADAR_NOT_ACTIVE_AFTER_CAC", reasons)

    runtime_log = resolve_path(evidence.get("runtime_log_path", ""))
    runtime_log_ok = runtime_log.is_file()
    require(runtime_log_ok, "RUNTIME_LOG_MISSING", reasons)
    if runtime_log_ok:
        actual_log_sha = sha256(runtime_log)
        require(evidence.get("runtime_log_sha256") == actual_log_sha,
                "RUNTIME_LOG_SHA256_MISMATCH", reasons)
        text = runtime_log.read_text(encoding="utf-8", errors="replace")
        for marker in REQUIRED_RUNTIME_MARKERS:
            require(marker in text, "RUNTIME_MARKER_MISSING:" + marker, reasons)

    try:
        elapsed = (float(cac.get("completed_monotonic_ms")) -
                   float(cac.get("started_monotonic_ms"))) / 1000.0
    except (TypeError, ValueError):
        elapsed = -1.0
    require(elapsed >= MIN_CAC_SECONDS, "CAC_DURATION_BELOW_70_SECONDS", reasons)
    require(cac.get("channel") == TARGET_PRIMARY, "CAC_CHANNEL_NOT_112", reasons)
    require(cac.get("bandwidth_mhz") == TARGET_BW_MHZ,
            "CAC_BANDWIDTH_NOT_80", reasons)
    require(cac.get("status_before") == 0, "CAC_PRE_STATE_NOT_IDLE", reasons)
    require(cac.get("status_during") == 1, "CAC_ACTIVE_STATE_NOT_OBSERVED", reasons)
    require(cac.get("status_after") == 0, "CAC_POST_STATE_NOT_IDLE", reasons)
    require(cac.get("tx_blocked_during") is True,
            "TRANSMIT_NOT_PROVEN_BLOCKED_DURING_CAC", reasons)
    require(cac.get("cac_done") is True, "CAC_DONE_NOT_PROVEN", reasons)
    require(cac.get("cac_in_progress") is False,
            "CAC_STILL_IN_PROGRESS", reasons)
    require(cac.get("radar_detected") is False,
            "RADAR_DETECTED_CHANNEL_MUST_ENTER_NOP", reasons)
    require(TARGET_SUBCHANNELS <= int_set(cac.get("non_occupancy_clear")),
            "NON_OCCUPANCY_STATE_NOT_CLEAR_FOR_80MHZ_BLOCK", reasons)
    require(cac.get("radar_monitoring_after_cac") is True,
            "IN_SERVICE_RADAR_MONITORING_NOT_PROVEN", reasons)
    require(cac.get("ap_beaconing_after_cac") is True,
            "AP_BEACONING_AFTER_CAC_NOT_PROVEN", reasons)

    passed = not reasons
    return {
        "schema": "openmitrastar-w3-dfs-es-gate-result-v1",
        "pass": passed,
        "state": "AP_TX_ENABLED" if passed else "FAIL_CLOSED",
        "rf_allowed": passed,
        "led_5ghz_allowed": passed,
        "led_policy": "CAC_BLINK_READY_SOLID_FAIL_OFF",
        "target": {
            "country": TARGET_COUNTRY,
            "region": TARGET_REGION,
            "primary_channel": TARGET_PRIMARY,
            "center_channel": TARGET_CENTER,
            "bandwidth_mhz": TARGET_BW_MHZ,
            "subchannels": sorted(TARGET_SUBCHANNELS),
        },
        "cac_elapsed_seconds": elapsed,
        "reasons": reasons,
    }


def env_text(result: dict[str, Any]) -> str:
    passed = result["pass"]
    reason = "PASS" if passed else ";".join(result["reasons"])
    return "\n".join((
        f"W3_DFS_ES_80_GATE={'PASS' if passed else 'FAIL'}",
        f"W3_DFS_STATE={result['state']}",
        f"W3_DFS_RF_ALLOWED={1 if passed else 0}",
        f"W3_DFS_LED_5GHZ_ALLOWED={1 if passed else 0}",
        "W3_DFS_COUNTRY=ES",
        "W3_DFS_REGION=es",
        "W3_DFS_PRIMARY_CHANNEL=112",
        "W3_DFS_CENTER_CHANNEL=106",
        "W3_DFS_BANDWIDTH_MHZ=80",
        "W3_DFS_SUBCHANNELS=100,104,108,112",
        f"W3_DFS_REASON={reason}",
        "",
    ))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, default=DEFAULT_EVIDENCE)
    parser.add_argument("--json-output", type=Path)
    parser.add_argument("--env-output", type=Path)
    parser.add_argument("--allow-fail", action="store_true",
                        help="return zero even when the gate correctly fails closed")
    args = parser.parse_args()

    evidence_path = args.evidence if args.evidence.is_absolute() else ROOT / args.evidence
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    result = evaluate(evidence)
    if args.json_output:
        output = args.json_output if args.json_output.is_absolute() else ROOT / args.json_output
        output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    if args.env_output:
        output = args.env_output if args.env_output.is_absolute() else ROOT / args.env_output
        output.write_text(env_text(result), encoding="utf-8")
    print(env_text(result), end="")
    if not result["pass"]:
        for reason in result["reasons"]:
            print(f"BLOCKED {reason}", file=sys.stderr)
    return 0 if result["pass"] or args.allow_fail else 2


if __name__ == "__main__":
    raise SystemExit(main())
