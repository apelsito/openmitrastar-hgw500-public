from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_f205_runtime_signature as f205  # noqa: E402


def test_frozen_runtime_signature_contract() -> None:
    overlay = f205.OVERLAY
    manager = (overlay / "usr/bin/lyoko-pkg").read_text(encoding="utf-8")
    api = (overlay / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    for marker in ("verify_feed_signature", "feed-signature-invalid", "runtime_signature_verification=ed25519-dropbear"):
        assert marker in manager
    assert '"verification_scope":"build-and-runtime"' in api
    assert '"runtime_signature_available":%s' in api
    verifier = overlay / "usr/bin/lyoko-ed25519-verify"
    assert verifier.stat().st_size == 51076
    assert (overlay / "etc/lyoko/keys/feed-ed25519.raw").stat().st_size == 32
    assert (overlay / "usr/share/lyoko/feed/Packages.sig").stat().st_size == 64


def test_built_f205_contract() -> None:
    manifest_path = f205.OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    source = json.loads((f205.SOURCE_BUILD / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f205-runtime-signature/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["release_eligible"] is False
    assert manifest["artifacts"]["kernel_lzma"]["sha256"] == source["artifacts"]["kernel_lzma"]["sha256"]
    assert manifest["layout"]["rootfs_window_bytes"] == 0x620000
    assert manifest["frontend"]["ui_version"] == "2.8.0"
    assert manifest["frontend"]["source"] == "lyoko-foundation-2.8-f205"
    changed = set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"])
    assert "usr/bin/lyoko-ed25519-verify" in changed
    assert "etc/lyoko/keys/feed-ed25519.raw" in changed
    assert "usr/share/lyoko/feed/Packages.sig" in changed
    assert "usr/bin/lyoko-pkg" in changed
    assert "usr/libexec/openmitrastar/om-api-v1" in changed
    assert manifest["private_key_scan"] == "PASS_PATH_ABSENT"
    verifier = manifest["runtime_signature_verifier"]
    assert verifier["bytes"] == 51076
    assert verifier["sha256"] == "831ea6de598834222c6e6e597b13f297aeaf5d472a55de0a7535419e978442b7"
    assert verifier["private_key_in_firmware"] is False
    assert verifier["native_tampered_message"] == "REJECTED"


def test_builder_has_no_hardware_actions() -> None:
    source = Path(f205.__file__).read_text(encoding="utf-8")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "COM3", "reboot"):
        assert forbidden not in source
