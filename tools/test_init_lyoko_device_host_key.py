from __future__ import annotations

import json
from pathlib import Path
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/init_lyoko_device_host_key.py"


def test_source_never_prints_private_key() -> None:
    text = SCRIPT.read_text(encoding="utf-8")
    assert "private_key_bytes" in text
    assert "read_bytes()" not in text
    assert "workspace_embedded" in text
    assert "must be stored outside the workspace" in text


def test_real_dropbear_key_generation_and_reuse() -> None:
    with tempfile.TemporaryDirectory(prefix="lyoko-device-identity-") as directory:
        root = Path(directory)
        command = ["python", str(SCRIPT), "--device-id", "pytest-device", "--identity-root", str(root)]
        first = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        assert first.returncode == 0, first.stderr
        first_payload = json.loads(first.stdout)
        assert first_payload["created"] is True
        second = subprocess.run(command, cwd=ROOT, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=30, check=False)
        assert second.returncode == 0, second.stderr
        second_payload = json.loads(second.stdout)
        assert second_payload["created"] is False
        assert second_payload["fingerprint"] == first_payload["fingerprint"]
        metadata = json.loads((root / "pytest-device/identity.json").read_text(encoding="utf-8"))
        assert metadata["private_key_bytes"] == 83
        public = (root / "pytest-device/dropbear_ed25519_host_key.pub").read_text(encoding="ascii")
        assert public.startswith("ssh-ed25519 ")
        assert "PRIVATE" not in public
