from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f211_lyoko_store_v1 as f211  # noqa: E402


def test_store_geometry_matches_f209_contract() -> None:
    assert f211.STORE_SLOT_OFFSET == 0x5E0000
    assert f211.STORE_SIZE == 0x1C0000
    assert f211.STORE_SLOT_OFFSET + f211.STORE_SIZE == f211.SLOT_SIZE
    assert f211.STORE_SIZE % f211.ERASE_SIZE == 0
    assert f211.PAGE_SIZE == 0x2000


def test_store_builder_has_no_hardware_actions() -> None:
    source = Path(f211.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "serial.Serial", "ssh "):
        assert forbidden not in source


def test_built_store_contract() -> None:
    manifest_path = f211.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    image = f211.OUT / manifest["store"]["file"]
    combined = f211.OUT / manifest["combined_slot"]["file"]
    assert manifest["status"] == "PASS"
    assert manifest["store"]["bytes"] == 0x1C0000
    assert manifest["store"]["eraseblocks"] == 28
    assert manifest["store"]["contains_private_identity"] is False
    assert image.stat().st_size == 0x1C0000
    assert image.read_bytes()[:2] == b"\x85\x19"
    assert combined.stat().st_size == 0x7A0000
    assert all(manifest["checks"].values())
    assert manifest["combined_slot"]["flash_authorized"] is False
