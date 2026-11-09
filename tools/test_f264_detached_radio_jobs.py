from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-foundation-6.0.1-f264-full"
OVERLAY = SOURCE / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F263 = PRIVATE / "f263-device-bound"
F264 = PRIVATE / "f264-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_background_jobs_detach_from_ssh_stdio() -> None:
    txn = (OVERLAY / "usr/sbin/om-config-transaction").read_text(encoding="utf-8")
    qtn = (OVERLAY / "usr/sbin/om-qtnctl").read_text(encoding="utf-8")
    rtl = (OVERLAY / "usr/sbin/om-rtlctl").read_text(encoding="utf-8")
    assert ') </dev/null >/dev/null 2>&1 &' in txn
    assert '$hostapd -dd -f "$state/hostapd.log" "$conf" </dev/null >/dev/null 2>&1 &' in qtn
    assert '$hostapd -f "$state/hostapd.log" "$conf" </dev/null >/dev/null 2>&1 &' in rtl


def test_f264_manifest_and_payload_contract() -> None:
    manifest = json.loads((F264 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f264-detached-radio-jobs/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["transaction_hardening"]["background_stdio"] == "detached-from-ssh"
    assert manifest["native_rtl_control"]["backend"] == "nl80211-hostapd-restart"
    assert manifest["developer_console"]["mode"] == "single-developer-console"
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/openmitrastar/release",
        "usr/sbin/om-config-transaction",
        "usr/sbin/om-qtnctl",
        "usr/sbin/om-rtlctl",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F264 / named("f264", suffix)) == sha256(F263 / named("f263", suffix))
