from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F286 = PRIVATE / "f286-device-bound"
F287 = PRIVATE / "f287-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_baseline_remains_napi128_ring256() -> None:
    source = DRIVER.read_text(encoding="utf-8")
    assert "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t256" in source
    assert "#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t128" in source


def test_f287_manifest_and_artifact_contract() -> None:
    manifest = json.loads((F287 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f287-emac-napi256-from-f286/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["binary_contract"]["result"] == "PASS"
    assert manifest["binary_contract"]["rx_ring_descriptors"] == 256
    assert manifest["binary_contract"]["napi_weight"] == 256
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    assert manifest["change_scope"]["single_functional_variable"] == "qtn-topaz-emac NAPI weight 128 -> 256"
    assert manifest["native_qtn_control"] == json.loads((F286 / "manifest.json").read_text(encoding="ascii"))["native_qtn_control"]
    assert manifest["developer_console"]["firmware_line"] == "F287 Full"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {"etc/openmitrastar/release"}
    assert sha256(F287 / named("f287", ".kernel.lzma")) != sha256(F286 / named("f286", ".kernel.lzma"))
    assert sha256(F287 / named("f287", ".rootfs.squashfs")) != sha256(F286 / named("f286", ".rootfs.squashfs"))
    for suffix in (".config", ".dtb"):
        assert sha256(F287 / named("f287", suffix)) == sha256(F286 / named("f286", suffix))
