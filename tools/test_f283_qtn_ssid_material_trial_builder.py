from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-foundation-6.3.7-f283-qtn-ssid-material-trial"
OVERLAY = SOURCE / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F282 = PRIVATE / "f282-device-bound"
F283 = PRIVATE / "f283-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_qtn_material_trial_is_separate_from_web_apply() -> None:
    feature = (OVERLAY / "etc/openmitrastar/features/qtn-native-control-v1").read_text(encoding="ascii").strip()
    qtnctl = (OVERLAY / "usr/sbin/om-qtnctl").read_text(encoding="utf-8")
    app = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    assert feature == "OPENMITRASTAR_QTN_NATIVE_CONTROL=0"
    for marker in ("OMQTNCTL stage=", "configure-begin", "mode-begin", "channel-begin", "apply-verified"):
        assert marker in qtnctl
    assert "inspectOnlyChannel" in app
    step_feature = (OVERLAY / "etc/openmitrastar/features/qtn-step-probe-v1").read_text(encoding="ascii").strip()
    step = (OVERLAY / "usr/sbin/om-qtn-step").read_text(encoding="utf-8")
    assert step_feature == "OPENMITRASTAR_QTN_STEP_PROBE=1"
    assert "OPENMITRASTAR_QTN_STEP_V1" in step
    assert "OMQTNSTEP begin" in step and "OMQTNSTEP pass" in step and "OMQTNSTEP fail" in step
    assert "acquire_lock" in step and "release_lock" in step
    assert 'printf \'%s\\n\' "$$" >"$lock/pid"' in step
    assert 'ifconfig_bin=${OM_IFCONFIG:-/bin/ifconfig}' in step
    radioctl = (OVERLAY / "usr/sbin/om-radioctl").read_text(encoding="utf-8")
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    for setting in ("retry_count", "ldpc", "forty_only", "tpc_interval", "multicast_rate"):
        assert setting in radioctl
        assert f'data-setting="{setting}"' in html
    assert "inverse_bool_json" in radioctl
    assert "truefalse" not in radioctl and "falsetrue" not in radioctl
    assert "plan_config()" in qtnctl
    assert "get_mode()" in qtnctl
    assert "bandwidth_from_mode()" in qtnctl
    assert 'old_mode=$(get_mode)' in qtnctl
    assert 'old_bandwidth=$(bandwidth_from_mode "$old_mode")' in qtnctl
    assert 'mode_change=false; [ "$target_mode" = "$old_mode" ] || mode_change=true' in qtnctl
    assert "txpower-limit-skipped-wext-regulatory-reject" in qtnctl
    assert '$iwconfig "$iface" txpower "$txpower_dbm"' not in qtnctl
    assert '"schema":"lyoko.qtn.plan/v1"' in qtnctl
    assert "apply-noop" in qtnctl
    assert qtnctl.index('if [ "$ssid" = "$old_ssid" ]') < qtnctl.index('dependencies_ready || { error_result control-backend-unavailable')
    api = (OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    app = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    assert "radios/5g/plan)" in api
    assert api.count("radios/5g/plan)") == 1
    plan_case = api.split("radios/5g/plan)", 1)[1].split("config/apply|", 1)[0]
    assert "require_read" not in plan_case
    assert "csrf_valid" in plan_case
    assert 'sh "$radioctl" plan_config 5g' in api
    assert 'api("/api/v1/radios/5g/plan"' in app
    assert 'id="radio5-plan"' in html
    assert "wait_original_state()" in step
    assert "state-not-converged" in step
    assert 'kill "$pid"' in step
    assert '"$proc_root/$pid/comm"' in step
    assert "txpower-limit-same" not in step
    assert "write_hostapd_config()" in step
    assert '[ -s "$conf" ] || write_hostapd_config "$conf"' in step
    assert "OMQTNSTEP stage=hostapd-stop" in step
    assert "OMQTNSTEP stage=pre-rearm" in step
    assert "OMQTNSTEP stage=hostapd-start" in step
    assert "OMQTNSTEP stage=post-rearm" in step
    trial = (OVERLAY / "usr/sbin/om-qtn-material-trial").read_text(encoding="utf-8")
    trial_feature = (OVERLAY / "etc/openmitrastar/features/qtn-material-trial-v1").read_text(encoding="ascii").strip()
    assert trial_feature == "OPENMITRASTAR_QTN_NATIVE_CONTROL=1"
    assert "OPENMITRASTAR_QTN_MATERIAL_TRIAL_V1" in trial
    assert "Lyoko-5G-Material-Test" in trial
    assert "watchdog.armed" in trial
    assert "stage=restore-pass" in trial
    assert "wpa_passphrase" not in trial
    for operation in ("rf-write-same", "interface-up-same", "mode-write-same", "ssid-write-same", "channel-write-same", "txpower-init-same", "doth-write-same", "tpc-write-same", "tpc-interval-same", "hostapd-restart-same", "post-rearm-same"):
        assert operation in step
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv"):
        assert forbidden not in step


def test_f283_manifest_and_kernel_contract() -> None:
    manifest = json.loads((F283 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f283-qtn-ssid-material-trial/v1"
    assert manifest["source"]["firmware"] == "F282 installed physical baseline"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["native_qtn_control"]["default_enabled"] is False
    assert manifest["native_qtn_control"]["hardware_status"] == "F282_HOSTAPD_RESTART_PASS"
    assert manifest["developer_console"]["qtn_mutation_default"] == "disabled-after-hang"
    assert manifest["developer_console"]["firmware_line"] == "F283 Full"
    assert manifest["developer_console"]["radio_workbench"] == "contract-driven-live-mode-plan-preview"
    assert manifest["native_qtn_control"]["mutation_plan"] == "authenticated read-only API/UI preview with live mode comparison and fail-closed no-op fast path"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/openmitrastar/release",
        "etc/openmitrastar/features/qtn-material-trial-v1",
        "usr/sbin/om-qtn-material-trial",
    }
    assert manifest["foundation_assets"]["source_rootfs"]["sha256"] == sha256(
        F282 / named("f282", ".rootfs.squashfs")
    )
    assert manifest["qtn_material_trial"]["global_web_apply_enabled"] is False
    assert manifest["qtn_material_trial"]["channel_change"] is False
    assert manifest["qtn_material_trial"]["psk_change"] is False
    assert manifest["qtn_material_trial"]["hardware_status"] == "NOT_RUN"
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F283 / named("f283", suffix)) == sha256(F282 / named("f282", suffix))
