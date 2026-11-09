from __future__ import annotations

import base64
import hashlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/prepare_f196_device_flash_contract.py"


def test_openssh_fingerprint_contract() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "base64.b64decode" in source
    assert "SHA256:" in source
    assert "BLOCKED_RECOVERY_UNPROVEN" in source
    assert '"flash_authorized": False' in source
    assert '"mtd4/linux_live"' in source
    assert "LAB_PROMOTION_ONLY_NOT_RELEASE" in source


def test_known_vector() -> None:
    import importlib.util
    spec = importlib.util.spec_from_file_location("f196_contract", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    raw = b"test-wire-key"
    line = "ssh-ed25519 " + base64.b64encode(raw).decode("ascii")
    expected = "SHA256:" + base64.b64encode(hashlib.sha256(raw).digest()).decode("ascii").rstrip("=")
    assert module.openssh_fingerprint(line) == expected
