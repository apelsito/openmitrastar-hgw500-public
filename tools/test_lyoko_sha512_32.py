from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_sha512_uses_only_32_bit_words() -> None:
    source = (ROOT / "tools/lyoko_sha512_32.c").read_text(encoding="utf-8")
    header = (ROOT / "tools/lyoko_sha512_32.h").read_text(encoding="utf-8")
    assert "uint32_t hi" in header and "uint32_t lo" in header
    assert "uint64_t" not in source + header
    assert "unsigned long long" not in source + header
    assert "wadd5" in source and "wror" in source


def test_builder_has_no_hardware_actions() -> None:
    source = (ROOT / "tools/build_lyoko_sha512_32.sh").read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
    assert "selftest-arc" in source
