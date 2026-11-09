from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re

import build_f299_emac_hw_demand_early_restart_from_f293 as f299
import build_f300_emac_hw_demand_two_sample_from_f299 as builder


ROOT = Path(__file__).resolve().parents[1]
DEVICE = "hgw500bna-qcv2-a2-primary"
PRIVATE = Path.home() / ".openmitrastar/devices" / DEVICE / "firmware"
F293 = PRIVATE / "f293-device-bound"
F299 = PRIVATE / "f299-device-bound"
F300 = PRIVATE / "f300-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rendered_source() -> str:
    return builder.render_f300_driver(builder.BASE_DRIVER.read_text(encoding="utf-8"))


def test_render_is_deterministic_and_does_not_mutate_parent_sources() -> None:
    before = builder.BASE_DRIVER.read_bytes()
    f299_builder_before = Path(f299.__file__).read_bytes()
    first = rendered_source()
    second = rendered_source()
    assert first == second
    assert builder.BASE_DRIVER.read_bytes() == before
    assert Path(f299.__file__).read_bytes() == f299_builder_before
    assert hashlib.sha256(first.encode()).hexdigest() != hashlib.sha256(before).hexdigest()


def test_early_gate_requires_two_consecutive_samples_and_all_safety_conditions() -> None:
    source = rendered_source()
    assert "#define QTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES\t2" in source
    stall_guard = re.search(
        r"if \(!pending && idle_ms >= QTN_TOPAZ_EMAC_POLL_STALL_POKE_MS.*?"
        r"hw_rx_demand_restart =(?P<gate>.*?)"
        r"if \(!\(rx_head_status & QTN_EMAC_DESC_OWN\)\)",
        source,
        re.S,
    )
    assert stall_guard is not None
    gate = stall_guard.group("gate")
    assert "poll_same_cur_rx_pokes >=" in gate
    assert "QTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES" in gate
    assert "poll_same_cur_rx_pokes <" in gate
    assert "QTN_TOPAZ_EMAC_RX_RESTART_POKES" in gate
    assert "poll_mac_rx_progress_streak >=" in gate
    assert source.index("hw_rx_demand_restart =") < source.index("if (!(rx_head_status & QTN_EMAC_DESC_OWN))")
    assert re.search(
        r"else if \(emac->poll_same_cur_rx_pokes >=\s*"
        r"QTN_TOPAZ_EMAC_RX_RESTART_POKES \|\|\s*hw_rx_demand_restart\)",
        source,
    )


def test_only_functional_source_delta_from_f299_is_confirmation_threshold() -> None:
    base = builder.BASE_DRIVER.read_text(encoding="utf-8")
    parent = f299.render_f299_driver(base)
    candidate = rendered_source()
    expected = parent.replace(
        "#define QTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES\t4",
        "#define QTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES\t2",
        1,
    )
    assert candidate == expected


def test_progress_streak_is_consecutive_and_fail_closed() -> None:
    source = rendered_source()
    assert "mac_rx_delta && emac->poll_same_cur_rx_pokes" in source
    assert source.count("emac->poll_mac_rx_progress_streak = 0;") >= 5
    assert "if (emac->poll_mac_rx_progress_streak != U32_MAX)" in source
    assert "emac->poll_mac_rx_progress_streak++;" in source
    assert "emac->poll_mac_rx_progress_streak_max = max(" in source
    assert "emac->poll_mac_rx_read_failures++;\n\t\t\temac->poll_mac_rx_progress_streak = 0;" in source


def test_f290_fallback_cooldown_and_restart_sequence_remain_intact() -> None:
    baseline = builder.BASE_DRIVER.read_text(encoding="utf-8")
    candidate = rendered_source()
    restart_sequence = (
        "qtn_emac_restart_rx_dma(emac, dma_ctrl);\n"
        "\t\t\temac->poll_same_cur_rx_pokes = 0;\n"
        "\t\t\temac->poll_last_progress_jiffies = jiffies;\n"
        "\t\t\temac->poll_last_rx_restart_jiffies = jiffies;\n"
        "\t\t\trx_restarted = true;"
    )
    for marker in (
        "#define QTN_TOPAZ_EMAC_RX_RESTART_POKES\t16",
        "#define QTN_TOPAZ_EMAC_RX_RESTART_COOLDOWN_MS\t10000",
        "if (!time_after_eq(jiffies,\n"
        "\t\t\t\t\t   emac->poll_last_rx_restart_jiffies +\n"
        "\t\t\t\t\t   rx_restart_cooldown))",
        "qtn_emac_restart_rx_dma(emac, dma_ctrl);",
        "emac->poll_last_progress_jiffies = jiffies;",
        "emac->poll_last_rx_restart_jiffies = jiffies;",
    ):
        assert marker in baseline
        assert marker in candidate
    assert restart_sequence in baseline
    assert restart_sequence in candidate
    assert candidate.count("qtn_emac_restart_rx_dma(emac, dma_ctrl);") == 1
    assert "QTN_TOPAZ_EMAC_RX_FAULT_MEMORY_MS" not in candidate
    assert "recent_rx_fault" not in candidate


def test_only_expected_driver_semantics_are_added() -> None:
    source = rendered_source()
    builder.verify_source_contract(source)
    for marker in (
        "rx_restart_reason_hw_demand",
        "rx_restart_last_mac_rx_progress_streak",
        "rx_restart_last_trigger_pokes",
        "mac_rx_progress_streak=",
        "mac_rx_progress_streak_max=",
    ):
        assert marker in source
    assert "QTN_TOPAZ_EMAC_RX_RING_COUNT\t256" in source
    assert "QTN_TOPAZ_EMAC_NAPI_WEIGHT\t256" in source
    assert "QTN_TOPAZ_EMAC_TX_RING_COUNT\t64" in source
    assert "QTN_TOPAZ_EMAC_RX_BUF_SIZE\t2048" in source


def test_f300_manifest_and_artifact_contract() -> None:
    manifest = json.loads((F300 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f300-emac-hw-demand-two-sample-from-f299/v1"
    assert manifest["classification"] == "PRIVATE_DEVICE_BOUND_OFFLINE_HARDWARE_TEST_CANDIDATE"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["contracts"]["hardware_boot"] == "NOT_RUN"
    assert manifest["contracts"]["flash"] is False
    assert manifest["physical_validation"]["status"] == "NOT_RUN"
    assert manifest["physical_validation"]["improvement_claimed"] is False
    assert manifest["binary_contract"]["result"] == "PASS"
    assert manifest["binary_contract"]["rx_ring_descriptors"] == 256
    assert manifest["binary_contract"]["napi_weight"] == 256
    assert manifest["binary_contract"]["rx_pending_mask"] == "0x1f1"
    assert manifest["binary_contract"]["fallback_restart_pokes"] == 16
    assert manifest["binary_contract"]["early_restart_samples"] == 2
    assert manifest["change_scope"]["single_functional_variable"] == (
        "reduce the F299 hardware-ingress confirmation threshold from four consecutive samples to two"
    )
    assert manifest["change_scope"]["early_gate"]["same_cur_rx_samples"] == 2
    assert manifest["change_scope"]["early_gate"]["mac_frames_rx_total_progress_samples"] == 2
    assert manifest["change_scope"]["radio5"].endswith("byte-identical to F299")
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/openmitrastar/release"
    }
    assert manifest["developer_console"]["firmware_line"] == "F300 Full"
    assert sha256(F300 / named("f300", ".kernel.lzma")) != sha256(F299 / named("f299", ".kernel.lzma"))
    assert sha256(F300 / named("f300", ".rootfs.squashfs")) != sha256(F299 / named("f299", ".rootfs.squashfs"))
    for suffix in (".config", ".dtb"):
        assert sha256(F300 / named("f300", suffix)) == sha256(F299 / named("f299", suffix))


def test_f300_hashes_and_slot_boundaries() -> None:
    manifest = json.loads((F300 / "manifest.json").read_text(encoding="ascii"))
    candidate = F300 / manifest["artifacts"]["webformat"]["file"]
    assert candidate.stat().st_size == manifest["artifacts"]["webformat"]["bytes"]
    assert sha256(candidate) == manifest["artifacts"]["webformat"]["sha256"]
    assert candidate.stat().st_size <= builder.STORE_SLOT_OFFSET
    sums = {}
    for line in (F300 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    for path in F300.iterdir():
        if path.is_file() and path.name != "SHA256SUMS" and not path.name.startswith("known_hosts.f300"):
            assert sums[path.name] == sha256(path)
