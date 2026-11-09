from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/generate_openmitrastar_current_state.py"


def test_generator_has_authoritative_boundaries() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in ("F194", "F213", "F222", "F223", "F224", "F225", "F226", "F227", "F228", "F229", "F230", "F231", "F232", "F233", "F234", "F235", "F236", "F237", "F238", "F239", "F240", "F241", "F242", "F243", "F244", "F211", "F212", "RECOVERY", "RECOVERY_PROVISIONING", "STORE_FORMAT", "STORE_UPDATE", "F222_FLASH", "F222_GATE", "F222_PACKAGES", "F219_RADIO2_EVALUATION", "F219_RADIO5", "release_blockers"):
        assert marker in text
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "password", "private_key_bytes"):
        assert forbidden not in text
