from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-foundation-6.1.0-f267-radio-workbench"
OVERLAY = SOURCE / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F266 = PRIVATE / "f266-device-bound"
F267 = PRIVATE / "f267-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_qtn_mutation_is_default_off_but_inspectable() -> None:
    feature = (OVERLAY / "etc/openmitrastar/features/qtn-native-control-v1").read_text(encoding="ascii").strip()
    qtnctl = (OVERLAY / "usr/sbin/om-qtnctl").read_text(encoding="utf-8")
    app = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    assert feature == "OPENMITRASTAR_QTN_NATIVE_CONTROL=0"
    for marker in ("OMQTNCTL stage=", "configure-begin", "mode-begin", "channel-begin", "apply-verified"):
        assert marker in qtnctl
    assert "inspectOnlyChannel" in app


def test_radio_workbench_is_contract_driven() -> None:
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    app = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    radioctl = (OVERLAY / "usr/sbin/om-radioctl").read_text(encoding="utf-8")
    transaction = (OVERLAY / "usr/sbin/om-config-transaction").read_text(encoding="utf-8")
    rtlctl = (OVERLAY / "usr/sbin/om-rtlctl").read_text(encoding="utf-8")
    for setting in ("ssid_broadcast", "client_isolation", "wmm", "short_gi", "beacon_interval", "dtim_period", "max_clients"):
        assert f'data-setting="{setting}"' in html
        assert setting in radioctl
        assert setting in transaction
        assert setting in rtlctl
    assert "settingState" in app
    assert "data-readback" in html
    assert "qtn-dynamic-control-disabled-after-management-loss" in radioctl


def test_f267_manifest_and_kernel_contract() -> None:
    manifest = json.loads((F267 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f267-radio-workbench/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["native_qtn_control"]["default_enabled"] is False
    assert manifest["native_qtn_control"]["hardware_status"] == "BLOCKED_AFTER_APPLY_HANG"
    assert manifest["developer_console"]["qtn_mutation_default"] == "disabled-after-hang"
    assert manifest["developer_console"]["radio_workbench"] == "contract-driven-expanded"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/lyoko/capabilities.json",
        "etc/openmitrastar/release",
        "usr/sbin/om-config-transaction",
        "usr/sbin/om-radioctl",
        "usr/sbin/om-rtlctl",
        "usr/share/openmitrastar/web/app.css",
        "usr/share/openmitrastar/web/dashboard.html",
        "www/app.js",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F267 / named("f267", suffix)) == sha256(F266 / named("f266", suffix))
