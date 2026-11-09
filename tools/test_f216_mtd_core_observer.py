from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "work/kernel-port/modules/qtn-topaz-mtd-observer/qtn-topaz-mtd-observer.c"
OUT = ROOT / "outputs/kernel-port/f216-mtd-core-observer-20260901"


def test_source_uses_mtd_core_without_direct_mmio() -> None:
    text = SOURCE.read_text(encoding="utf-8")
    assert 'get_mtd_device_nm(LYOKO_STORE_NAME)' in text
    assert "put_mtd_device(mtd)" in text
    assert "MTD_WRITEABLE" in text
    assert "ioremap" not in text
    assert "readl" not in text
    assert "writel" not in text
    assert "0xe403" not in text.lower()


def test_built_artifact_contract() -> None:
    manifest_path = OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f216-mtd-core-observer/v1"
    assert manifest["capabilities"]["direct_mmio"] is False
    assert manifest["capabilities"]["read_data"] is False
    assert manifest["capabilities"]["erase"] is False
    assert manifest["capabilities"]["write"] is False
    assert manifest["physical_validation"] == "NOT_RUN"
