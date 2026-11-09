from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F247 = PRIVATE / "f247-device-bound"
F258 = PRIVATE / "f258-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f258_source_fixes_dispatch_and_stale_lock() -> None:
    overlay = ROOT / "versions/lyoko-foundation-4.9.1-f258/overlay"
    manager = (overlay / "usr/bin/lyoko-pkg").read_text(encoding="utf-8")
    dispatcher = (overlay / "usr/libexec/lyoko/pkgbox-run").read_text(encoding="utf-8")
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    assert "/usr/libexec/lyoko/pkgbox-run" in manager
    assert "ar) exec /usr/libexec/lyoko/ar" in dispatcher
    for applet in ("wc", "mkdir", "rm", "awk", "sha256sum", "tar", "gzip"):
        assert applet in dispatcher
    assert "kill -0" in api and "stale=true" in api


def test_f258_preserves_f247_kernel_and_is_test_candidate() -> None:
    manifest_path = F258 / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f258-package-runtime-fix/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["package_runtime_fix"]["stale_api_lock_recovery"] is True
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F258 / named("f258", suffix)) == sha256(F247 / named("f247", suffix))
