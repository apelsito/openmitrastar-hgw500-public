from __future__ import annotations

import hashlib
import json
from pathlib import Path


PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F229 = PRIVATE / "f229-device-bound"
F231 = PRIVATE / "f231-device-bound"


def artifact(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f231_preserves_f229_kernel_and_fails_closed_without_qcsapi() -> None:
    manifest_path = F231 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f231-radio-backend-truth/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["radio_control_backend"]["availability"] == "runtime-probed"
    assert manifest["radio_control_backend"]["missing_behavior"].endswith("fail-closed")
    assert manifest["radio_control_backend"]["blocked_reason"] == "qcsapi-control-binary-unavailable"
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F231 / artifact("f231", suffix)) == sha256(F229 / artifact("f229", suffix))
