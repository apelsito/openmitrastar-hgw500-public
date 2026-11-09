from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac-f288-rx-fault-napi.c"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F287 = PRIVATE / "f287-device-bound"
F288 = PRIVATE / "f288-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_keeps_napi256_and_services_rx_faults() -> None:
    source = DRIVER.read_text(encoding="utf-8")
    assert "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t256" in source
    assert "#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t256" in source
    assert source.count("QTN_TOPAZ_EMAC_DMA_IRQ_RX_FAULTS") >= 5


def test_f288_manifest_and_artifact_contract() -> None:
    manifest = json.loads((F288 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f288-emac-rx-fault-napi-from-f287/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["binary_contract"]["result"] == "PASS"
    assert manifest["binary_contract"]["rx_ring_descriptors"] == 256
    assert manifest["binary_contract"]["napi_weight"] == 256
    assert manifest["binary_contract"]["rx_pending_mask"] == "0x1f1"
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    assert "RX_STOPPED, NO_RX_DESC and RX_MISSED" in manifest["change_scope"]["single_functional_variable"]
    assert manifest["native_qtn_control"] == json.loads((F287 / "manifest.json").read_text(encoding="ascii"))["native_qtn_control"]
    assert manifest["developer_console"]["firmware_line"] == "F288 Full"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {"etc/openmitrastar/release"}
    assert sha256(F288 / named("f288", ".kernel.lzma")) != sha256(F287 / named("f287", ".kernel.lzma"))
    assert sha256(F288 / named("f288", ".rootfs.squashfs")) != sha256(F287 / named("f287", ".rootfs.squashfs"))
    for suffix in (".config", ".dtb"):
        assert sha256(F288 / named("f288", suffix)) == sha256(F287 / named("f287", suffix))
