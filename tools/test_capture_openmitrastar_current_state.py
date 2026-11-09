from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/capture_openmitrastar_current_state.py"


def test_capture_is_read_only_and_redacted() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    for marker in ("StrictHostKeyChecking=yes", '"read_only": True', '"radio_mutation": False', "lyoko_emac_stats"):
        assert marker in text
    assert '"reboot": False' in text
    assert '"flash": False' in text
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "station_mac", "passphrase"):
        assert forbidden not in text


def test_section_parser() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("current_state", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    parsed = module.sections("noise\n---kernel---\n5.10\n---boot_state---\nready\n")
    assert parsed == {"kernel": "5.10", "boot_state": "ready"}
