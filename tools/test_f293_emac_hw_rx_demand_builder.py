from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac-f293-hw-rx-demand.c"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F292 = PRIVATE / "f292-device-bound"
F293 = PRIVATE / "f293-device-bound"
F290_DRIVER = ROOT / "work/kernel-port/linux-5.10/drivers/net/ethernet/qtn/qtn-topaz-emac-f290-rx-restart-context.c"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_keeps_f290_behavior_and_adds_hw_rx_demand_telemetry() -> None:
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
        "qtn_emac_read_rx_stat",
        "QTN_TOPAZ_EMAC_MAC_RXSTAT_FRAMES_TOTAL",
        "poll_last_mac_rx_frames",
        "poll_mac_rx_progress_observations",
        "poll_dma_missed_frames_total",
        "rx_restart_last_mac_rx_progress_age_ms",
        "rx_restart_last_dma_missed_frames_total",
    ):
        assert marker in source
    assert "recent_rx_fault" not in source
    assert "QTN_TOPAZ_EMAC_RX_FAULT_MEMORY_MS" not in source


def test_restart_gate_and_action_are_unchanged_from_f290() -> None:
    baseline = F290_DRIVER.read_text(encoding="utf-8")
    candidate = DRIVER.read_text(encoding="utf-8")
    patterns = (
        r"#define QTN_TOPAZ_EMAC_RX_RESTART_POKES\s+\d+",
        r"#define QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS\s+\d+",
        r"else if \(emac->poll_same_cur_rx_pokes >=\s*QTN_TOPAZ_EMAC_RX_RESTART_POKES\)",
        r"if \(!time_after_eq\(jiffies,\s*emac->poll_last_rx_restart_jiffies \+\s*rx_restart_cooldown\)\)",
        r"qtn_emac_restart_rx_dma\(emac, dma_ctrl\);",
    )
    for pattern in patterns:
        baseline_match = re.search(pattern, baseline)
        candidate_match = re.search(pattern, candidate)
        assert baseline_match is not None
        assert candidate_match is not None
        assert candidate_match.group(0) == baseline_match.group(0)
    assert candidate.count("qtn_emac_restart_rx_dma(emac, dma_ctrl);") == 1
    decision_start = candidate.index("if (!time_after_eq(jiffies,", candidate.index("QTN_TOPAZ_EMAC_RX_RESTART_POKES)"))
    decision_end = candidate.index("qtn_emac_restart_rx_dma(emac, dma_ctrl);", decision_start)
    restart_decision = candidate[decision_start:decision_end]
    assert "poll_last_mac_rx" not in restart_decision
    assert "dma_missed_frames" not in restart_decision


def test_f293_manifest_and_artifact_contract() -> None:
    manifest = json.loads((F293 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f293-emac-hw-rx-demand-from-f292/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["binary_contract"]["result"] == "PASS"
    assert manifest["binary_contract"]["rx_ring_descriptors"] == 256
    assert manifest["binary_contract"]["napi_weight"] == 256
    assert manifest["binary_contract"]["rx_pending_mask"] == "0x1f1"
    telemetry = manifest["binary_contract"]["hardware_rx_demand_telemetry"]
    assert "rx_restart_last_dma_status=" in telemetry
    assert "mac_rx_frames=" in telemetry
    assert "rx_restart_last_mac_rx_progress_age_ms=" in telemetry
    assert "rx_restart_last_dma_missed_frames_total=" in telemetry
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    assert manifest["change_scope"]["single_functional_variable"] == "add read-only Arasan MAC RX-demand and DMA missed-frame telemetry"
    source_manifest = json.loads((F292 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["native_qtn_control"] == source_manifest["native_qtn_control"]
    assert manifest["developer_console"]["firmware_line"] == "F293 Full"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {"etc/openmitrastar/release"}
    assert sha256(F293 / named("f293", ".kernel.lzma")) != sha256(F292 / named("f292", ".kernel.lzma"))
    assert sha256(F293 / named("f293", ".rootfs.squashfs")) != sha256(F292 / named("f292", ".rootfs.squashfs"))
    for suffix in (".config", ".dtb"):
        assert sha256(F293 / named("f293", suffix)) == sha256(F292 / named("f292", suffix))
