from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-foundation-6.3.4-f280-store-driver-disabled"
OVERLAY = SOURCE / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F278 = PRIVATE / "f278-device-bound"
F280 = PRIVATE / "f280-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_store_module_is_present_but_disabled() -> None:
    feature = (OVERLAY / "etc/openmitrastar/features/qtn-native-control-v1").read_text(encoding="ascii").strip()
    qtnctl = (OVERLAY / "usr/sbin/om-qtnctl").read_text(encoding="utf-8")
    app = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    assert feature == "OPENMITRASTAR_QTN_NATIVE_CONTROL=0"
    multicast_feature = (OVERLAY / "etc/openmitrastar/features/multicast-cert-v1").read_text(encoding="ascii").strip()
    multicast = (OVERLAY / "usr/sbin/om-multicast-cert").read_text(encoding="utf-8")
    assert multicast_feature == "OPENMITRASTAR_MULTICAST_CERT=1"
    assert "OPENMITRASTAR_MULTICAST_CERT_V1" in multicast
    assert "rollback-watchdog" in multicast
    assert "acquire_lock" in multicast
    store_feature = (OVERLAY / "etc/openmitrastar/features/store-mtd-driver-v1").read_text(encoding="ascii").strip()
    store_module = OVERLAY / "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-mtd.ko"
    assert store_feature == "OPENMITRASTAR_STORE_MTD_DRIVER=0"
    assert store_module.read_bytes() == (ROOT / "outputs/kernel-port/f279-qtn-topaz-store-mtd-20260903/qtn-topaz-store-mtd.ko").read_bytes()
    init_text = "\n".join(path.read_text(encoding="utf-8", errors="ignore") for path in (OVERLAY / "etc/init.d").glob("*"))
    assert "qtn-topaz-store-mtd" not in init_text
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
    for operation in ("rf-write-same", "interface-up-same", "mode-write-same", "ssid-write-same", "channel-write-same", "txpower-init-same", "txpower-limit-same", "doth-write-same", "tpc-write-same", "tpc-interval-same", "hostapd-restart-same", "post-rearm-same"):
        assert operation in step
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv"):
        assert forbidden not in step


def test_f280_manifest_and_kernel_contract() -> None:
    manifest = json.loads((F280 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f280-store-driver-disabled/v1"
    assert manifest["source"]["firmware"] == "F278"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["classification"] == "PRIVATE_DEVICE_BOUND_OFFLINE_SUCCESSOR_HOLD"
    assert manifest["native_qtn_control"]["default_enabled"] is False
    assert manifest["native_qtn_control"]["hardware_status"] == "BLOCKED_AFTER_APPLY_HANG"
    assert manifest["developer_console"]["qtn_mutation_default"] == "disabled-after-hang"
    assert manifest["developer_console"]["firmware_line"] == "F280 Full"
    assert manifest["developer_console"]["radio_workbench"] == "contract-driven-live-mode-plan-preview"
    assert manifest["native_qtn_control"]["mutation_plan"] == "authenticated read-only API/UI preview with live mode comparison and fail-closed no-op fast path"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/openmitrastar/release",
        "etc/openmitrastar/features/store-mtd-driver-v1",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage",
        "lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-mtd.ko",
    }
    assert manifest["foundation_assets"]["source_rootfs"]["sha256"] == sha256(
        F278 / named("f278", ".rootfs.squashfs")
    )
    assert manifest["store_mtd_driver"]["autoload"] is False
    assert manifest["store_mtd_driver"]["feature_default"] is False
    assert manifest["store_mtd_driver"]["write_default"] is False
    assert manifest["store_mtd_driver"]["bulk_erase"] is False
    assert manifest["store_mtd_driver"]["hardware_status"] == "NOT_LOADED"
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F280 / named("f280", suffix)) == sha256(F278 / named("f278", suffix))
