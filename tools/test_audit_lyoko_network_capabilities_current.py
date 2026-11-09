from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/audit_lyoko_network_capabilities.py"


def test_network_audit_prefers_installed_f222_config() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "F222_CONFIG" in source
    assert "f222-device-bound" in source
    assert "DEFAULT_CONFIG = F222_CONFIG if F222_CONFIG.is_file() else F171_CONFIG" in source
    assert '"kernel_config"' in source
    assert "sha256(args.kernel_config)" in source
