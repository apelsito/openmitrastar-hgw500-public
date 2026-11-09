from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-foundation-6.3.0-f275-qtn-plan-ui"
OVERLAY = SOURCE / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F274 = PRIVATE / "f274-device-bound"
F275 = PRIVATE / "f275-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_qtn_mutation_is_default_off_and_plan_is_exposed_read_only() -> None:
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
    assert '"schema":"lyoko.qtn.plan/v1"' in qtnctl
    assert "apply-noop" in qtnctl
    assert qtnctl.index('if [ "$ssid" = "$old_ssid" ]') < qtnctl.index('dependencies_ready || { error_result control-backend-unavailable')
    api = (OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    app = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    assert "radios/5g/plan)" in api
    assert 'sh "$radioctl" plan_config 5g' in api
    assert 'api("/api/v1/radios/5g/plan"' in app
    assert 'id="radio5-plan"' in html
    for operation in ("rf-write-same", "interface-up-same", "mode-write-same", "ssid-write-same", "channel-write-same", "txpower-init-same", "txpower-limit-same", "doth-write-same", "tpc-write-same", "tpc-interval-same", "hostapd-restart-same", "post-rearm-same"):
        assert operation in step
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv"):
        assert forbidden not in step


def test_f275_manifest_and_kernel_contract() -> None:
    manifest = json.loads((F275 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f275-qtn-plan-ui/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["native_qtn_control"]["default_enabled"] is False
    assert manifest["native_qtn_control"]["hardware_status"] == "BLOCKED_AFTER_APPLY_HANG"
    assert manifest["developer_console"]["qtn_mutation_default"] == "disabled-after-hang"
    assert manifest["developer_console"]["radio_workbench"] == "contract-driven-plan-preview"
    assert manifest["native_qtn_control"]["mutation_plan"] == "authenticated read-only API/UI preview plus fail-closed no-op fast path"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/openmitrastar/release",
        "etc/lyoko/frontend.env",
        "usr/libexec/openmitrastar/om-api-v1",
        "usr/sbin/om-qtnctl",
        "usr/sbin/om-radioctl",
        "usr/share/openmitrastar/web/dashboard.html",
        "www/app.js",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F275 / named("f275", suffix)) == sha256(F274 / named("f274", suffix))
