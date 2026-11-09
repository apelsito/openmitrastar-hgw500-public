from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F261 = PRIVATE / "f261-device-bound"
F262 = PRIVATE / "f262-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_f262_source_restarts_and_verifies_realtek_hostapd() -> None:
    overlay = ROOT / "versions/lyoko-foundation-4.9.5-f262/overlay"
    rtlctl = (overlay / "usr/sbin/om-rtlctl").read_text(encoding="utf-8")
    radioctl = (overlay / "usr/sbin/om-radioctl").read_text(encoding="utf-8")
    for marker in ("pid_running()", "stop_hostapd()", "start_hostapd()", "hostapd_wait_attempts"):
        assert marker in rtlctl
    assert 'hostapd_cli -p "$ctrl" -i "$iface" reload' not in rtlctl
    assert "nl80211-hostapd-restart" in rtlctl
    assert "nl80211-hostapd-restart" in radioctl
    assert "nl80211-hostapd-reload" not in radioctl


def test_f262_is_single_scope_and_preserves_f261_payload() -> None:
    manifest = json.loads((F262 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f262-rtl-hostapd-restart/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["native_rtl_control"]["backend"] == "nl80211-hostapd-restart"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "usr/sbin/om-radioctl",
        "usr/sbin/om-rtlctl",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F262 / named("f262", suffix)) == sha256(F261 / named("f261", suffix))


def test_f262_sha256sums_are_valid() -> None:
    entries = {}
    for line in (F262 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        entries[name] = digest
    excluded = {"SHA256SUMS", "known_hosts.f262"}
    files = {path.name for path in F262.iterdir() if path.is_file() and path.name not in excluded}
    assert set(entries) == files
    for name, digest in entries.items():
        assert sha256(F262 / name) == digest
