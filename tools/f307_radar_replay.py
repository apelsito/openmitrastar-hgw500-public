#!/usr/bin/env python3
"""Deterministic offline replay for the F303 Quantenna radar evidence model.

The replay engine deliberately consumes classifier outcomes as OEM-oracle
inputs. It does not implement pulse classification, access MMIO, load a module,
or claim that physical radar detection works.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
from pathlib import Path
from typing import Any


SESSION_SCHEMA = "openmitrastar.f307-radar-replay/v1"
RESULT_SCHEMA = "openmitrastar.f307-radar-replay-result/v1"
OEM_RADAR_SHA256 = "3550945b4affe54ddc5dcc6a3d13bb4caed6f38e1a6d0fb7b295028381e58332"
NORMAL_CAC_MS = 70_000
WEATHER_CAC_MS = 600_000
NOP_MS = 1_800_000

IMMEDIATE_CHANNELS = {36, 40, 44, 48}
DFS_CHANNELS = {52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140}
ADMITTED_CHANNELS = IMMEDIATE_CHANNELS | DFS_CHANNELS
WEATHER_CHANNELS = {120, 124, 128}
PAIRS_40 = (
    (36, 40), (44, 48), (52, 56), (60, 64), (100, 104),
    (108, 112), (116, 120), (124, 128), (132, 136),
)
BLOCKS_80 = (
    (36, 40, 44, 48),
    (52, 56, 60, 64),
    (100, 104, 108, 112),
    (116, 120, 124, 128),
    (132, 136, 140, 144),
)
SENSITIVE_KEYS = re.compile(r"(?i)(psk|password|passphrase|private.?key|secret|client.?mac|calibration)")


def _load_f303():
    path = Path(__file__).with_name("f303_radar_vector_harness.py")
    spec = importlib.util.spec_from_file_location("f303_radar_vector_harness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load F303 radar vector harness")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


F303 = _load_f303()


def canonical_sha256(payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    return hashlib.sha256(encoded).hexdigest()


def _require_int(value: Any, field: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{field} must be an integer")
    return value


def _scan_sensitive(value: Any, path: str = "$") -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if SENSITIVE_KEYS.search(str(key)):
                raise ValueError(f"sensitive field is forbidden at {path}.{key}")
            _scan_sensitive(child, f"{path}.{key}")
    elif isinstance(value, list):
        for index, child in enumerate(value):
            _scan_sensitive(child, f"{path}[{index}]")


def validate_provenance(session: dict[str, Any]) -> dict[str, Any]:
    source = session.get("source")
    if source not in {"synthetic", "oem-oracle-sanitized", "authorized-lab-capture-sanitized"}:
        raise ValueError("unsupported replay source")
    provenance = session.get("provenance")
    if not isinstance(provenance, dict):
        raise ValueError("provenance object is required")
    if provenance.get("oem_radar_sha256") != OEM_RADAR_SHA256:
        raise ValueError("OEM radar hash mismatch")
    if provenance.get("raw_uart_retained") is not False:
        raise ValueError("raw_uart_retained must be false")
    if provenance.get("sensitive_material_retained") is not False:
        raise ValueError("sensitive_material_retained must be false")
    if source != "synthetic":
        capture_sha = provenance.get("capture_sha256")
        if not isinstance(capture_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", capture_sha):
            raise ValueError("sanitized captures require capture_sha256")
    return {"source": source, **provenance}


def build_channel_plan(config: dict[str, Any]) -> dict[str, Any]:
    if config.get("country") != "ES" or config.get("radar_region") != "eu":
        raise ValueError("Lyoko DFS replay requires country ES normalized to radar region eu")
    primary = _require_int(config.get("channel"), "regulatory.channel")
    bandwidth = _require_int(config.get("bandwidth_mhz"), "regulatory.bandwidth_mhz")
    if primary not in ADMITTED_CHANNELS:
        raise ValueError("channel is outside the F301 ES contract")

    if bandwidth == 20:
        occupied = (primary,)
    elif bandwidth == 40:
        secondary = _require_int(config.get("secondary_channel"), "regulatory.secondary_channel")
        occupied = next((pair for pair in PAIRS_40 if set(pair) == {primary, secondary}), ())
        if not occupied:
            raise ValueError("invalid or incomplete ES 40 MHz channel pair")
    elif bandwidth == 80:
        occupied = next((block for block in BLOCKS_80 if primary in block), ())
        if not occupied or any(channel not in ADMITTED_CHANNELS for channel in occupied):
            raise ValueError("incomplete ES 80 MHz block; channel 144 is not admitted")
    else:
        raise ValueError("bandwidth must be 20, 40 or 80 MHz")

    dfs_required = bool(set(occupied) & DFS_CHANNELS)
    weather = bool(set(occupied) & WEATHER_CHANNELS)
    cac_ms = WEATHER_CAC_MS if weather else NORMAL_CAC_MS if dfs_required else 0
    return {
        "country": "ES",
        "radar_region": "eu",
        "primary_channel": primary,
        "bandwidth_mhz": bandwidth,
        "occupied_20mhz_channels": list(occupied),
        "dfs_required": dfs_required,
        "weather_radar_intersection": weather,
        "cac_required_ms": cac_ms,
        "non_occupancy_ms": NOP_MS if dfs_required else 0,
    }


def _event_snapshot(state: dict[str, Any], event: dict[str, Any], details: dict[str, Any]) -> dict[str, Any]:
    now = event["at_ms"]
    active_nop = sorted(channel for channel, until in state["nop_until"].items() if now < until)
    return {
        "at_ms": now,
        "type": event["type"],
        "details": details,
        "state": {
            "backend_started": state["backend_started"],
            "detector_enabled": state["detector_enabled"],
            "cac_active": state["cac_started_at"] is not None,
            "current_channel": state["plan"]["primary_channel"],
            "tx_allowed": state["tx_allowed"],
            "evacuation_required": state["evacuation_required"],
            "active_nop_channels": active_nop,
        },
    }


def replay_session(session: dict[str, Any]) -> dict[str, Any]:
    if session.get("schema") != SESSION_SCHEMA:
        raise ValueError("unsupported or missing replay schema")
    _scan_sensitive(session)
    provenance = validate_provenance(session)
    plan = build_channel_plan(session.get("regulatory", {}))
    events = session.get("events")
    if not isinstance(events, list) or not events:
        raise ValueError("events must be a non-empty array")

    state: dict[str, Any] = {
        "backend_started": False,
        "detector_enabled": False,
        "cac_started_at": None,
        "plan": plan,
        "tx_allowed": not plan["dfs_required"],
        "evacuation_required": False,
        "nop_until": {},
        "nop_registered": set(),
        "radar_callback_count": 0,
        "radar_channels": set(),
    }
    violations: list[str] = []
    vector_failures: list[str] = []
    timeline: list[dict[str, Any]] = []
    previous_ms = -1

    for index, event in enumerate(events):
        if not isinstance(event, dict):
            raise ValueError(f"events[{index}] must be an object")
        at_ms = _require_int(event.get("at_ms"), f"events[{index}].at_ms")
        if at_ms < 0 or at_ms < previous_ms:
            raise ValueError("event timestamps must be monotonic and non-negative")
        previous_ms = at_ms
        kind = event.get("type")
        details: dict[str, Any] = {}

        if kind == "backend_start":
            if state["backend_started"]:
                violations.append(f"event[{index}]:backend-already-started")
            state["backend_started"] = True
            details["f302_provider_executed"] = False
        elif kind == "detector_enable":
            if not state["backend_started"]:
                violations.append(f"event[{index}]:backend-not-started")
            else:
                state["detector_enabled"] = True
        elif kind == "cac_start":
            channel = state["plan"]["primary_channel"]
            if not state["detector_enabled"]:
                violations.append(f"event[{index}]:detector-not-enabled")
            elif not state["plan"]["dfs_required"]:
                violations.append(f"event[{index}]:cac-on-non-dfs-channel")
            elif at_ms < state["nop_until"].get(channel, 0):
                violations.append(f"event[{index}]:cac-started-during-nop")
            else:
                state["cac_started_at"] = at_ms
                state["tx_allowed"] = False
                state["evacuation_required"] = False
        elif kind == "cac_complete":
            started = state["cac_started_at"]
            if started is None:
                violations.append(f"event[{index}]:cac-not-active")
            elif at_ms - started < state["plan"]["cac_required_ms"]:
                violations.append(f"event[{index}]:cac-completed-too-early")
            else:
                state["cac_started_at"] = None
                state["tx_allowed"] = True
        elif kind == "poll":
            if not state["detector_enabled"]:
                violations.append(f"event[{index}]:poll-with-detector-disabled")
            vector = event.get("vector")
            if not isinstance(vector, dict):
                raise ValueError(f"events[{index}].vector must be an object")
            if vector.get("region") != state["plan"]["radar_region"]:
                violations.append(f"event[{index}]:vector-region-mismatch")
            if vector.get("channel") != state["plan"]["primary_channel"]:
                violations.append(f"event[{index}]:vector-channel-mismatch")
            if vector.get("bandwidth_mhz") != state["plan"]["bandwidth_mhz"]:
                violations.append(f"event[{index}]:vector-bandwidth-mismatch")
            vector_result = F303.run_vector(vector)
            details["vector_result"] = vector_result
            if not vector_result["expectations"]["pass"]:
                vector_failures.append(str(vector.get("name", f"event-{index}")))
            if vector_result["dispatch"]["mark_radar_callback_fired"]:
                channel = state["plan"]["primary_channel"]
                state["radar_callback_count"] += 1
                state["radar_channels"].add(channel)
                state["nop_registered"].add(channel)
                state["nop_until"][channel] = max(state["nop_until"].get(channel, 0), at_ms + NOP_MS)
                state["cac_started_at"] = None
                state["tx_allowed"] = False
                state["evacuation_required"] = True
        elif kind == "tx_probe":
            channel = state["plan"]["primary_channel"]
            actual = bool(
                state["tx_allowed"]
                and not state["evacuation_required"]
                and at_ms >= state["nop_until"].get(channel, 0)
            )
            expected = event.get("expected_allowed")
            if not isinstance(expected, bool):
                raise ValueError(f"events[{index}].expected_allowed must be boolean")
            details.update({"actual_allowed": actual, "expected_allowed": expected})
            if actual != expected:
                violations.append(f"event[{index}]:tx-probe-mismatch")
        elif kind == "nop_probe":
            channel = _require_int(event.get("channel"), f"events[{index}].channel")
            actual = at_ms < state["nop_until"].get(channel, 0)
            expected = event.get("expected_active")
            if not isinstance(expected, bool):
                raise ValueError(f"events[{index}].expected_active must be boolean")
            details.update({"channel": channel, "actual_active": actual, "expected_active": expected})
            if actual != expected:
                violations.append(f"event[{index}]:nop-probe-mismatch")
        elif kind == "channel_switch":
            target = {
                "country": "ES",
                "radar_region": "eu",
                "channel": event.get("channel"),
                "bandwidth_mhz": event.get("bandwidth_mhz"),
            }
            if "secondary_channel" in event:
                target["secondary_channel"] = event["secondary_channel"]
            target_plan = build_channel_plan(target)
            target_channel = target_plan["primary_channel"]
            if at_ms < state["nop_until"].get(target_channel, 0):
                violations.append(f"event[{index}]:channel-switch-target-in-nop")
            else:
                state["plan"] = target_plan
                state["cac_started_at"] = None
                state["evacuation_required"] = False
                state["tx_allowed"] = not target_plan["dfs_required"]
            details["target_plan"] = target_plan
        elif kind == "backend_stop":
            state["backend_started"] = False
            state["detector_enabled"] = False
            state["cac_started_at"] = None
            state["tx_allowed"] = False
        else:
            raise ValueError(f"unsupported event type: {kind!r}")

        timeline.append(_event_snapshot(state, event, details))

    expected = session.get("expected", {})
    if not isinstance(expected, dict):
        raise ValueError("expected must be an object")
    expectation_mismatches: list[str] = []
    observed = {
        "final_channel": state["plan"]["primary_channel"],
        "final_tx_allowed": state["tx_allowed"],
        "radar_callback_count": state["radar_callback_count"],
        "radar_channels": sorted(state["radar_channels"]),
        "nop_registered_channels": sorted(state["nop_registered"]),
        "violation_count": len(violations),
    }
    for key, wanted in expected.items():
        if key not in observed or observed[key] != wanted:
            expectation_mismatches.append(key)

    passed = not violations and not vector_failures and not expectation_mismatches
    return {
        "schema": RESULT_SCHEMA,
        "name": session.get("name", "unnamed"),
        "source": session.get("source"),
        "input_sha256": canonical_sha256(session),
        "status": "PASS" if passed else "FAIL",
        "classification_algorithm": "NOT_IMPLEMENTED",
        "classifier_inputs_are_oracles": True,
        "physical_rf_detection_proven": False,
        "f302_module_or_hardware_executed": False,
        "regulatory_model": "ES policy replay only; not regulatory certification",
        "provenance": provenance,
        "initial_channel_plan": plan,
        "timeline": timeline,
        "observed": observed,
        "violations": violations,
        "vector_expectation_failures": vector_failures,
        "expectation_mismatches": expectation_mismatches,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("session", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    session = json.loads(args.session.read_text(encoding="utf-8"))
    result = replay_session(session)
    rendered = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="ascii")
    else:
        print(rendered, end="")
    return 0 if result["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
