from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F248 = PRIVATE / "f248-device-bound"
F250 = PRIVATE / "f250-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f250_source_is_feature_gated_and_restoring() -> None:
    overlay = ROOT / "versions/lyoko-foundation-5.1-f250/overlay"
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    ledctl = (overlay / "usr/sbin/om-ledctl").read_text(encoding="utf-8")
    html = (overlay / "www/dashboard.html").read_text(encoding="utf-8")
    assert "OPENMITRASTAR_LED_TEST_API=0" in (overlay / "etc/openmitrastar/features/hardware-led-test-v1").read_text(encoding="ascii")
    for marker in ("OPENMITRASTAR_LED_IDENTIFY_V1", "led-api-disabled", "led-identification-failed", 'before=$($ledctl status', 'after=$($ledctl status'):
        assert marker in api
    assert "trap restore_leds EXIT HUP INT TERM" in ledctl
    assert 'id="led-identify"' in html
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "hostapd", "iwpriv"):
        assert forbidden not in api


def test_f250_preserves_f248_kernel_and_is_offline_hold() -> None:
    manifest_path = F250 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f250-led-control/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["led_control"]["snapshot_restore_required"] is True
    assert manifest["led_control"]["feature_gate_default"] is False
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F250 / named("f250", suffix)) == sha256(F248 / named("f248", suffix))
