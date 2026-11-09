#!/usr/bin/env python3
"""Static contract tests for the F316 external-radar/qdrv integration."""

from __future__ import annotations

import hashlib
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
QDRV_ROOT = ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag"
QDRV_RADAR = QDRV_ROOT / "qdrv/qdrv_radar.c"
QDRV_WLAN = QDRV_ROOT / "qdrv/qdrv_wlan.c"
IEEE80211_INPUT = QDRV_ROOT / "wlan/ieee80211_input.c"
DOC = ROOT / "docs/OPENMITRASTAR_F316_QDRV_DFS_INTEGRATION.md"

EXPECTED_SHA256 = {
    QDRV_RADAR: "c261b6777d9322a4baf641a37861bf588e754e5411f7f993ea16725d00c395dc",
    QDRV_WLAN: "f4def5f050cb8500efdd12103839c606a1641fef11e808734ce93beeeafb00fa",
    IEEE80211_INPUT: "0a9fe5e65d41cdfcc13cdbf063673935c79bfd082726067cf354f06a00cb4c45",
}


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def function_body(source: str, name: str) -> str:
    match = re.search(rf"\b{re.escape(name)}\s*\([^;]*?\)\s*\{{", source, re.S)
    assert match, f"function not found: {name}"
    start = source.find("{", match.start())
    depth = 0
    for index in range(start, len(source)):
        char = source[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start + 1 : index]
    raise AssertionError(f"unterminated function: {name}")


def assert_ordered(text: str, *needles: str) -> None:
    offset = 0
    for needle in needles:
        position = text.find(needle, offset)
        assert position >= 0, f"missing or out-of-order token: {needle}"
        offset = position + len(needle)


def test_audited_linux510_sources_are_exact() -> None:
    for path, expected in EXPECTED_SHA256.items():
        assert path.is_file(), path
        assert sha256(path) == expected, f"source drift requires contract re-audit: {path}"


def test_start_contract_orders_provider_setup_before_registration() -> None:
    body = function_body(read(QDRV_RADAR), "sys_start_radarmod")
    assert_ordered(
        body,
        "radar_start(region)",
        "radar_set_bw(ic->ic_radar_bw)",
        "sys_disable_rdetection()",
        "radar_register(mark_radar)",
        "radar_register_is_dfs_chan(qdrv_radar_is_dfs_chan)",
        "radar_register_is_dfs_weather_chan(qdrv_radar_is_dfs_weather_chan)",
    )
    assert "return region_enabled" in body


def test_doth_and_dfs_are_both_required_for_detection() -> None:
    body = function_body(read(QDRV_RADAR), "qdrv_radar_is_rdetection_required")
    assert "bool doth = ic->ic_flags & IEEE80211_F_DOTH" in body
    assert_ordered(body, "if (doth)", "chan->ic_flags & IEEE80211_CHAN_DFS", "rdetect = true")
    assert "QDRV_LF_DFS_DONTCAREDOTH" in body


def test_new_dfs_channel_blocks_tx_before_cac_and_arms_after_channel_set() -> None:
    source = read(QDRV_RADAR)
    before = function_body(source, "qdrv_radar_before_newchan")
    after = function_body(source, "qdrv_radar_on_newchan")
    assert_ordered(before, "if (rdetect)", "sys_disable_xmit()", "sys_disable_rdetection()")
    assert_ordered(after, "radar_set_chan(new_chan->ic_ieee)", "rdetect =", "start_cac()")
    assert_ordered(after, "start_cac()", "radar_get_status()", "sys_enable_rdetection()")
    assert_ordered(after, "} else {", "sys_enable_xmit()", "sys_disable_rdetection()")


def test_standard_weather_and_nop_periods_are_exact() -> None:
    source = read(QDRV_RADAR)
    assert "#define CAC_PERIOD\t\t(70 * HZ)" in source
    assert "#define CAC_WEATHER_PERIOD_EU\t(600 * HZ)" in source
    assert "#define QDRV_RADAR_DFLT_NONOCCUPY_PERIOD\t1800" in read(QDRV_ROOT / "qdrv/qdrv_radar.h")
    start_cac = function_body(source, "start_cac")
    assert_ordered(
        start_cac,
        "ieee80211_is_on_weather_channel(ic, cur_chan)",
        "CAC_WEATHER_PERIOD_EU",
        "CAC_PERIOD",
    )


def test_cac_marks_block_blocks_tx_and_completion_unblocks() -> None:
    source = read(QDRV_RADAR)
    start = function_body(source, "start_cac")
    complete = function_body(source, "cac_completed_action")
    before = function_body(source, "qdrv_radar_before_newchan")
    assert "IEEE80211_CHAN_DFS_CAC_IN_PROGRESS" in start
    assert "QDRV_WLAN_SM_STATE_CAC_ACTIVE" in start
    assert_ordered(before, "if (rdetect)", "sys_disable_xmit()")
    assert_ordered(
        complete,
        "sys_enable_xmit()",
        "IEEE80211_CHAN_DFS_CAC_DONE",
        "~IEEE80211_CHAN_DFS_CAC_IN_PROGRESS",
        "IEEE80211_CHANNEL_STATUS_AVAILABLE",
    )


def test_mark_radar_callback_enters_qdrv_without_channel_metadata() -> None:
    source = read(QDRV_RADAR)
    callback = function_body(source, "mark_radar")
    detected = function_body(source, "qdrv_radar_detected")
    assert "qdrv_radar_detected(qdrv_radar_cb.ic, 0)" in callback
    assert "if (!qdrv_radar_configured)" in detected
    assert "if (!qdrv_radar_cb.enabled)" in detected
    assert "if (ic != qdrv_radar_cb.ic)" in detected
    assert_ordered(detected, "stop_cac()", "qdrv_radar_is_rdetection_required(ic->ic_curchan)")


def test_detection_orders_nop_detector_stop_and_evacuation() -> None:
    body = function_body(read(QDRV_RADAR), "qdrv_radar_detected")
    action_start = body.index("/* set radar_found_flag")
    action = body[action_start:]
    assert_ordered(
        action,
        "start_nonoccupy(chan_idx)",
        "stop_cac()",
        "if (!rdetect)",
        "sys_disable_rdetection()",
        "dfs_action(local_new_ieee, radar_detected_during_cac)",
    )


def test_nop_expiry_requires_new_cac() -> None:
    source = read(QDRV_RADAR)
    start = function_body(source, "start_nonoccupy")
    expire = function_body(source, "nonoccupy_expire_action")
    assert "chan->ic_flags |= IEEE80211_CHAN_RADAR" in start
    assert "expires = jiffies + ic->ic_non_occupancy_period" in start
    assert "IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_RADAR_DETECTED" in start
    assert "chan->ic_flags &= ~IEEE80211_CHAN_RADAR" in expire
    assert "IEEE80211_CHANNEL_STATUS_NOT_AVAILABLE_CAC_REQUIRED" in expire


def test_occupied_20_40_80_blocks_propagate_radar_and_cac_state() -> None:
    source = read(QDRV_WLAN)
    availability = function_body(source, "qdrv_mark_channel_availability_status")
    cac = function_body(source, "qdrv_mark_channel_dfs_cac_status")
    check = function_body(source, "qdrv_check_channel")

    for width in ("BW_HT20", "BW_HT40", "BW_HT80"):
        assert width in availability
        assert width in cac
        assert width in check

    assert availability.count("->ic_flags |= IEEE80211_CHAN_RADAR") >= 6
    assert availability.count("IEEE80211_CHAN_DFS_CAC_DONE") >= 12
    assert cac.count("ic_flags |= cac_flag") >= 7
    assert check.count("qdrv_chan_has_radar") >= 7
    for position in ("IEEE80211_CHAN_VHT80_LL", "IEEE80211_CHAN_VHT80_LU", "IEEE80211_CHAN_VHT80_UL", "IEEE80211_CHAN_VHT80_UU"):
        assert position in availability
        assert position in cac
        assert position in check


def test_weather_decision_covers_wide_channel_flags() -> None:
    body = function_body(read(QDRV_ROOT / "wlan/ieee80211.c"), "ieee80211_is_on_weather_channel")
    assert "IEEE80211_CHAN_WEATHER" in body
    assert "IEEE80211_CHAN_WEATHER_40M" in body
    assert "IEEE80211_CHAN_WEATHER_80M" in body
    assert "cur_bw >= BW_HT40" in body
    assert "cur_bw >= BW_HT80" in body


def test_evacuation_uses_mandatory_tx_stop_csa() -> None:
    radar = function_body(read(QDRV_RADAR), "dfs_action_after_newchan_select")
    csa = function_body(read(IEEE80211_INPUT), "ieee80211_dfs_send_csa")
    assert "ieee80211_dfs_send_csa(vap, new_chan->ic_ieee)" in radar
    assert "IEEE80211_CSW_REASON_DFS" in csa
    assert "IEEE80211_CSA_MUST_STOP_TX" in csa


def test_current_qdrv_failure_modes_are_explicitly_documented() -> None:
    radar = read(QDRV_RADAR)
    start = function_body(radar, "sys_start_radarmod")
    enable = function_body(radar, "qdrv_radar_enable_radar_detection")
    disable = function_body(radar, "qdrv_radar_disable")

    assert "radar_register(mark_radar);" in start
    assert "if (radar_register" not in start
    assert "radar_set_chan(ic->ic_curchan->ic_ieee);" in enable
    assert "if (radar_set_chan" not in enable
    assert_ordered(disable, "sys_disable_rdetection()", "sys_enable_xmit()")

    doc = read(DOC)
    for identifier in range(1, 11):
        assert f"FM-{identifier:02d}" in doc


def test_document_covers_every_requested_contract_area() -> None:
    doc = read(DOC)
    for heading in (
        "## Provider ABI Contract",
        "### Start",
        "## DOTH, CAC And TX Contract",
        "## Detection, Evacuation And NOP",
        "## Occupied 20/40/80 MHz Blocks",
        "## Known Failure Modes",
        "## F316 Acceptance Contract",
    ):
        assert heading in doc
    for term in ("70 * HZ", "600 * HZ", "1,800 seconds", "mark_radar()", "MUST_STOP_TX"):
        assert term in doc


def test_contract_test_is_offline_and_read_only() -> None:
    source = Path(__file__).read_text(encoding="utf-8").lower()
    forbidden_parts = (
        ("para", "miko"),
        ("serial", ".serial"),
        ("com", "3"),
        ("192.168", ".1.90"),
        ("/dev/", "mtd"),
        ("flash", "_erase"),
        ("nand", "write"),
        ("mtd", "_debug"),
        ("tf", "tp"),
        ("sub", "process"),
    )
    for parts in forbidden_parts:
        forbidden = "".join(parts)
        assert forbidden not in source
