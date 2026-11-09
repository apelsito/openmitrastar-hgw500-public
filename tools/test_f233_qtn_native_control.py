from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F231 = PRIVATE / "f231-device-bound"
F233 = PRIVATE / "f233-device-bound"


def artifact(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f233_preserves_f231_kernel_and_is_hardware_hold() -> None:
    manifest_path = F233 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f233-qtn-native-control/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["native_qtn_control"]["backend"] == "wext-hostapd-restart"
    assert manifest["native_qtn_control"]["hardware_status"] == "NOT_RUN"
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F233 / artifact("f233", suffix)) == sha256(F231 / artifact("f231", suffix))
