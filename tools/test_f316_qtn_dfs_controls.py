from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import shlex
import sys
import tempfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
F313_TEST = ROOT / "versions/lyoko-foundation-6.8.0-f313-qtn-controls/tests/test_f313_qtn_controls.py"
F316 = ROOT / "versions/lyoko-foundation-7.0.0-f316-radar-native"
QTNCTL = F316 / "overlay/usr/sbin/om-qtnctl"
RADIOCTL = F316 / "overlay/usr/sbin/om-radioctl"


def load_helpers():
    spec = importlib.util.spec_from_file_location("f316_qtn_test_helpers", F313_TEST)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.QTNCTL = QTNCTL
    module.RADIOCTL = RADIOCTL
    module.TRANSACTION = F316 / "overlay/usr/sbin/om-config-transaction"
    return module


def create_f316_fake(root: Path, *, dfs_ready: bool = True):
    helpers = load_helpers()
    env, qtnctl = helpers.create_fake_qtn(root)
    tmp = helpers.wsl_path(root)
    helpers.write_ascii(
        root / "bin/iwconfig",
        r'''#!/bin/sh
root=${OM_TEST_ROOT:?}
case "${2:-}" in
essid) printf '%s\n' "$3" > "$root/ssid" ;;
channel)
  printf 'channel %s\n' "$3" >> "$root/set.log"
  printf '%s\n' "$3" > "$root/channel"
  case "$3" in
  52|56|60|64|100|104|108|112|116|120|124|128|132|136|140)
    status=$(cat "$root/next_avail_status" 2>/dev/null || printf 8)
    printf '%s\n' "$status" > "$root/chan_avail_status"
    if [ "$status" = 8 ]; then
      behavior=$(cat "$root/cac_behavior" 2>/dev/null || printf complete)
      if [ "$behavior" = complete ]; then printf '1\n0\n' > "$root/cac_sequence"; else : > "$root/cac_sequence"; fi
      printf '1\n' > "$root/cac_status"
    else
      : > "$root/cac_sequence"; printf '0\n' > "$root/cac_status"
    fi
    ;;
  *) : > "$root/cac_sequence"; printf '0\n' > "$root/cac_status"; printf '2\n' > "$root/chan_avail_status" ;;
  esac
  ;;
*)
  channel=$(cat "$root/channel")
  case "$channel" in
  36) freq=5.18;; 40) freq=5.20;; 44) freq=5.22;; 48) freq=5.24;;
  52) freq=5.26;; 56) freq=5.28;; 60) freq=5.30;; 64) freq=5.32;;
  100) freq=5.50;; 104) freq=5.52;; 108) freq=5.54;; 112) freq=5.56;;
  116) freq=5.58;; 120) freq=5.60;; 124) freq=5.62;; 128) freq=5.64;;
  132) freq=5.66;; 136) freq=5.68;; 140) freq=5.70;; *) exit 1;; esac
  printf 'wifi0 IEEE 802.11ac ESSID:"%s" Frequency:%s GHz Tx-Power=21 dBm\n' "$(cat "$root/ssid")" "$freq"
  ;;
esac
''',
    )
    helpers.write_ascii(
        root / "bin/iwpriv",
        r'''#!/bin/sh
root=${OM_TEST_ROOT:?}
cmd=${2:-}
case "$cmd" in
get_mode) printf 'wifi0 get_mode:11ac%sEdge+\n' "$(cat "$root/bandwidth")"; exit 0 ;;
get_hide_ssid) key=hide_ssid ;;
get_ap_bridge) key=ap_bridge ;;
get_wmm) key=wmm ;;
get_short_gi) key=short_gi ;;
get_ldpc) key=ldpc ;;
get_40only_mode) key=forty_only ;;
get_dtim_period) key=dtim_period ;;
get_bintval) key=beacon_interval ;;
get_retrycount) key=retry_count ;;
get_mcast_rate) key=multicast_rate ;;
get_tpc_intvl) key=tpc_interval ;;
get_ba_control) key=ba_control ;;
get_ba_max) key=ba_max ;;
get_ampdu_dens) key=ampdu_density ;;
get_doth) key=doth ;;
get_tpc) key=tpc ;;
get_disablescan) key=disablescan ;;
get_scan_dfs) key=scan_no_dfs ;;
get_alt_chan) key=alt_chan ;;
get_dfs_switch) key=dfs_switch ;;
get_dfs_csa_cnt) key=dfs_csa_count ;;
get_reg_is_eu) key=reg_is_eu ;;
chan_avail_stat) key=chan_avail_status ;;
get_cacstatus)
  if [ -s "$root/cac_sequence" ]; then
    value=$(sed -n '1p' "$root/cac_sequence")
    sed '1d' "$root/cac_sequence" > "$root/cac_sequence.next"
    mv "$root/cac_sequence.next" "$root/cac_sequence"
    printf '%s\n' "$value" > "$root/cac_status"
    [ "$value" = 0 ] && printf '2\n' > "$root/chan_avail_status"
  else
    value=$(cat "$root/cac_status")
  fi
  printf 'wifi0 get_cacstatus:%s\n' "$value"
  exit 0
  ;;
scs_get) key=scs ;;
mode)
  case "$3" in *20*) value=20;; *40*) value=40;; *80*) value=80;; *) exit 1;; esac
  printf 'mode %s\n' "$3" >> "$root/set.log"
  printf '%s\n' "$value" > "$root/bandwidth"
  exit 0
  ;;
hide_ssid) key=hide_ssid ;;
ap_bridge) key=ap_bridge ;;
wmm) key=wmm ;;
short_gi) key=short_gi ;;
set_ldpc) key=ldpc ;;
set_40only_mode) key=forty_only ;;
retrycount) key=retry_count ;;
mcast_rate) key=multicast_rate ;;
tpc_interval) key=tpc_interval ;;
ba_control) key=ba_control ;;
ba_max) key=ba_max ;;
set_ampdu_dens) key=ampdu_density ;;
bintval) key=beacon_interval ;;
dtim_period) key=dtim_period ;;
doth) key=doth ;;
tpc) key=tpc ;;
scs_set) key=scs; [ "$3" = 65536 ] && set -- "$1" "$2" 0 ;;
autocs_enable) key=autocs ;;
disablescan) key=disablescan ;;
scan_cancel) exit 0 ;;
scan_no_dfs) key=scan_no_dfs ;;
set_alt_chan) key=alt_chan ;;
init_txpower) printf 'init_txpower %s\n' "$3" >> "$root/set.log"; exit 0 ;;
*) exit 1 ;;
esac
case "$cmd" in
get_*|scs_get|chan_avail_stat) printf 'wifi0 %s:%s\n' "$cmd" "$(cat "$root/$key")" ;;
*)
  printf '%s %s\n' "$cmd" "$3" >> "$root/set.log"
  if [ -e "$root/fail-$cmd-once" ]; then rm -f "$root/fail-$cmd-once"; exit 1; fi
  printf '%s\n' "$3" > "$root/$key"
  ;;
esac
''',
    )
    for name, value in {
        "cac_status": "0\n",
        "chan_avail_status": "2\n",
        "cac_behavior": "complete\n",
        "next_avail_status": "8\n",
        "tpc": "1\n",
        "disablescan": "1\n",
        "dfs_switch": "0\n",
        "dfs_csa_count": "0\n",
        "reg_is_eu": "1\n",
    }.items():
        helpers.write_ascii(root / name, value)
    (root / "bin/iwconfig").chmod(0o755)
    (root / "bin/iwpriv").chmod(0o755)
    helpers.write_ascii(root / "dfs-feature", f"OPENMITRASTAR_QTN_DFS_CONTROL={1 if dfs_ready else 0}\n")
    helpers.write_ascii(root / "dfs-ready", f"{1 if dfs_ready else 0}\n")
    env += (
        " OM_QTN_SLEEP_COMMAND=/bin/true"
        " OM_QTN_CAC_TIMEOUT_NORMAL=4"
        " OM_QTN_CAC_TIMEOUT_WEATHER=5"
    )
    return helpers, env, qtnctl, tmp


def run_apply(helpers, env: str, qtnctl: str, path: Path):
    return helpers.run_wsl(
        f"{env} sh {shlex.quote(qtnctl)} apply {shlex.quote(helpers.wsl_path(path))}"
    )


def test_static_control_contract_has_no_cac_bypass() -> None:
    qtnctl = QTNCTL.read_text(encoding="utf-8")
    radioctl = RADIOCTL.read_text(encoding="utf-8")
    assert "cac_timeout_normal=${OM_QTN_CAC_TIMEOUT_NORMAL:-90}" in qtnctl
    assert "cac_timeout_weather=${OM_QTN_CAC_TIMEOUT_WEATHER:-630}" in qtnctl
    assert "forward_dynamic_order=" in qtnctl and "multicast_rate tpc_interval'" in qtnctl
    assert "rollback_dynamic_order='tpc_interval multicast_rate" in qtnctl
    assert "wait_dfs_cac" in qtnctl
    assert "dfs-doth-required" in qtnctl
    for forbidden in ("set_boot_cac", "radar_nop_time", "dfs_test_mode", "DONTCAREDOTH"):
        assert forbidden not in qtnctl
    assert '"quick_cac":false' in radioctl
    assert '"debug_bypass":false' in radioctl


@pytest.mark.parametrize(
    ("channel", "bandwidth", "expected_mode"),
    ((40, 20, "11ac20"), (44, 40, "11ac40"), (52, 80, "11ac80Edge+")),
)
def test_channel_bandwidth_mode_map_and_exact_rollback(channel: int, bandwidth: int, expected_mode: str) -> None:
    with tempfile.TemporaryDirectory(prefix="f316-mode-") as directory:
        root = Path(directory)
        helpers, env, qtnctl, tmp = create_f316_fake(root)
        try:
            request = root / "request.conf"
            helpers.write_ascii(request, f"band=5g\nchannel={channel}\nbandwidth={bandwidth}\n")
            result = run_apply(helpers, env, qtnctl, request)
            assert result.returncode == 0, result.stdout + result.stderr
            assert (root / "channel").read_text(encoding="ascii").strip() == str(channel)
            assert (root / "bandwidth").read_text(encoding="ascii").strip() == str(bandwidth)
            assert any(line == f"mode {expected_mode}" for line in (root / "set.log").read_text(encoding="ascii").splitlines())

            rollback = root / "rollback.conf"
            helpers.write_ascii(rollback, "band=5g\nchannel=36\nbandwidth=80\n")
            restored = helpers.run_wsl(
                f"{env} sh {shlex.quote(qtnctl)} rollback {shlex.quote(helpers.wsl_path(rollback))}"
            )
            assert restored.returncode == 0, restored.stdout + restored.stderr
            assert (root / "channel").read_text(encoding="ascii").strip() == "36"
            assert (root / "bandwidth").read_text(encoding="ascii").strip() == "80"
        finally:
            helpers.cleanup_fake_qtn(tmp)


def test_dfs_sets_doth_before_channel_and_waits_for_qdrv_cac() -> None:
    with tempfile.TemporaryDirectory(prefix="f316-dfs-") as directory:
        root = Path(directory)
        helpers, env, qtnctl, tmp = create_f316_fake(root)
        try:
            request = root / "dfs.conf"
            helpers.write_ascii(request, "band=5g\nchannel=116\nbandwidth=80\n")
            plan = helpers.run_wsl(
                f"{env} sh {shlex.quote(qtnctl)} plan {shlex.quote(helpers.wsl_path(request))}"
            )
            assert plan.returncode == 0, plan.stdout + plan.stderr
            planned = json.loads(plan.stdout)
            assert planned["apply_allowed"] is True
            assert planned["dfs_requested"] is True
            assert planned["cac_timeout_seconds"] == 5

            result = run_apply(helpers, env, qtnctl, request)
            assert result.returncode == 0, result.stdout + result.stderr
            log = (root / "set.log").read_text(encoding="ascii").splitlines()
            assert log.index("doth 1") < log.index("channel 116")
            assert "disablescan 0" in log
            assert "scan_no_dfs 0" in log
            assert "set_alt_chan 36" in log
            assert (root / "cac_status").read_text(encoding="ascii").strip() == "0"
            assert (root / "chan_avail_status").read_text(encoding="ascii").strip() == "2"
        finally:
            helpers.cleanup_fake_qtn(tmp)


def test_non_dfs_channel_and_bandwidth_remain_writable_without_radar_backend() -> None:
    with tempfile.TemporaryDirectory(prefix="f316-nondfs-") as directory:
        root = Path(directory)
        helpers, env, qtnctl, tmp = create_f316_fake(root, dfs_ready=False)
        try:
            request = root / "nondfs.conf"
            helpers.write_ascii(request, "band=5g\nchannel=44\nbandwidth=40\n")
            plan = helpers.run_wsl(
                f"{env} sh {shlex.quote(qtnctl)} plan {shlex.quote(helpers.wsl_path(request))}"
            )
            assert plan.returncode == 0, plan.stdout + plan.stderr
            assert json.loads(plan.stdout)["apply_allowed"] is True
            result = run_apply(helpers, env, qtnctl, request)
            assert result.returncode == 0, result.stdout + result.stderr
            assert (root / "channel").read_text(encoding="ascii").strip() == "44"
            assert (root / "bandwidth").read_text(encoding="ascii").strip() == "40"
            assert (root / "doth").read_text(encoding="ascii").strip() == "0"

            dfs = root / "dfs.conf"
            helpers.write_ascii(dfs, "band=5g\nchannel=52\n")
            blocked = helpers.run_wsl(
                f"{env} sh {shlex.quote(qtnctl)} plan {shlex.quote(helpers.wsl_path(dfs))}"
            )
            assert blocked.returncode == 0, blocked.stdout + blocked.stderr
            assert json.loads(blocked.stdout)["apply_allowed"] is False

            tpc = root / "tpc.conf"
            helpers.write_ascii(tpc, "band=5g\ntpc_interval=60\n")
            invalid = helpers.run_wsl(
                f"{env} sh {shlex.quote(qtnctl)} plan {shlex.quote(helpers.wsl_path(tpc))}"
            )
            assert invalid.returncode == 2
            assert json.loads(invalid.stdout)["error"] == "invalid-config"
        finally:
            helpers.cleanup_fake_qtn(tmp)


def test_radar_nop_rejects_target_and_self_restores_exact_state() -> None:
    with tempfile.TemporaryDirectory(prefix="f316-nop-") as directory:
        root = Path(directory)
        helpers, env, qtnctl, tmp = create_f316_fake(root)
        try:
            helpers.write_ascii(root / "next_avail_status", "4\n")
            request = root / "nop.conf"
            helpers.write_ascii(request, "band=5g\nchannel=52\nbandwidth=40\n")
            result = run_apply(helpers, env, qtnctl, request)
            assert result.returncode == 1
            payload = json.loads(result.stdout)
            assert "dfs-radar-nop:52" in payload["detail"]
            assert "self_rollback=restored" in payload["detail"], {
                "payload": payload,
                "set_log": (root / "set.log").read_text(encoding="ascii").splitlines(),
                "channel": (root / "channel").read_text(encoding="ascii").strip(),
                "bandwidth": (root / "bandwidth").read_text(encoding="ascii").strip(),
            }
            assert (root / "channel").read_text(encoding="ascii").strip() == "36"
            assert (root / "bandwidth").read_text(encoding="ascii").strip() == "80"
        finally:
            helpers.cleanup_fake_qtn(tmp)


def test_cac_timeout_rejects_target_and_self_restores_exact_state() -> None:
    with tempfile.TemporaryDirectory(prefix="f316-timeout-") as directory:
        root = Path(directory)
        helpers, env, qtnctl, tmp = create_f316_fake(root)
        try:
            helpers.write_ascii(root / "cac_behavior", "timeout\n")
            request = root / "timeout.conf"
            helpers.write_ascii(request, "band=5g\nchannel=100\nbandwidth=20\n")
            result = run_apply(helpers, env, qtnctl, request)
            assert result.returncode == 1
            payload = json.loads(result.stdout)
            assert "dfs-cac-timeout:100:20:4" in payload["detail"]
            assert "self_rollback=restored" in payload["detail"], {
                "payload": payload,
                "set_log": (root / "set.log").read_text(encoding="ascii").splitlines(),
                "channel": (root / "channel").read_text(encoding="ascii").strip(),
                "bandwidth": (root / "bandwidth").read_text(encoding="ascii").strip(),
            }
            assert (root / "channel").read_text(encoding="ascii").strip() == "36"
            assert (root / "bandwidth").read_text(encoding="ascii").strip() == "80"
        finally:
            helpers.cleanup_fake_qtn(tmp)


def test_tpc_interval_is_applied_after_doth_and_restored_first() -> None:
    with tempfile.TemporaryDirectory(prefix="f316-tpc-") as directory:
        root = Path(directory)
        helpers, env, qtnctl, tmp = create_f316_fake(root)
        try:
            helpers.write_ascii(root / "doth", "0\n")
            request = root / "tpc.conf"
            helpers.write_ascii(request, "band=5g\ntpc_interval=60\nmulticast_rate=6000\n")
            result = run_apply(helpers, env, qtnctl, request)
            assert result.returncode == 0, result.stdout + result.stderr
            log = (root / "set.log").read_text(encoding="ascii").splitlines()
            assert log.index("doth 1") < log.index("tpc 1") < log.index("tpc_interval 60")

            helpers.write_ascii(root / "set.log", "")
            rollback = root / "rollback.conf"
            helpers.write_ascii(rollback, "band=5g\ntpc_interval=30\nmulticast_rate=1000\n")
            restored = helpers.run_wsl(
                f"{env} sh {shlex.quote(qtnctl)} rollback {shlex.quote(helpers.wsl_path(rollback))}"
            )
            assert restored.returncode == 0, restored.stdout + restored.stderr
            rollback_log = (root / "set.log").read_text(encoding="ascii").splitlines()
            assert rollback_log.index("tpc_interval 30") < rollback_log.index("mcast_rate 1000")
            assert (root / "tpc_interval").read_text(encoding="ascii").strip() == "30"
        finally:
            helpers.cleanup_fake_qtn(tmp)


@pytest.mark.parametrize("dfs_ready", (False, True))
def test_radio_api_reports_actual_dfs_control_capabilities(dfs_ready: bool) -> None:
    with tempfile.TemporaryDirectory(prefix="f316-api-") as directory:
        root = Path(directory)
        helpers, env, qtnctl, tmp = create_f316_fake(root, dfs_ready=dfs_ready)
        radioctl = helpers.wsl_path(RADIOCTL)
        (root / "radio5g").mkdir(exist_ok=True)
        helpers.write_ascii(root / "radio5g/state", "ready\n")
        radio_env = (
            f"{env} OM_RUN_ROOT={tmp} OM_SYS_ROOT={tmp}/sys OM_QTNCTL={qtnctl} "
            f"OM_QTN_HOSTAPD_CLI={tmp}/bin/hostapd-cli OM_IWCONFIG_QTN={tmp}/bin/iwconfig "
            f"OM_IWPRIV_QTN={tmp}/bin/iwpriv OM_QTN_HOSTAPD_CONFIG={tmp}/state/hostapd.conf"
        )
        try:
            capabilities = helpers.run_wsl(f"{radio_env} sh {shlex.quote(radioctl)} capabilities 5g")
            assert capabilities.returncode == 0, capabilities.stdout + capabilities.stderr
            caps = json.loads(capabilities.stdout)
            assert caps["dfs_linux510_backend_ready"] is dfs_ready
            assert caps["dfs_control"]["cac_owner"] == "qdrv"
            assert caps["dfs_control"]["timeouts_seconds"] == {"normal": 90, "weather": 630}
            assert ("tpc_interval" in caps["writable_settings"]) is dfs_ready
            assert "channel" in caps["writable_settings"]
            assert "bandwidth" in caps["writable_settings"]

            settings_result = helpers.run_wsl(f"{radio_env} sh {shlex.quote(radioctl)} settings 5g")
            assert settings_result.returncode == 0, settings_result.stdout + settings_result.stderr
            settings = {item["id"]: item for item in json.loads(settings_result.stdout)["settings"]}
            assert settings["channel"]["writable"] is True
            assert settings["bandwidth"]["writable"] is True
            assert settings["tpc_interval"]["writable"] is dfs_ready
            assert settings["channel"]["dfs_backend_ready"] is dfs_ready

            dfs_result = helpers.run_wsl(f"{radio_env} sh {shlex.quote(radioctl)} dfs_status 5g")
            assert dfs_result.returncode == 0, dfs_result.stdout + dfs_result.stderr
            dfs = json.loads(dfs_result.stdout)
            assert dfs["writable"] is dfs_ready
            assert dfs["driver_raw"]["channel_availability_state"] == "available"
            assert dfs["channel_policy"]["availability_values"] == {
                "available": 2,
                "radar_nop": 4,
                "cac_required": 8,
            }
        finally:
            helpers.cleanup_fake_qtn(tmp)
