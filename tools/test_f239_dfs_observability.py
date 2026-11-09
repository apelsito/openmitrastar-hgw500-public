from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F237 = PRIVATE / "f237-device-bound"
F239 = PRIVATE / "f239-device-bound"


def artifact(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f239_preserves_f237_kernel_and_is_hardware_hold() -> None:
    manifest_path = F239 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f239-dfs-observability/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["native_qtn_control"]["backend"] == "wext-hostapd-restart"
    assert manifest["native_rtl_control"]["backend"] == "nl80211-hostapd-reload"
    assert manifest["config_apply"]["enabled"] is True
    assert manifest["dfs_observability"]["write_operations"] is False
    assert manifest["dfs_observability"]["policy"] == "fail-closed"
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F239 / artifact("f239", suffix)) == sha256(F237 / artifact("f237", suffix))
