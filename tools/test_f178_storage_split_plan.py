from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import plan_f178_storage_split as f178  # noqa: E402


def test_layout_is_aligned_and_stops_before_mtd5() -> None:
    assert f178.ROOTFS_OFFSET == 0x960000
    assert f178.STORE_OFFSET == 0xDC0000
    assert f178.STORE_SIZE == 0x1C0000
    assert f178.STORE_OFFSET + f178.STORE_SIZE == f178.DATA_OFFSET
    assert all(value % f178.ERASE == 0 for value in (f178.ROOTFS_OFFSET, f178.ROOTFS_SIZE, f178.STORE_OFFSET, f178.STORE_SIZE))


def test_generated_plan_preserves_safety_partitions() -> None:
    path = f178.OUT / "manifest.json"
    if not path.is_file():
        return
    plan = json.loads(path.read_text(encoding="ascii"))
    assert plan["status"] == "PASS"
    assert plan["checks"]["mtd3_untouched"] is True
    assert plan["checks"]["mtd5_untouched"] is True
    assert plan["proposed_subregions"]["rootfs_live"]["headroom_bytes"] >= 0x100000
    assert plan["proposed_subregions"]["lyoko_store"]["eraseblocks"] == 28
    assert plan["firmware_update_contract"]["full_mtd4_erase_forbidden_after_store_initialization"] is True
