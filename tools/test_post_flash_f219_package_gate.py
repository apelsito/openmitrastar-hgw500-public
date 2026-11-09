from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/post_flash_f219_package_gate.py"


def test_gate_is_volatile_and_checks_signed_lifecycle() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in (
        "lyoko-ed25519-verify",
        "LYOKO_PKG_VERIFY_PASS",
        "LYOKO_PKG_INSTALL_PASS",
        "LYOKO_PKG_REMOVE_PASS",
        "DATA_HASH_BEFORE",
        "DATA_HASH_AFTER",
        "/run/lyoko-packages/f219-physical-gate",
    ):
        assert marker in text
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in text
