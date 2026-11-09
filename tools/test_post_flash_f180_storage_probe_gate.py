from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tools/post_flash_f180_storage_probe_gate.py"


def test_gate_is_read_only_and_checks_exact_layout() -> None:
    text = GATE.read_text(encoding="utf-8")
    assert '"00460000"' in text
    assert 'mtd3: 00460000 00010000 "rootfs_live"' in text
    assert 'mtd4: 001c0000 00010000 "lyoko_store"' in text
    assert "store_write_attempted" in text
    for forbidden in ("flash_erase", "mtd_debug write", "dd of=", "mount /dev/mtdblock4"):
        assert forbidden not in text
