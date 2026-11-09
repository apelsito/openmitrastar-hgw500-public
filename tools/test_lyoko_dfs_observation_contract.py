"""Execute the candidate shell helper against local proc/WEXT fixtures only."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shlex
import subprocess

import pytest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "versions/lyoko-dfs-contract-v1/overlay/usr/sbin/om-dfs-status"
DEFAULT_STATUS = {
    "schema": "openmitrastar.radar-native-f316/v1",
    "backend_ready": "1",
    "authoritative_enable": "1",
    "dfs_enable": "1",
    "started": "1",
    "configured": "1",
    "polling": "1",
    "callbacks_ready": "1",
    "poll_runs": "42",
    "callback_invocations": "0",
    "channel": "116",  # Acquisition labels must not replace WEXT RF readback.
    "bandwidth": "80",
}


def shell_path(path: Path) -> str:
    path = path.resolve()
    if os.name != "nt":
        return str(path)
    return f"/mnt/{path.drive[0].lower()}/{path.as_posix().split(':', 1)[1].lstrip('/')}"


def run_shell(script: str) -> subprocess.CompletedProcess[str]:
    if os.name == "nt":
        command = ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "sh", "-c", script]
    else:
        command = ["sh", "-c", script]
    return subprocess.run(command, text=True, capture_output=True, check=False, timeout=30)


def write(path: Path, content: str) -> None:
    path.write_bytes(content.encode("ascii"))


@pytest.fixture
def observer(tmp_path):
    proc = tmp_path / "proc"
    proc.mkdir()
    write(proc / "status", "".join(f"{key}={value}\n" for key, value in DEFAULT_STATUS.items()))
    write(tmp_path / "uptime", "1234.98 2300.1\n")
    for name, value in {
        "get_cacstatus": "0", "chan_avail_stat": "2", "get_doth": "1",
        "get_mode": "11ac80Edge+", "get_region": "21317",
    }.items():
        write(tmp_path / name, value)
    write(tmp_path / "frequency", "5.26")
    write(tmp_path / "iwpriv", """#!/bin/sh
root=${OM_DFS_FIXTURE_ROOT:?}
case "$2" in get_cacstatus|chan_avail_stat|get_doth|get_mode|get_region) ;;
*) exit 95;; esac
printf '%s\\n' "$2" >> "$root/getters.log"
printf 'wifi0 %s:%s\\n' "$2" "$(cat "$root/$2")"
[ ! -f "$root/fail-$2" ]
""")
    write(tmp_path / "iwconfig", """#!/bin/sh
root=${OM_DFS_FIXTURE_ROOT:?}
[ "$#" = 1 ] || exit 95
printf 'wifi0 ESSID:"PRIVATE-SSID-NEVER-RETURN" Frequency:%s GHz Access Point: AA:BB:CC:DD:EE:FF\\n' "$(cat "$root/frequency")"
""")
    setup = run_shell(f"chmod 700 {shlex.quote(shell_path(tmp_path / 'iwpriv'))} {shlex.quote(shell_path(tmp_path / 'iwconfig'))}")
    assert setup.returncode == 0, setup.stderr

    def request(**overrides):
        environment = {
            "OM_RADAR_PROC_ROOT": shell_path(proc),
            "OM_DFS_UPTIME_FILE": shell_path(tmp_path / "uptime"),
            "OM_DFS_IWPRIV": shell_path(tmp_path / "iwpriv"),
            "OM_DFS_IWCONFIG": shell_path(tmp_path / "iwconfig"),
            "OM_DFS_FIXTURE_ROOT": shell_path(tmp_path),
            **overrides,
        }
        command = " ".join(f"{name}={shlex.quote(value)}" for name, value in environment.items())
        result = run_shell(f"{command} sh {shlex.quote(shell_path(HELPER))} status")
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert "PRIVATE-SSID-NEVER-RETURN" not in result.stdout
        assert "AA:BB:CC:DD:EE:FF" not in result.stdout
        return payload

    return tmp_path, request


def test_ready_and_complete_never_authorize_tx(observer):
    _, request = observer
    result = request()
    assert result["schema"] == "lyoko.radio.dfs-observation/v1"
    assert result["backend_ready"] is True
    assert result["detector"]["running"] is True
    assert result["detector"]["liveness_verified"] is False
    assert result["cac"]["state"] == "complete"
    assert result["cac"]["remaining_seconds"] is None
    assert result["tx"]["authorized"] is None
    assert result["dfs_tx_authorized"] is None
    assert result["controls"] == {"apply": False, "bypass": False}
    assert result["source"]["atomic"] is False
    assert result["observed_at_uptime_seconds"] == 1234


@pytest.mark.parametrize("key", ["started", "configured", "polling", "callbacks_ready", "dfs_enable"])
def test_ready_provider_does_not_hide_stopped_detector(observer, key):
    root, request = observer
    text = (root / "proc/status").read_text(encoding="ascii").replace(f"{key}=1", f"{key}=0")
    write(root / "proc/status", text)
    result = request()
    assert result["backend_ready"] is True
    assert result["detector"]["running"] is False
    assert result["dfs_tx_authorized"] is None


@pytest.mark.parametrize("cac,avail,state,active,required", [
    ("1", "8", "running", True, True),
    ("0", "8", "required", False, True),
    ("0", "2", "complete", False, False),
    ("1", "2", "inconsistent", None, None),
    ("1", "4", "inconsistent", None, None),
    ("garbled", "8", "unknown", None, None),
    ("0", "missing", "unknown", None, None),
])
def test_cac_readbacks_preserve_unknown_and_conflict(observer, cac, avail, state, active, required):
    root, request = observer
    write(root / "get_cacstatus", cac)
    write(root / "chan_avail_stat", avail)
    result = request()
    assert result["cac"]["state"] == state
    assert result["cac"]["active"] is active
    assert result["cac"]["required"] is required
    assert result["cac"]["remaining_seconds"] is None
    assert result["cac"]["required_seconds"] is None


def test_nop_is_current_channel_only_with_unknown_expiry(observer):
    root, request = observer
    write(root / "chan_avail_stat", "4")
    result = request()
    assert result["nop"]["active"] is True
    assert result["nop"]["entries"] == [{"channel": 52, "remaining_seconds": None}]
    assert result["nop"]["complete"] is False
    assert result["nop"]["scope"] == "current-channel-only"
    write(root / "chan_avail_stat", "2")
    result = request()
    assert result["nop"]["active"] is None
    assert result["nop"]["state"] == "unknown"
    assert result["nop"]["entries"] == []


def test_missing_provider_does_not_invent_readiness(observer):
    root, request = observer
    (root / "proc/status").unlink()
    result = request()
    assert result["available"] is False
    assert result["backend_ready"] is None
    assert result["detector"]["running"] is None
    assert result["cac"]["state"] == "complete"  # Independent qdrv observation.
    assert result["dfs_tx_authorized"] is None


def test_invalid_or_duplicate_provider_values_stay_unknown(observer):
    root, request = observer
    write(root / "proc/status", "schema=openmitrastar.radar-native-f316/v1\nbackend_ready=1\nbackend_ready=0\npoll_runs=" + "9" * 400 + "\n")
    result = request()
    assert result["backend_ready"] is None
    assert result["detector"]["polls"] is None
    assert result["detector"]["running"] is None


def test_unrecognised_provider_schema_is_not_interpreted(observer):
    root, request = observer
    write(root / "proc/status", "schema=future-unknown/v5\nbackend_ready=1\ndfs_enable=1\n")
    result = request()
    assert result["backend_ready"] is None
    assert result["available"] is False


def test_failed_getter_partial_output_is_discarded(observer):
    root, request = observer
    write(root / "fail-get_cacstatus", "1")
    result = request()
    assert result["cac"]["state"] == "unknown"
    assert result["cac"]["active"] is None


def test_missing_timeout_helper_skips_all_device_commands(observer):
    root, request = observer
    result = request(OM_DFS_TIMEOUT_COMMAND="lyoko-no-such-timeout-helper")
    assert not (root / "getters.log").exists()
    assert result["cac"]["state"] == "unknown"
    assert result["current_channel"] is None
    assert result["region"] is None
    assert result["policy_region"] == "ES"


@pytest.mark.parametrize("frequency,expected", [("5.18", 36), ("5.32", 64), ("5.60", 120), ("5.70", 140), ("missing", None)])
def test_channel_uses_rf_readback_not_shadow_label(observer, frequency, expected):
    root, request = observer
    write(root / "frequency", frequency)
    result = request()
    assert result["current_channel"] == expected
    assert result["channel"] == expected
    assert result["bandwidth_mhz"] == 80


def test_region_policy_is_not_hardware_readback(observer):
    root, request = observer
    write(root / "get_region", "0")
    result = request()
    assert result["region"] is None
    assert result["policy_region"] == "ES"


def test_non_dfs_channel_does_not_claim_cac_completed(observer):
    root, request = observer
    write(root / "frequency", "5.18")
    result = request()
    assert result["cac"]["state"] == "not-required"
    assert result["tx"]["authorized"] is None


def test_channel_outside_es_catalogue_does_not_invent_non_dfs_permission(observer):
    root, request = observer
    write(root / "frequency", "5.745")
    result = request()
    assert result["current_channel"] == 149
    assert result["current_channel_dfs"] is None
    assert result["cac"]["state"] == "unknown"
    assert result["dfs_tx_authorized"] is None


def test_compatibility_wrapper_preserves_status_invocation(tmp_path):
    write(tmp_path / "fake-status", "#!/bin/sh\nprintf '{\"operation\":\"%s\"}\\n' \"$1\"\n")
    fake = shlex.quote(shell_path(tmp_path / "fake-status"))
    wrapper = shlex.quote(shell_path(HELPER.with_name("om-radarctl")))
    setup = run_shell(f"chmod 700 {fake}")
    assert setup.returncode == 0, setup.stderr
    result = run_shell(f"OM_DFS_STATUS={fake} sh {wrapper}")
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"operation": "status"}
