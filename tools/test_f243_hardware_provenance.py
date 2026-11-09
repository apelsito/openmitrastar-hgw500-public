from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F241 = PRIVATE / "f241-device-bound"
F243 = PRIVATE / "f243-device-bound"


def artifact(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f243_preserves_f241_kernel_and_is_hardware_hold() -> None:
    manifest_path = F243 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f243-hardware-provenance/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["native_qtn_control"]["backend"] == "wext-hostapd-restart"
    assert manifest["native_rtl_control"]["backend"] == "nl80211-hostapd-reload"
    assert manifest["config_apply"]["enabled"] is True
    assert manifest["hardware_provenance"]["write_operations"] is False
    assert manifest["hardware_provenance"]["buttons"]["wifi5g"]["gpio"] == 4
    assert manifest["hardware_provenance"]["watchdog"]["present"] is False
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F243 / artifact("f243", suffix)) == sha256(F241 / artifact("f241", suffix))
