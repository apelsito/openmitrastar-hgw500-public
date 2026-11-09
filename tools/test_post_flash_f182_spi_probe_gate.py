from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "tools/post_flash_f182_spi_probe_gate.py"


def test_gate_requires_expected_read_only_probe_state() -> None:
    text = GATE.read_text(encoding="utf-8")
    for marker in (
        "lyoko-foundation-1.3-f182",
        "jedec_id=12722200",
        "expected_device=Y",
        "write_capable=N",
        "write_attempted",
    ):
        assert marker in text
    for forbidden in ("insmod", "rmmod", "writel", "flash_erase", "mtd_debug write", "dd of="):
        assert forbidden not in text
