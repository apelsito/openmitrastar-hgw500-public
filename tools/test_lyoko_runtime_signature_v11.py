import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/packages/lyoko-runtime-signature-v1.1"


def test_builder_does_not_use_private_key() -> None:
    source = (ROOT / "tools/build_lyoko_runtime_signature_v11.py").read_text(encoding="utf-8")
    assert "load_pem_public_key" in source
    assert "Ed25519PrivateKey" not in source
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source


def test_built_assets_match_two_package_index() -> None:
    manifest_path = OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["packages_bytes"] == 859
    assert manifest["packages_sha256"] == "82c32ef43dc325318533615b451dce23b853bd887c17e89852fc47ba8dcd01c9"
    assert manifest["signature_bytes"] == 64
    assert manifest["public_key_bytes"] == 32
    assert manifest["verified_before_write"] is True
