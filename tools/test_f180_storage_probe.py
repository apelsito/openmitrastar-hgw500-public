from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f180_storage_probe as f180  # noqa: E402


def test_variant_dts_has_non_overlapping_read_only_windows() -> None:
    text = f180.DTS.read_text(encoding="utf-8")
    assert 'reg = <0x90960000 0x00460000>;' in text
    assert 'lyoko_store: flash@90dc0000' in text
    assert 'reg = <0x90dc0000 0x001c0000>;' in text
    assert text.count('compatible = "mtd-rom";') >= 5
    assert 'linux,mtd-name = "lyoko_store";' in text


def test_built_storage_contract() -> None:
    manifest_path = f180.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    f179 = json.loads((f180.F179_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f180-storage-readonly-probe/v1"
    assert manifest["layout"]["rootfs_window_bytes"] == 0x460000
    assert manifest["storage"]["store_size"] == "0x001c0000"
    assert manifest["storage"]["store_write"] is False
    assert manifest["artifacts"]["rootfs_squashfs"]["sha256"] != f179["artifacts"]["rootfs_squashfs"]["sha256"]
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] != f179["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["physical_validation"]["status"] == "NOT_RUN"


def test_dtb_contains_store_identity() -> None:
    manifest_path = f180.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    dtb = f180.OUT / f"{f180.BASE}.dtb"
    data = dtb.read_bytes()
    assert b"rootfs_live" in data
    assert b"lyoko_store" in data
