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
F314 = ROOT / "versions/lyoko-foundation-6.8.2-f314-qtn-nondfs-guard"
F313 = ROOT / "versions/lyoko-foundation-6.8.0-f313-qtn-controls"
QTNCTL = F314 / "overlay/usr/sbin/om-qtnctl"
RADIOCTL = F314 / "overlay/usr/sbin/om-radioctl"
APP = F314 / "overlay/www/app.js"
RADIO5_START = F314 / "overlay/usr/sbin/om-radio5-start"


def load_helpers():
    spec = importlib.util.spec_from_file_location("f313_qtn_test_helpers", F313_TEST)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    module.QTNCTL = QTNCTL
    module.RADIOCTL = RADIOCTL
    module.TRANSACTION = F314 / "overlay/usr/sbin/om-config-transaction"
    return module


F313_INHERITED_TESTS = (
    "test_driver_ranges_and_dfs_remain_fail_closed",
    "test_beacon_and_dtim_use_restart_then_exact_readback",
    "test_mid_sequence_failure_self_restores_previous_values",
    "test_invalid_ranges_and_material_channel_changes_are_rejected",
    "test_transaction_stage_apply_and_rollback_restores_advanced_values",
    "test_radio_contract_exposes_individual_controls_but_not_dfs_writes",
    "test_radio_settings_json_is_machine_readable_and_uses_driver_ranges",
)


@pytest.mark.parametrize("test_name", F313_INHERITED_TESTS)
def test_f313_control_contract_is_preserved_in_f314(test_name: str) -> None:
    helpers = load_helpers()
    getattr(helpers, test_name)()


def test_f314_advanced_controls_exclude_tpc_until_dfs_provider() -> None:
    helpers = load_helpers()
    with tempfile.TemporaryDirectory(prefix="f314-advanced-") as directory:
        root = Path(directory)
        env, qtnctl = helpers.create_fake_qtn(root)
        tmp = helpers.wsl_path(root)
        try:
            desired = root / "desired.conf"
            helpers.write_ascii(
                desired,
                "band=5g\nssid_broadcast=false\nclient_isolation=true\nwmm=false\n"
                "short_gi=false\nldpc=false\nforty_only=true\nretry_count=7\n"
                "ba_control=255\nba_max=32\nampdu_density=4\nmulticast_rate=6000\n",
            )
            applied = helpers.run_wsl(
                f"{env} sh {shlex.quote(qtnctl)} apply {shlex.quote(helpers.wsl_path(desired))}"
            )
            assert applied.returncode == 0, applied.stdout + applied.stderr
            assert json.loads(applied.stdout)["verified"] is True
            tpc = root / "tpc.conf"
            helpers.write_ascii(tpc, "band=5g\ntpc_interval=60\n")
            blocked = helpers.run_wsl(
                f"{env} sh {shlex.quote(qtnctl)} plan {shlex.quote(helpers.wsl_path(tpc))}"
            )
            assert blocked.returncode == 2
            assert json.loads(blocked.stdout)["error"] == "invalid-config"
        finally:
            helpers.cleanup_fake_qtn(tmp)


def test_f314_transaction_adds_watchdog_launch_rollback() -> None:
    transaction = (F314 / "overlay/usr/sbin/om-config-transaction").read_text(encoding="utf-8")
    assert '"$qtnctl" "$action" "$file"' in transaction
    assert transaction.count('apply_file "$rollback" rollback') >= 6
    assert "rollback-watchdog-launch" in transaction
    assert 'detach_exec=${OM_DETACH_EXEC:-/usr/sbin/om-detach-exec}' in transaction


def test_static_guard_contract() -> None:
    qtnctl = QTNCTL.read_text(encoding="utf-8")
    radioctl = RADIOCTL.read_text(encoding="utf-8")
    app = APP.read_text(encoding="utf-8")
    assert "current_channel_safe" in qtnctl
    assert "qtn-current-dfs-without-radar" in qtnctl
    assert "radio5_current_dfs_without_backend" in radioctl
    assert "qtn-current-dfs-without-radar" in radioctl
    assert '"qtn-current-dfs-without-radar": ["Protección DFS activa", "blocked"]' in app
    start = RADIO5_START.read_text(encoding="utf-8")
    assert "OMRADIO5_DFS_FAIL_CLOSED" in start
    assert "dfs-current-channel-without-radar" in start
    assert "management=preserve" in start
    assert "printf 'dfs-blocked\\n'" in start
    assert "fail_closed_stop dfs-current-channel-without-radar" in start
    assert "OMRADIO5_FAIL_CLOSED_PASS" in start
    assert "OMRADIO5_FAIL_CLOSED_UNVERIFIED" in start
    assert "dfs-stop-unverified" in start
    assert '"$stop_rf" = 0' in start
    assert '"$stop_hostapd" = down' in start
    assert '"$stop_bridge" = detached' in start
    assert '"$stop_management" = preserved' in start
    assert "get_tpc_intvl:[[:space:]]*30[[:space:]]*$" in start
    assert 'qtn_doth_value=0' in start
    assert 'doth "$qtn_doth_value"' in start
    assert "target_doth=0" in qtnctl
    assert 'doth "$target_doth"' in qtnctl
    assert "non-dfs-stability" in qtnctl
    assert "unavailable-until-dfs-provider" in start
    assert "OMRADIO5_FIXED_CHANNEL_POLICY" in start
    assert "scs_set 65536" in start
    assert "disablescan 1" in start
    assert "scan_cancel 1" in start
    assert "scan_no_dfs 1" in start
    assert "set_alt_chan 0" in start
    assert "apply_fixed_channel_policy" in qtnctl
    assert "fixed-channel-policy scs_command=65536 disablescan=1 scan_no_dfs=1 alt=0" in qtnctl
    assert 'bintval "$target_beacon"' in qtnctl
    assert 'dtim_period "$target_dtim"' in qtnctl


def test_builder_regenerates_and_verifies_radio_artifact_manifest() -> None:
    builder = (ROOT / "tools/build_f314_qtn_nondfs_guard_from_f313.py").read_text(encoding="utf-8")
    assert "usr/share/openmitrastar/radio5g/artifacts.sha256" in builder
    assert "artifact target missing" in builder
    assert "F314 packaged artifact hash mismatch" in builder


def test_boot_reasserts_channel_36_before_final_dfs_guard() -> None:
    start = RADIO5_START.read_text(encoding="utf-8")
    channel_set = "/usr/sbin/iwconfig-qtn wifi0 channel 36"
    guard = "OMRADIO5_DFS_FAIL_CLOSED"
    positions = []
    offset = 0
    while True:
        position = start.find(channel_set, offset)
        if position < 0:
            break
        positions.append(position)
        offset = position + len(channel_set)

    assert len(positions) >= 2
    assert all(position < start.index(guard) for position in positions[:2])


def _run_fail_closed_probe(*, cooperative: bool) -> subprocess.CompletedProcess[str]:
    with tempfile.TemporaryDirectory(prefix="f314-fail-closed-") as directory:
        root = Path(directory)
        sys_root = root / "sys"
        bin_root = root / "bin"
        for path in (
            sys_root / "module/qdrv/parameters",
            sys_root / "class/net/wifi0",
            sys_root / "class/net/br0/brif/eth0",
            sys_root / "class/net/br0/brif/wlan0",
            sys_root / "class/net/br0/brif/wifi0",
            bin_root,
        ):
            path.mkdir(parents=True, exist_ok=True)
        helpers = load_helpers()
        helpers.write_ascii(sys_root / "module/qdrv/parameters/openmitrastar_rf_enable", "1\n")
        helpers.write_ascii(sys_root / "class/net/wifi0/flags", "0x1\n")
        helpers.write_ascii(
            bin_root / "hostapd-cli-qtn",
            "#!/bin/sh\n[ \"${5:-}\" = ping ] && exit 1\nexit 0\n",
        )
        helpers.write_ascii(
            bin_root / "brctl",
            "#!/bin/sh\n"
            + (f"rmdir {helpers.wsl_path(sys_root / 'class/net/br0/brif/wifi0')}\n" if cooperative else "exit 0\n"),
        )
        helpers.write_ascii(
            bin_root / "ifconfig",
            "#!/bin/sh\n"
            + (f"printf '0x0\\n' > {helpers.wsl_path(sys_root / 'class/net/wifi0/flags')}\n" if cooperative else "exit 0\n"),
        )
        helpers.write_ascii(bin_root / "stop", "#!/bin/sh\nexit 1\n")
        for executable in bin_root.iterdir():
            executable.chmod(0o755)
        env = (
            f"OM_RADIO5_TEST_FAIL_CLOSED_ONLY=1 "
            f"OM_RADIO5_SYS_ROOT={helpers.wsl_path(sys_root)} "
            f"OM_RADIO5_RF={helpers.wsl_path(sys_root / 'module/qdrv/parameters/openmitrastar_rf_enable')} "
            f"OM_RADIO5_STOP_HOSTAPD_CLI={helpers.wsl_path(bin_root / 'hostapd-cli-qtn')} "
            f"OM_RADIO5_STOP_BRCTL={helpers.wsl_path(bin_root / 'brctl')} "
            f"OM_RADIO5_STOP_IFCONFIG={helpers.wsl_path(bin_root / 'ifconfig')} "
            f"OM_RADIO5_LOG_PATH=/dev/stdout "
            f"OM_RADIO5_STOP={helpers.wsl_path(bin_root / 'stop')}"
        )
        return helpers.run_wsl(f"{env} sh {shlex.quote(helpers.wsl_path(RADIO5_START))}")


def test_fail_closed_stop_passes_only_after_verified_shutdown() -> None:
    result = _run_fail_closed_probe(cooperative=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "OMRADIO5_FAIL_CLOSED_PASS" in result.stdout


def test_fail_closed_stop_rejects_unverified_netdev_and_bridge() -> None:
    result = _run_fail_closed_probe(cooperative=False)
    assert result.returncode != 0
    assert "OMRADIO5_FAIL_CLOSED_UNVERIFIED" in result.stdout


def test_dfs_current_channel_disables_backend_and_refuses_apply() -> None:
    helpers = load_helpers()
    with tempfile.TemporaryDirectory(prefix="f314-dfs-guard-") as directory:
        root = Path(directory)
        env, qtnctl = helpers.create_fake_qtn(root)
        tmp = helpers.wsl_path(root)
        try:
            iwconfig = root / "bin/iwconfig"
            source = iwconfig.read_text(encoding="ascii")
            source = source.replace(
                '48) freq=5.24;; *) freq=5.18;; esac',
                '48) freq=5.24;; 132) freq=5.66;; *) freq=5.18;; esac',
            )
            helpers.write_ascii(iwconfig, source)
            helpers.write_ascii(root / "channel", "132\n")
            available = helpers.run_wsl(f"{env} sh {shlex.quote(qtnctl)} available")
            assert available.returncode != 0

            request = root / "request.conf"
            helpers.write_ascii(request, "band=5g\nwmm=false\n")
            applied = helpers.run_wsl(f"{env} sh {shlex.quote(qtnctl)} apply {shlex.quote(helpers.wsl_path(request))}")
            assert applied.returncode == 3
            payload = json.loads(applied.stdout)
            assert payload["error"] == "qtn-current-dfs-without-radar"
            assert payload["detail"] == "132"

            helpers.write_ascii(root / "channel", "36\n")
            recovered = helpers.run_wsl(f"{env} sh {shlex.quote(qtnctl)} available")
            assert recovered.returncode == 0
        finally:
            helpers.cleanup_fake_qtn(tmp)


def test_dfs_current_channel_allows_only_rollback_recovery_to_channel_36() -> None:
    helpers = load_helpers()
    with tempfile.TemporaryDirectory(prefix="f314-dfs-rollback-") as directory:
        root = Path(directory)
        env, qtnctl = helpers.create_fake_qtn(root)
        tmp = helpers.wsl_path(root)
        try:
            iwconfig = root / "bin/iwconfig"
            source = iwconfig.read_text(encoding="ascii").replace(
                '48) freq=5.24;; *) freq=5.18;; esac',
                '48) freq=5.24;; 116) freq=5.58;; *) freq=5.18;; esac',
            )
            helpers.write_ascii(iwconfig, source)
            helpers.write_ascii(root / "channel", "116\n")
            helpers.write_ascii(root / "wmm", "0\n")
            rollback = root / "rollback.conf"
            helpers.write_ascii(rollback, "band=5g\nwmm=true\n")
            result = helpers.run_wsl(
                f"{env} OM_QTN_RADIO5_STOP=/bin/false sh {shlex.quote(qtnctl)} "
                f"rollback {shlex.quote(helpers.wsl_path(rollback))}"
            )
            assert result.returncode == 0, result.stdout + result.stderr
            assert (root / "channel").read_text(encoding="ascii").strip() == "36"
            assert (root / "wmm").read_text(encoding="ascii").strip() == "1"
        finally:
            helpers.cleanup_fake_qtn(tmp)
