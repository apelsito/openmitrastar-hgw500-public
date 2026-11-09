from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build_f223_emac_rxring256.py"
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac.c"
DEVICE_ID = "hgw500bna-qcv2-a2-primary"
PRIVATE_FIRMWARE = Path.home() / ".openmitrastar/devices" / DEVICE_ID / "firmware"
F222_BUILD = PRIVATE_FIRMWARE / "f222-device-bound"
F222_BASE = f"openmitrastar-linux510-f222-{DEVICE_ID}-PRIVATE-NO-FLASH"
F223_BUILD = PRIVATE_FIRMWARE / "f223-device-bound"
F223_BASE = f"openmitrastar-linux510-f223-{DEVICE_ID}-PRIVATE-NO-FLASH"
OLD_RX_RING = "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t128"
NEW_RX_RING = "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t256"
NAPI_128 = "#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t128"
F222_DRIVER_SHA256 = "4627921b95e0c523d4c7b909f62e1e445bc54da57c8920f930354976ef0f7036"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_builder():
    if not SCRIPT.is_file():
        pytest.skip("F223 builder has not been implemented yet")
    spec = importlib.util.spec_from_file_location("build_f223_emac_rxring256", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_f223_source_changes_only_rx_ring_and_keeps_napi_128() -> None:
    source = DRIVER.read_text(encoding="utf-8")
    assert source.count(NEW_RX_RING) == 1
    assert source.count(NAPI_128) == 1
    reconstructed_f222 = source.replace(NEW_RX_RING, OLD_RX_RING)
    assert hashlib.sha256(reconstructed_f222.encode()).hexdigest() == F222_DRIVER_SHA256


def test_f223_builder_is_offline_and_declares_f222_parent() -> None:
    load_builder()
    text = SCRIPT.read_text(encoding="utf-8")
    assert 'firmware/f222-device-bound' in text
    assert 'source_base = f"openmitrastar-linux510-f222-' in text
    assert NEW_RX_RING.replace("\t", "\\t") in text
    assert NAPI_128.replace("\t", "\\t") in text
    for forbidden in (
        "flash_erase",
        "mtd_debug",
        "fw_setenv",
        "spi_flash write",
        "COM3",
        "reboot",
    ):
        assert forbidden not in text


def test_f223_built_artifact_preserves_f222_rootfs_and_flash_layout() -> None:
    load_builder()
    manifest_path = F223_BUILD / "manifest.json"
    if not manifest_path.is_file():
        pytest.skip("F223 artifact has not been built yet")

    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    parent_path = F222_BUILD / "manifest.json"
    parent = json.loads(parent_path.read_text(encoding="ascii"))
    f222_rootfs = F222_BUILD / f"{F222_BASE}.rootfs.squashfs"
    f223_rootfs = F223_BUILD / f"{F223_BASE}.rootfs.squashfs"
    f222_config = F222_BUILD / f"{F222_BASE}.config"
    f223_config = F223_BUILD / f"{F223_BASE}.config"
    f222_dtb = F222_BUILD / f"{F222_BASE}.dtb"
    f223_dtb = F223_BUILD / f"{F223_BASE}.dtb"

    assert manifest["schema"] == "openmitrastar.f223-emac-rxring256-from-f222/v1"
    assert manifest["change_scope"]["single_variable"] == (
        "qtn-topaz-emac RX ring 128 -> 256 descriptors"
    )
    assert manifest["change_scope"]["napi_weight"] == "unchanged at 128"
    assert manifest["change_scope"]["rootfs"] == "byte-identical to installed F222"
    assert manifest["change_scope"]["kernel_config"] == "byte-identical to installed F222"
    assert manifest["change_scope"]["dtb"] == "byte-identical to installed F222"

    assert sha256(f223_rootfs) == sha256(f222_rootfs)
    assert sha256(f223_config) == sha256(f222_config)
    assert sha256(f223_dtb) == sha256(f222_dtb)
    assert (
        manifest["artifacts"]["rootfs_squashfs"]["bytes"]
        == parent["artifacts"]["rootfs_squashfs"]["bytes"]
    )
    assert (
        manifest["artifacts"]["rootfs_squashfs"]["sha256"]
        == parent["artifacts"]["rootfs_squashfs"]["sha256"]
    )
    assert manifest["artifacts"]["rootfs_squashfs"]["file"] == f"{F223_BASE}.rootfs.squashfs"
    assert manifest["layout"]["mtd_mapping"] == parent["layout"]["mtd_mapping"]
    assert manifest["layout"]["rootfs_window_bytes"] == parent["layout"]["rootfs_window_bytes"]
    assert manifest["layout"]["slot_bytes"] == parent["layout"]["slot_bytes"]
    assert manifest["storage"] == parent["storage"]
    assert manifest["safety"]["protected_partitions"] == "mtd0/mtd1/mtd2/mtd3/mtd5 unchanged"
    assert manifest["safety"]["write_target_if_promoted"].startswith("mtd4/linux_live only")

    assert manifest["binary_contract"]["result"] == "PASS"
    assert manifest["binary_contract"]["rx_ring_descriptors"] == 256
    assert manifest["binary_contract"]["napi_weight"] == 128
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert manifest["physical_validation"]["improvement_claimed"] is False
    assert manifest["contracts"]["hardware_boot"] == "NOT_RUN"
    assert manifest["contracts"]["flash"] is False
