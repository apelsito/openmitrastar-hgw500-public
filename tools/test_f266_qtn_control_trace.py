from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-foundation-6.0.3-f266-full"
OVERLAY = SOURCE / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F265 = PRIVATE / "f265-device-bound"
F266 = PRIVATE / "f266-device-bound"


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


def test_f266_manifest_and_kernel_contract() -> None:
    manifest = json.loads((F266 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f266-qtn-control-trace/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["native_qtn_control"]["default_enabled"] is False
    assert manifest["native_qtn_control"]["hardware_status"] == "BLOCKED_AFTER_APPLY_HANG"
    assert manifest["developer_console"]["qtn_mutation_default"] == "disabled-after-hang"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/features/qtn-native-control-v1",
        "etc/openmitrastar/release",
        "usr/sbin/om-qtnctl",
        "www/app.js",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F266 / named("f266", suffix)) == sha256(F265 / named("f265", suffix))
