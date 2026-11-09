#!/usr/bin/env python3
"""Audit F301 DFS/regulatory support and emit a hardware-safe ES gate plan.

This tool is deliberately local and plan-only. It reads the exact F301
artifact, extracted SquashFS files and existing physical evidence. It never
opens SSH/UART, changes a radio, starts TFTP, reboots, or writes an MTD.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEVICE_ID = "hgw500bna-qcv2-a2-primary"
F301_DIR = Path.home() / ".openmitrastar/devices" / DEVICE_ID / "firmware/f301-device-bound"
F301_BASE = f"openmitrastar-linux510-f301-{DEVICE_ID}-PRIVATE-NO-FLASH"
F301_MANIFEST = F301_DIR / "manifest.json"
F301_CANDIDATE = F301_DIR / f"{F301_BASE}.webformat.bin"
F301_ROOTFS = F301_DIR / f"{F301_BASE}.rootfs.squashfs"
F301_STATE_DOC = ROOT / "docs/OPENMITRASTAR_F301_CURRENT_STATE.md"
F301_CAMPAIGN = ROOT / "outputs/f3-certification/f301-integrated-regression-20260904T121108Z/campaign.json"
CHANNEL_POLICY = ROOT / "docs/LYOKO_CHANNEL_POLICY_ES.md"
RADAR_COMPAT_SOURCE = ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_radar_compat.c"
QDRV_MAKEFILE = ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/Makefile"

EXPECTED_CANDIDATE_BYTES = 5_267_456
EXPECTED_CANDIDATE_SHA256 = "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262"
EXPECTED_QDRV_SHA256 = "0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff"
EXPECTED_REGDB_SHA256 = "2263cc2407d6e0d1543aa55bd7d2b9b98598301c59b4d3dca40701132f044365"
EXPECTED_ES_POWER_SHA256 = "1f884017d214bf185a82bd3ed991f5095251474d9336c9c3af07f2a36aaf28d5"

IMMEDIATE_CHANNELS = {36, 40, 44, 48}
DFS_CHANNELS = {52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140}
ALL_CHANNELS = IMMEDIATE_CHANNELS | DFS_CHANNELS
WEATHER_20MHZ_CHANNELS = {120, 124, 128}
NORMAL_CAC_SECONDS = 70
WEATHER_CAC_SECONDS = 600
NON_OCCUPANCY_SECONDS = 1800
POST_CAC_MONITOR_SECONDS = 120

PAIRS_40 = (
    (36, 40), (44, 48), (52, 56), (60, 64),
    (100, 104), (108, 112), (116, 120), (124, 128), (132, 136),
)
BLOCKS_80 = (
    (36, 40, 44, 48),
    (52, 56, 60, 64),
    (100, 104, 108, 112),
    (116, 120, 124, 128),
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def feature_value(rootfs: Path, name: str) -> str:
    path = rootfs / "etc/openmitrastar/features" / name
    return path.read_text(encoding="ascii").strip() if path.is_file() else ""


def to_wsl_path(path: Path) -> str:
    value = path.resolve()
    drive = value.drive.rstrip(":").lower()
    tail = value.as_posix()[3:]
    return f"/mnt/{drive}/{tail}"


def extract_rootfs(rootfs: Path, destination: Path, distro: str) -> None:
    command = (
        "set -eu; "
        f"rm -rf '{to_wsl_path(destination)}'; "
        f"mkdir -p '{to_wsl_path(destination.parent)}'; "
        f"unsquashfs -no-progress -d '{to_wsl_path(destination)}' "
        f"'{to_wsl_path(rootfs)}' >/dev/null"
    )
    run = subprocess.run(
        ["wsl.exe", "-d", distro, "-u", "root", "-e", "bash", "--noprofile", "--norc", "-c", command],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if run.returncode:
        raise RuntimeError(run.stderr or run.stdout or "unsquashfs failed")


def classify_channel(primary: int, bandwidth: int) -> dict[str, Any]:
    reasons: list[str] = []
    occupied: tuple[int, ...] = ()
    secondary_readback_required = bandwidth == 40

    if primary not in ALL_CHANNELS:
        reasons.append("CHANNEL_NOT_IN_F301_ES_POLICY")
    if bandwidth not in (20, 40, 80):
        reasons.append("BANDWIDTH_NOT_SUPPORTED")

    if not reasons:
        if bandwidth == 20:
            occupied = (primary,)
        elif bandwidth == 40:
            occupied = next((pair for pair in PAIRS_40 if primary in pair), ())
            if not occupied:
                reasons.append("INCOMPLETE_40MHZ_BLOCK_OR_SECONDARY_UNKNOWN")
        else:
            occupied = next((block for block in BLOCKS_80 if primary in block), ())
            if not occupied:
                reasons.append("INCOMPLETE_80MHZ_BLOCK_REQUIRES_CHANNEL_144")

    dfs_required = bool(set(occupied) & DFS_CHANNELS)
    weather_intersection = bool(set(occupied) & WEATHER_20MHZ_CHANNELS)
    if reasons:
        channel_class = "invalid"
        cac_seconds = None
    elif not dfs_required:
        channel_class = "immediate-non-dfs"
        cac_seconds = 0
    elif weather_intersection:
        channel_class = "dfs-weather-radar"
        cac_seconds = WEATHER_CAC_SECONDS
    else:
        channel_class = "dfs-standard"
        cac_seconds = NORMAL_CAC_SECONDS

    return {
        "primary_channel": primary,
        "bandwidth_mhz": bandwidth,
        "occupied_20mhz_channels": list(occupied),
        "channel_class": channel_class,
        "dfs_required": dfs_required,
        "weather_radar_intersection": weather_intersection,
        "cac_seconds_minimum": cac_seconds,
        "gate_observation_seconds": None if cac_seconds is None else cac_seconds + 15,
        "post_cac_monitor_seconds": POST_CAC_MONITOR_SECONDS if dfs_required else 0,
        "non_occupancy_seconds": NON_OCCUPANCY_SECONDS if dfs_required else 0,
        "secondary_channel_readback_required": secondary_readback_required,
        "valid": not reasons,
        "reasons": reasons,
    }


def collect_audit(rootfs: Path) -> dict[str, Any]:
    checks: dict[str, bool] = {}
    details: dict[str, Any] = {}

    manifest = read_json(F301_MANIFEST)
    campaign = read_json(F301_CAMPAIGN)
    state_doc = F301_STATE_DOC.read_text(encoding="utf-8")
    policy = CHANNEL_POLICY.read_text(encoding="utf-8")
    compat = RADAR_COMPAT_SOURCE.read_text(encoding="utf-8")
    makefile = QDRV_MAKEFILE.read_text(encoding="utf-8")

    candidate_hash = sha256(F301_CANDIDATE)
    checks["candidate_size_pinned"] = F301_CANDIDATE.stat().st_size == EXPECTED_CANDIDATE_BYTES
    checks["candidate_hash_pinned"] = candidate_hash == EXPECTED_CANDIDATE_SHA256
    checks["manifest_hash_matches_candidate"] = manifest["artifacts"]["webformat"]["sha256"] == candidate_hash
    checks["manifest_dfs_read_only"] = manifest["dfs_observability"]["mode"] == "read-only"
    checks["manifest_dfs_fail_closed"] = manifest["dfs_observability"]["policy"] == "fail-closed"
    checks["manifest_radar_not_ready"] = manifest["dfs_observability"]["radar_backend_ready"] is False
    checks["manifest_no_dfs_writes"] = manifest["dfs_observability"]["write_operations"] is False
    checks["current_state_records_installed_f301"] = (
        "F301 is installed persistently in physical `mtd4/linux_live`" in state_doc
        and EXPECTED_CANDIDATE_SHA256 in state_doc
    )

    dfs = campaign["final_diagnostics"]["dfs"]
    checks["physical_campaign_passed"] = campaign["status"] == "PASS"
    checks["physical_region_es"] = dfs["region"] == "ES" and dfs["region_code"] == 21317
    checks["physical_driver_dfs_region_not_ready"] = dfs["driver_reg_is_eu"] == 0
    checks["physical_doth_enabled"] = dfs["driver_raw"]["doth"] == 1
    checks["physical_current_channel_non_dfs"] = dfs["current_channel"] == 36 and dfs["current_channel_dfs"] is False
    checks["physical_dfs_write_blocked"] = dfs["writable"] is False and dfs["blocked_reason"] == "dfs-radar-backend-unavailable"
    checks["physical_no_fatal_markers"] = campaign["final_diagnostics"]["fatal_count"] == 0

    qdrv = rootfs / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/radio5g/qdrv.ko"
    regdb = rootfs / "etc/qtn_regulatory_db.bin"
    power = rootfs / "etc/power_tables/tx_power_QSR1000_es.txt"
    radio_start = (rootfs / "usr/sbin/om-radio5-start").read_text(encoding="utf-8")
    radioctl = (rootfs / "usr/sbin/om-radioctl").read_text(encoding="utf-8")
    qtnctl = (rootfs / "usr/sbin/om-qtnctl").read_text(encoding="utf-8")
    module_names = {path.name for path in qdrv.parent.glob("*.ko")}

    checks["qdrv_hash_pinned"] = qdrv.is_file() and sha256(qdrv) == EXPECTED_QDRV_SHA256
    checks["qdrv_contains_fail_closed_marker"] = (
        qdrv.is_file() and b"proprietary radar backend is unavailable" in qdrv.read_bytes()
    )
    checks["regdb_hash_pinned"] = regdb.is_file() and sha256(regdb) == EXPECTED_REGDB_SHA256
    checks["es_power_table_hash_pinned"] = power.is_file() and sha256(power) == EXPECTED_ES_POWER_SHA256
    checks["dfs_feature_disabled"] = feature_value(rootfs, "qtn-dfs-control-v1") == "OPENMITRASTAR_QTN_DFS_CONTROL=0"
    checks["general_qtn_mutation_disabled"] = feature_value(rootfs, "qtn-native-control-v1") == "OPENMITRASTAR_QTN_NATIVE_CONTROL=0"
    checks["native_radar_module_absent"] = "qtn_radar_native.ko" not in module_names
    checks["qdrv_links_fail_closed_compat"] = "qdrv_radar_compat.o" in makefile
    checks["compat_radar_start_returns_false"] = (
        "bool radar_start(const char *region)" in compat
        and "proprietary radar backend is unavailable" in compat
        and "return false;" in compat
    )
    checks["compat_dfs_requirement_unknown"] = "return DFS_RQMT_UNKNOWN;" in compat
    checks["compat_registration_is_unsupported"] = compat.count("return -EOPNOTSUPP;") >= 5
    checks["boot_sets_es_region"] = "iwpriv-qtn wifi0 region 21317" in radio_start
    checks["boot_enables_80211h_tpc"] = (
        "iwpriv-qtn wifi0 doth 1" in radio_start
        and "iwpriv-qtn wifi0 tpc 1" in radio_start
        and "iwpriv-qtn wifi0 tpc_interval 30" in radio_start
    )
    checks["backend_requires_feature_and_native_ready"] = (
        "qtn-dfs-control-v1" in radioctl
        and "/sys/module/qtn_radar_native/parameters/ready" in radioctl
        and "qtn-dfs-control-v1" in qtnctl
        and "/sys/module/qtn_radar_native/parameters/ready" in qtnctl
    )
    checks["policy_has_cac_and_nop"] = "600-second CAC" in policy and "1,800 seconds" in policy

    details.update({
        "candidate_sha256": candidate_hash,
        "qdrv_sha256": sha256(qdrv) if qdrv.is_file() else None,
        "regdb_sha256": sha256(regdb) if regdb.is_file() else None,
        "es_power_table_sha256": sha256(power) if power.is_file() else None,
        "physical_readback": {
            "region": dfs["region"],
            "region_code": dfs["region_code"],
            "driver_reg_is_eu": dfs["driver_reg_is_eu"],
            "channel": dfs["current_channel"],
            "bandwidth_mhz": dfs["bandwidth_mhz"],
            "doth": dfs["driver_raw"]["doth"],
            "cac_status": dfs["driver_raw"]["cac_status"],
            "dfs_switch": dfs["driver_raw"]["dfs_switch"],
            "dfs_csa_count": dfs["driver_raw"]["dfs_csa_count"],
            "channel_availability": dfs["driver_raw"]["channel_availability"],
            "writable": dfs["writable"],
        },
    })
    failed = sorted(name for name, passed in checks.items() if not passed)
    return {
        "status": "PASS" if not failed else "FAIL",
        "checks": checks,
        "failed_checks": failed,
        "details": details,
        "support_classification": {
            "es_region_and_calibrated_power": "PHYSICALLY_OBSERVED_ON_CHANNEL_36",
            "non_dfs_36_48": "TRAFFIC_PROVEN_ON_36; OTHER_IMMEDIATE_CHANNELS_REQUIRE_GATE",
            "dfs_observability": "AVAILABLE_READ_ONLY",
            "dfs_cac_radar_nop": "BLOCKED_NATIVE_RADAR_BACKEND_ABSENT",
            "radar_event_injection": "CAN_ONLY_PROVE_EVACUATION_PLUMBING; NOT_RF_DETECTION",
            "regulatory_certification": "NOT_PROVEN",
        },
        "known_contract_gaps": [
            "Physical get_reg_is_eu is 0 even though the configured region reads ES/21317.",
            "DOTH/TPC enabled state does not prove that a radar detector is running.",
            "The current CAC label is based on primary channel only, not the complete 40/80 MHz occupied block.",
            "The current 80 MHz mode map admits primaries 132/136/140 although channel 144 is absent from the ES contract.",
            "CAC transmit suppression, in-service radar monitoring, evacuation and NOP have no physical F301 proof.",
        ],
    }


def physical_gate_plan(channel: int, bandwidth: int, audit: dict[str, Any]) -> dict[str, Any]:
    target = classify_channel(channel, bandwidth)
    audit_pass = audit["status"] == "PASS"
    if not audit_pass:
        eligibility = "BLOCKED_LOCAL_EVIDENCE_INTEGRITY"
    elif not target["valid"]:
        eligibility = "BLOCKED_CHANNEL_WIDTH_CONTRACT"
    elif target["dfs_required"]:
        eligibility = "BLOCKED_DFS_RADAR_BACKEND_UNAVAILABLE"
    else:
        eligibility = "READY_FOR_CONTROLLED_NON_DFS_PHYSICAL_GATE"

    immediate_steps = [
        "Pin exact installed F301 identity and snapshot SSID/channel/bandwidth/mode without exposing the PSK.",
        "Keep wired management, UART observation and an external rollback watchdog available before mutation.",
        "Plan exactly one channel/bandwidth change; reject any region, power-table, bridge, qdrv or firmware change.",
        "Apply through the existing bounded om-qtnctl path with the temporary material-trial feature gate.",
        "Verify ES region 21317, DOTH=1, TPC=1, hostapd PONG, wifi0 in br0 and 2.4 GHz still ready.",
        "Associate AELITA to 5 GHz, prove BSSID/channel/PHY, transfer 32 MiB each direction and hold traffic for 120 seconds.",
        "Restore the exact original channel/bandwidth, verify client and management recovery, then disarm the watchdog.",
    ]
    dfs_steps = [
        "Do not select or transmit on a DFS target while qdrv_radar_compat remains linked or qtn_radar_native ready is absent.",
        "A future versioned mtd4 candidate must provide a native Linux 5.10 radar backend and retain F301 as exact rollback.",
        "Read the complete occupied 20 MHz block from the driver; for 40 MHz the secondary-channel readback is mandatory.",
        "Prove ES/EU classification, native callbacks, continuous detector state and an empty NOP before channel selection.",
        "Prove zero AP beacon/association and no TX traffic for the full CAC plus the observation margin.",
        "After CAC, prove in-service radar monitoring, association and 32 MiB bidirectional traffic plus a 120-second soak.",
        "Use synthetic doth_radar only to test CSA/evacuation/NOP plumbing; it cannot certify physical radar detection.",
        "Final radar PASS requires an authorized calibrated radar source, automatic evacuation and 1800-second NOP evidence.",
        "On any missing readback, unexpected TX, fatal marker or management loss, restore the original config or exact F301 image.",
    ]
    return {
        "eligibility": eligibility,
        "target": target,
        "hardware_execution_in_this_tool": False,
        "immediate_non_dfs_gate": {
            "status": "IMPLEMENTABLE_WITH_EXISTING_F301_BACKEND" if audit_pass else "BLOCKED",
            "steps": immediate_steps,
            "pass_criteria": [
                "exact F301 hash and original radio snapshot captured",
                "region ES/21317, DOTH and TPC preserved",
                "5 GHz client proves target channel and WPA2/CCMP",
                "32 MiB downstream and upstream plus 120-second connected soak pass",
                "2.4 GHz, Ethernet, SSH and br0 remain healthy",
                "original channel/bandwidth restore verifies exactly",
                "zero fatal ARC/QMAC/MuC/DMA markers and zero MTD writes",
            ],
        },
        "dfs_gate": {
            "status": "BLOCKED" if audit["support_classification"]["dfs_cac_radar_nop"].startswith("BLOCKED") else "READY",
            "blocker": "F301 links qdrv_radar_compat; radar_start returns false and no qtn_radar_native module is packaged.",
            "steps": dfs_steps,
            "pass_criteria": [
                "native Linux 5.10 radar backend is loaded, ready and continuously running",
                "ES maps to EU DFS and the complete occupied block is legal for the selected bandwidth",
                "TX and beaconing stay suppressed for the complete CAC",
                "CAC lasts at least 70 seconds, or 600 seconds when the occupied block intersects 5600-5650 MHz",
                "post-CAC in-service monitoring, association and traffic pass",
                "calibrated radar causes automatic evacuation and 1800-second NOP registration",
                "rollback restores exact F301 health after any failure",
            ],
        },
        "outcomes": {
            "PASS": "All criteria for the selected class pass and exact restoration is verified.",
            "BLOCKED": "A prerequisite is absent before RF mutation; no target-channel transmission occurs.",
            "FAIL": "A mutation began but a health, traffic, CAC, radar or restore criterion failed; rollback is mandatory.",
        },
        "blocked_criteria": [
            "local artifact or evidence integrity check fails",
            "selected channel-width block is incomplete or not admitted by the ES contract",
            "driver EU/DFS classification is unavailable",
            "native radar module is absent, not ready or stops during CAC/in-service monitoring",
            "the target or any occupied subchannel is in NOP",
            "no authorized calibrated radar source is available for final detector certification",
        ],
        "rollback": {
            "runtime_trial": "Arm the router-local watchdog before mutation; restore the exact captured SSID/channel/bandwidth and verify convergence before disarming it.",
            "management_loss": "Do not stack another mutation. Observe UART and let the armed local rollback finish; require exact F301 health before retrying.",
            "future_firmware_candidate": "If a native-radar mtd4 candidate fails, restore the exact pinned F301 image through the existing guarded Bootbase path and verify full-slot/protected-partition evidence.",
            "never_write": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5", "logical mtd6"],
        },
    }


def build_result(rootfs: Path, channel: int, bandwidth: int) -> dict[str, Any]:
    audit = collect_audit(rootfs)
    return {
        "schema": "openmitrastar.f301-dfs-es-plan/v1",
        "mode": "LOCAL_READ_ONLY_PLAN",
        "firmware": "F301",
        "country": "ES",
        "legal_note": "Engineering policy derived only from local project evidence; not legal advice.",
        "audit": audit,
        "selected_gate": physical_gate_plan(channel, bandwidth, audit),
        "channel_matrix": [
            classify_channel(channel_id, width)
            for width in (20, 40, 80)
            for channel_id in sorted(ALL_CHANNELS)
        ],
        "hardware_actions": {
            "ssh": False,
            "uart": False,
            "tftp": False,
            "radio_mutation": False,
            "reboot": False,
            "flash": False,
            "mtd_writes": 0,
        },
        "evidence": [
            str(F301_MANIFEST.relative_to(ROOT)) if F301_MANIFEST.is_relative_to(ROOT) else str(F301_MANIFEST),
            str(F301_STATE_DOC.relative_to(ROOT)),
            str(F301_CAMPAIGN.relative_to(ROOT)),
            str(CHANNEL_POLICY.relative_to(ROOT)),
            str(RADAR_COMPAT_SOURCE.relative_to(ROOT)),
            str(QDRV_MAKEFILE.relative_to(ROOT)),
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--channel", type=int, default=100)
    parser.add_argument("--bandwidth", type=int, default=20)
    parser.add_argument("--rootfs-tree", type=Path)
    parser.add_argument("--distro", default="podman-mem9-tidb")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--require-dfs-ready", action="store_true")
    args = parser.parse_args()

    temporary: tempfile.TemporaryDirectory[str] | None = None
    try:
        if args.rootfs_tree:
            rootfs = args.rootfs_tree.resolve()
        else:
            temporary = tempfile.TemporaryDirectory(prefix="f301-dfs-plan-", dir=ROOT / ".codex_tmp")
            rootfs = Path(temporary.name) / "rootfs"
            extract_rootfs(F301_ROOTFS, rootfs, args.distro)
        result = build_result(rootfs, args.channel, args.bandwidth)
    finally:
        if temporary is not None:
            temporary.cleanup()

    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        output = args.output if args.output.is_absolute() else ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(payload, encoding="utf-8")
    print(payload, end="")
    if result["audit"]["status"] != "PASS":
        return 2
    if args.require_dfs_ready and result["selected_gate"]["target"]["dfs_required"]:
        return 3
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
