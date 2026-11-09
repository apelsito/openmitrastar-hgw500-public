from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac-f291-recent-fault-restart.c"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F290 = PRIVATE / "f290-device-bound"
F291 = PRIVATE / "f291-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_keeps_napi256_and_services_rx_faults() -> None:
    source = DRIVER.read_text(encoding="utf-8")
    assert "#define QTN_TOPAZ_EMAC_RX_RING_COUNT\t256" in source
    assert "#define QTN_TOPAZ_EMAC_NAPI_WEIGHT\t256" in source
    assert source.count("QTN_TOPAZ_EMAC_DMA_IRQ_RX_FAULTS") >= 5
    for marker in (
        "poll_last_rx_fault_jiffies",
        "poll_last_rx_fault_status",
        "rx_restart_last_dma_status",
        "rx_restart_last_head_status",
        "rx_restart_last_fault_age_ms",
    ):
        assert marker in source
    assert "#define QTN_TOPAZ_EMAC_RX_FAULT_MEMORY_MS\t10000" in source
    assert "else if (recent_rx_fault &&" in source


def test_f291_manifest_and_artifact_contract() -> None:
    manifest = json.loads((F291 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f291-emac-recent-fault-restart-from-f290/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["binary_contract"]["result"] == "PASS"
    assert manifest["binary_contract"]["rx_ring_descriptors"] == 256
    assert manifest["binary_contract"]["napi_weight"] == 256
    assert manifest["binary_contract"]["rx_pending_mask"] == "0x1f1"
    assert "rx_restart_last_dma_status=" in manifest["binary_contract"]["restart_context_telemetry"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    assert manifest["change_scope"]["single_functional_variable"] == "gate full RX DMA restart on a remembered RX fault within 10 seconds"
    assert manifest["native_qtn_control"] == json.loads((F290 / "manifest.json").read_text(encoding="ascii"))["native_qtn_control"]
    assert manifest["developer_console"]["firmware_line"] == "F291 Full"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {"etc/openmitrastar/release"}
    assert sha256(F291 / named("f291", ".kernel.lzma")) != sha256(F290 / named("f290", ".kernel.lzma"))
    assert sha256(F291 / named("f291", ".rootfs.squashfs")) != sha256(F290 / named("f290", ".rootfs.squashfs"))
    for suffix in (".config", ".dtb"):
        assert sha256(F291 / named("f291", suffix)) == sha256(F290 / named("f290", suffix))
