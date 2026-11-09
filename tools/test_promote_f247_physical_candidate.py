from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F246 = PRIVATE / "f246-device-bound"
F247 = PRIVATE / "f247-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f247_is_exact_f246_bytes_with_test_candidate_metadata() -> None:
    manifest_path = F247 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f247-integrated-physical-test-candidate/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["release_eligible"] is False
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert manifest["source"]["runtime_identity"] == "lyoko-foundation-4.9-f245-device"
    assert manifest["safety"]["rollback_artifact"] == "F222 known-good reflash to mtd4"
    assert manifest["safety"]["rollback_artifact_sha256"] == "ab8f8727f3b1c29a312eddb21f1aa5bc9f474d7be91569f57c9230aaf1fc1c21"
    assert manifest["safety"]["rollback_tool"] == "tools/restore_f222_mtd4_from_f247.ps1"
    for suffix in (".webformat.bin", ".rootfs.squashfs", ".kernel.lzma", ".config", ".dtb"):
        assert sha256(F247 / named("f247", suffix)) == sha256(F246 / named("f246", suffix))


def test_f247_promoter_has_no_hardware_surface() -> None:
    source = (ROOT / "tools/promote_f247_physical_candidate.py").read_text(encoding="utf-8")
    for forbidden in ("import serial", "import socket", "subprocess", "flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
