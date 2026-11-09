from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F235 = PRIVATE / "f235-device-bound"
F237 = PRIVATE / "f237-device-bound"


def artifact(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f237_preserves_f235_kernel_and_is_hardware_hold() -> None:
    manifest_path = F237 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f237-hardened-dual-radio-control/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["native_qtn_control"]["backend"] == "wext-hostapd-restart"
    assert manifest["native_rtl_control"]["backend"] == "nl80211-hostapd-reload"
    assert manifest["config_apply"]["enabled"] is True
    assert manifest["transaction_hardening"]["qtn_ready_gate"] == "PONG plus state=ENABLED"
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F237 / artifact("f237", suffix)) == sha256(F235 / artifact("f235", suffix))
