from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-foundation-6.1.2-f269-qtn-step-lock-fix"
OVERLAY = SOURCE / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F268 = PRIVATE / "f268-device-bound"
F269 = PRIVATE / "f269-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_qtn_mutation_is_default_off_and_step_probe_has_stale_lock_recovery() -> None:
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
    for operation in ("rf-write-same", "interface-up-same", "mode-write-same", "ssid-write-same", "channel-write-same", "txpower-init-same", "txpower-limit-same", "doth-write-same", "tpc-write-same", "tpc-interval-same", "hostapd-restart-same", "post-rearm-same"):
        assert operation in step
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv"):
        assert forbidden not in step


def test_f269_manifest_and_kernel_contract() -> None:
    manifest = json.loads((F269 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f269-qtn-step-lock-fix/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["native_qtn_control"]["default_enabled"] is False
    assert manifest["native_qtn_control"]["hardware_status"] == "BLOCKED_AFTER_APPLY_HANG"
    assert manifest["developer_console"]["qtn_mutation_default"] == "disabled-after-hang"
    assert manifest["native_qtn_control"]["step_probe"] == "ACK-gated CLI with stale-lock recovery"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/openmitrastar/release",
        "usr/sbin/om-qtn-step",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F269 / named("f269", suffix)) == sha256(F268 / named("f268", suffix))
