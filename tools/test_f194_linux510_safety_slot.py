from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f194_linux510_safety_slot as f194  # noqa: E402


def test_safety_dts_maps_rootfs_inside_mtd3() -> None:
    text = f194.SAFETY_DTS.read_text(encoding="utf-8")
    assert "flash@901c0000" in text
    assert "reg = <0x901c0000 0x00620000>;" in text
    assert 'linux,mtd-name = "rootfs_safety";' in text
    assert 'root=31:3 rootfstype=squashfs ro rootwait' in text
    assert "0x90960000" not in text


def test_builder_requires_exact_f170_control_rebuild() -> None:
    text = Path(f194.__file__).read_text(encoding="utf-8")
    assert "control rebuild does not reproduce the installed F170 kernel" in text
    assert '"netif_napi_add(ndev, &emac->napi, qtn_emac_poll, 64);"' in text
    assert '"napi_weight=%u\\\\npoll_ticks' in text
    assert "reconstructed F170 EMAC source hash mismatch" in text
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "saveenv"):
        assert forbidden not in text


def test_built_safety_contract() -> None:
    manifest_path = f194.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f194-linux510-safety-slot/v1"
    assert manifest["target_slot"] == "mtd3/linux_safety"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["control_rebuild"]["control_kernel_sha256"] == manifest["parents"]["f170_kernel_lzma_sha256"]
    assert manifest["control_rebuild"]["safety_dtb_sha256"] != manifest["control_rebuild"]["live_dtb_sha256"]
    assert manifest["artifacts"]["rootfs_squashfs"]["sha256"] == manifest["parents"]["f170_rootfs_sha256"]
    assert manifest["rootfs_window"]["address"] == "0x901c0000"
    assert manifest["layout"]["mtd_mapping"].startswith("read-only rootfs_safety 0x901c0000")
    assert manifest["safety_bootbase_contract"]["result"] == "PASS"
    assert manifest["safety_bootbase_contract"]["handoff_slot"] == "linux_safety"
    assert manifest["safety_bootbase_contract"]["fallback_slot"] == "linux_live"
    assert manifest["artifacts"]["safety_full_slot"]["bytes"] == 0x7A0000
