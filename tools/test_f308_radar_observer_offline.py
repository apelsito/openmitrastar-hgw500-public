#!/usr/bin/env python3

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/f308_radar_observer/qtn_radar_observer_f308.c"
MAKEFILE = SOURCE.with_name("Makefile")
BUILDER = ROOT / "tools/build_f308_radar_observer_offline.py"
OUT = ROOT / "outputs/kernel-port/f308-radar-observer-v2-20260904"

EXPECTED_API = {
    "detect_drv_sample_loc_get", "dfs_rqmt_code", "radar_disable", "radar_enable",
    "radar_get_chan", "radar_get_status", "radar_ocac_info_addr_get",
    "radar_record_buffer_pt", "radar_register", "radar_register_is_dfs_chan",
    "radar_register_is_dfs_weather_chan", "radar_register_statcb", "radar_set_bw",
    "radar_set_chan", "radar_set_shared_params", "radar_start", "radar_stop",
    "sta_dfs_is_region_required",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_source_is_fail_closed_and_never_stores_or_invokes_callback() -> None:
    source = SOURCE.read_text(encoding="ascii")
    assert "return false;" in source
    assert "return DFS_RQMT_UNKNOWN;" in source
    assert "return -EOPNOTSUPP;" in source
    assert "backend_ready=0" in source
    assert "tx_authorization=denied" in source
    assert "qdrv_radar_detected" not in source
    assert "mark_radar" not in source
    assert not re.search(r"static\s+.*\(\*.*callback", source)


def test_source_has_no_rf_write_irq_or_worker_primitive() -> None:
    source = SOURCE.read_text(encoding="ascii")
    for marker in (
        "writel", "writeb", "writew", "iowrite", "memcpy_toio",
        "request_irq", "free_irq", "schedule_work", "schedule_delayed_work",
        "timer_setup", "mod_timer", ".proc_write",
    ):
        assert marker not in source
    assert "readl(" in source
    assert "ioremap(" in source


def test_observer_is_inert_by_default_and_bounded() -> None:
    source = SOURCE.read_text(encoding="ascii")
    assert "static bool observe_enable;" in source
    assert "F308_MAX_SAMPLES 18U" in source
    assert "sample_limit == 0 || sample_limit > F308_MAX_SAMPLES" in source
    assert "F308_RING_DEPTH 256U" in source
    assert "samples_meaningful=0" in source
    assert "configuration_known=0" in source
    assert "chronology_proven=0" in source


def test_procfs_is_modern_read_only_and_output_is_sanitized() -> None:
    source = SOURCE.read_text(encoding="ascii")
    assert "struct proc_ops" in source
    assert 'proc_create("status", 0444' in source
    assert 'proc_create("snapshot", 0444' in source
    assert ".proc_read = seq_read" in source
    assert ".proc_write" not in source
    assert "%px" not in source
    output_literals = "\n".join(re.findall(r'"([^"\\]*(?:\\.[^"\\]*)*)"', source))
    assert "physical_address" not in output_literals
    assert "0x%" not in output_literals


def test_all_f302_abi_symbols_are_exported() -> None:
    source = SOURCE.read_text(encoding="ascii")
    exports = set(re.findall(r"EXPORT_SYMBOL\(([^)]+)\);", source))
    assert exports == EXPECTED_API


def test_makefile_builds_only_the_observer() -> None:
    makefile = MAKEFILE.read_text(encoding="ascii")
    objects = [line.strip() for line in makefile.splitlines() if line.strip().startswith("obj-m")]
    assert objects == ["obj-m += qtn_radar_observer_f308.o"]
    assert "qtn_radar_native_f302" not in makefile


def test_builder_is_offline_and_pins_f301_f306_kernel() -> None:
    source = BUILDER.read_text(encoding="utf-8")
    for marker in (
        "EXPECTED_CONFIG_SHA256", "EXPECTED_VMLINUX_SHA256", "EXPECTED_SYMVERS_SHA256",
        "f301-device-bound/manifest.json", "f306-device-bound/manifest.json",
        "F301/F306 kernel lineage mismatch", "reproducible_two_builds",
    ):
        assert marker in source
    for forbidden in (
        "paramiko", "COM3", "192.168.1.90", "tftp.exe",
        "Send-Uart", "Invoke-Router", "Invoke-Ssh",
        "spi_flash read", "spi_flash write",
    ):
        assert forbidden not in source


def test_built_manifest_and_binary_contract() -> None:
    manifest = json.loads((OUT / "manifest.json").read_text(encoding="ascii"))
    assert manifest["status"] == "PASS"
    assert manifest["classification"] == "OFFLINE_BOUNDED_READ_ONLY_OBSERVER_NOT_A_DETECTOR"
    assert manifest["target"]["firmware_lineage"]["byte_identical"] is True
    assert manifest["provider"]["vermagic"] == "5.10.260-openmitrastar-radiohw mod_unload ARC700"
    assert set(manifest["provider"]["exports"]) == EXPECTED_API
    assert manifest["provider"]["reproducible_two_builds"] is True
    assert manifest["behavior"]["observe_enable_default"] is False
    assert manifest["behavior"]["rf_register_writes"] == 0
    assert manifest["behavior"]["callback_invocations"] == 0
    assert manifest["behavior"]["samples_meaningful"] is False
    assert manifest["qdrv_link_probe"]["status"] == "PASS"
    assert all(value is False for value in manifest["safety"].values())
    source_artifacts = {entry["path"]: entry for entry in manifest["source_artifacts"]}
    for path in (SOURCE, MAKEFILE, BUILDER, ROOT / "docs/OPENMITRASTAR_F308_RADAR_OBSERVER.md"):
        relative = path.relative_to(ROOT).as_posix()
        assert source_artifacts[relative]["bytes"] == path.stat().st_size
        assert source_artifacts[relative]["sha256"] == sha256(path)
    provider = OUT / manifest["provider"]["file"]
    assert provider.stat().st_size == manifest["provider"]["bytes"]
    assert sha256(provider) == manifest["provider"]["sha256"]


def test_built_imports_have_no_write_callback_irq_or_worker_symbol() -> None:
    imports = (OUT / "provider-imports.txt").read_text(encoding="ascii").splitlines()
    joined = "\n".join(imports)
    for marker in (
        "writel", "writeb", "writew", "iowrite", "memcpy_toio",
        "request_irq", "free_irq", "schedule", "timer", "qdrv_radar_detected",
    ):
        assert marker not in joined
    for required in ("ioremap", "iounmap", "proc_create", "proc_mkdir", "seq_read"):
        assert required in imports


def test_sha256sums_are_complete_and_valid() -> None:
    lines = (OUT / "SHA256SUMS").read_text(encoding="ascii").splitlines()
    sums = {}
    for line in lines:
        digest, name = line.split("  ", 1)
        sums[name] = digest
    files = {path.name for path in OUT.iterdir() if path.is_file() and path.name != "SHA256SUMS"}
    assert set(sums) == files
    for name, digest in sums.items():
        assert sha256(OUT / name) == digest
