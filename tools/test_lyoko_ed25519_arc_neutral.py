from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/build_lyoko_ed25519_arc_neutral.sh"


def test_neutral_verifier_replaces_only_sha512_implementation() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "curve25519.c" in text
    assert "sha512.c" in text
    assert "ENDIAN_NEUTRAL" in text
    assert "LTC_NO_ASM" in text
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in text
