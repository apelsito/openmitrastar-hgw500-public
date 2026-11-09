from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-foundation-6.0-f263-full"
OVERLAY = SOURCE / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F257 = PRIVATE / "f257-device-bound"
F263 = PRIVATE / "f263-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_full_console_and_regulatory_contract() -> None:
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    js = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    radioctl = (OVERLAY / "usr/sbin/om-radioctl").read_text(encoding="utf-8")

    assert 'class="mode-switcher"' not in html
    assert 'class="status-pill developer-pill">Developer<' in html
    assert html.count('data-focus="') >= 9
    assert 'id="dfs-risk-dialog"' in html
    assert 'id="dfs-risk-accept" type="checkbox"' in html
    assert "const dfsChannels = new Set(" in js
    assert "state.dfsBackendReady" in js
    assert "dfs-radar-backend-unavailable" in js
    assert '"candidate_values":[52,56,60,64,100,104,108,112,116,120,124,128,132,136,140]' in radioctl
    assert '"weather_radar":[120,124,128]' in radioctl
    assert '"non_occupancy_seconds":1800' in radioctl
    assert (ROOT / "docs/LYOKO_CHANNEL_POLICY_ES.md").is_file()


def test_full_runtime_includes_all_proven_fixes() -> None:
    pkg = (OVERLAY / "usr/bin/lyoko-pkg").read_text(encoding="utf-8")
    api = (OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    txn = (OVERLAY / "usr/sbin/om-config-transaction").read_text(encoding="utf-8")
    qtn = (OVERLAY / "usr/sbin/om-qtnctl").read_text(encoding="utf-8")
    rtl = (OVERLAY / "usr/sbin/om-rtlctl").read_text(encoding="utf-8")

    assert "pkgbox=/usr/libexec/lyoko/pkgbox-run" in pkg
    assert '"$pkgbox" gunzip -c' in pkg
    assert 'rm -rf "$package_lock"' in api
    assert 'rm -rf "$led_lock"' in api
    assert 'rmdir "$lock_dir"' not in txn
    assert 'ifconfig=${OM_IFCONFIG:-/bin/ifconfig}' in qtn
    assert "stop_hostapd()" in rtl and "start_hostapd()" in rtl
    assert "nl80211-hostapd-restart" in rtl
    for helper in ("ar", "gunzip", "pkgbox-run"):
        assert (OVERLAY / "usr/libexec/lyoko" / helper).is_file()


def test_f263_manifest_and_kernel_contract() -> None:
    manifest = json.loads((F263 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f263-full-lyoko/v1"
    assert manifest["classification"] == "PRIVATE_DEVICE_BOUND_HARDWARE_TEST_CANDIDATE"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["developer_console"]["mode"] == "single-developer-console"
    assert manifest["developer_console"]["ui_version"] == "6.0.0"
    assert manifest["dfs_observability"]["radar_backend_ready"] is False
    assert manifest["storage"]["store_erased_ff"] is True
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F263 / named("f263", suffix)) == sha256(F257 / named("f257", suffix))


def test_f263_sha256sums_are_valid() -> None:
    entries = {}
    for line in (F263 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        entries[name] = digest
    excluded = {"SHA256SUMS", "known_hosts.f263"}
    files = {path.name for path in F263.iterdir() if path.is_file() and path.name not in excluded}
    assert set(entries) == files
    for name, digest in entries.items():
        assert sha256(F263 / name) == digest
