from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]
FOUNDATION = ROOT / "versions/lyoko-foundation-6.6.0-f298-capability-truth"
OVERLAY = FOUNDATION / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F297 = PRIVATE / "f297-device-bound"
F298 = PRIVATE / "f298-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_capability_registry_is_current_and_human_readable() -> None:
    html = (OVERLAY / "www/dashboard.html").read_text(encoding="utf-8")
    css = (OVERLAY / "www/app.css").read_text(encoding="utf-8")
    capability_css = (OVERLAY / "www/capabilities.css").read_text(encoding="utf-8")
    js = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    emulator = (FOUNDATION / "emulator/server.py").read_text(encoding="utf-8")
    registry = json.loads((OVERLAY / "etc/lyoko/capabilities.json").read_text(encoding="utf-8"))
    items = {item["id"]: item for item in registry["items"]}
    assert registry["source"] == "lyoko-f298-evidence-registry"
    assert all(item["mode"] == "developer" for item in items.values())
    assert all(item.get("title") and item.get("description") for item in items.values())
    assert "F290/F292" in items["wifi.2g.ap"]["evidence"]
    assert "F290/F292" in items["wifi.5g.ap"]["evidence"]
    assert items["packages.volatile_install"]["state"] == "available"
    assert items["network.vlan"]["state"] == "blocked"
    assert "F297" in items["network.igmp"]["evidence"]
    assert "F295" in items["storage.protection"]["evidence"]
    assert "item.title || item.id" in js
    assert "item.description" in js
    assert ".capability-id" in capability_css and ".capability-evidence" in capability_css
    assert 'content="6.6.0"' in html
    assert "mac_rx_frames" in emulator


def test_multicast_harness_remains_guarded_and_nonpersistent() -> None:
    feature = (OVERLAY / "etc/openmitrastar/features/multicast-cert-v1").read_text(encoding="ascii")
    backend = (OVERLAY / "usr/sbin/om-multicast-cert").read_text(encoding="utf-8")
    assert feature.strip() == "OPENMITRASTAR_MULTICAST_CERT=1"
    for marker in (
        "OPENMITRASTAR_MULTICAST_CERT_V1",
        "rollback-watchdog",
        "acquire_lock",
        "restore_values",
        "multicast_snooping",
        "multicast_querier",
        "multicast_router",
    ):
        assert marker in backend
    for forbidden in ("flash_erase", "mtd_debug", "spi_flash", "fw_setenv", "/persist", "/dev/mtd"):
        assert forbidden not in backend


def test_observer_remains_packaged_but_has_no_autoload_path() -> None:
    feature = (OVERLAY / "etc/openmitrastar/features/store-protection-observer-v1").read_text(encoding="ascii")
    assert "OPENMITRASTAR_STORE_PROTECTION_OBSERVER=0" in feature
    assert "OPENMITRASTAR_STORE_PROTECTION_AUTOLOAD=0" in feature
    assert "OPENMITRASTAR_STORE_PROTECTION_WRITE_CAPABLE=0" in feature
    init_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (OVERLAY / "etc/init.d").iterdir()
        if path.is_file()
    )
    assert "qtn-topaz-store-protection-observer" not in init_text
    syntax = subprocess.run(["node", "--check", str(OVERLAY / "www/app.js")], capture_output=True, text=True, check=False)
    assert syntax.returncode == 0, syntax.stderr


def test_f298_manifest_is_rootfs_only_offline_hold() -> None:
    manifest = json.loads((F298 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f298-capability-truth-from-f297/v1"
    assert manifest["candidate_eligible"] is False
    assert manifest["flash_supported"] is False
    assert manifest["developer_console"]["emac_diagnostics"] == "interactive hardware RX-demand inspector"
    assert manifest["developer_console"]["store_protection"] == "read-only observer status"
    assert manifest["developer_console"]["capability_registry"] == "human-readable-current-evidence"
    assert manifest["multicast_certification"]["enabled_at_boot"] is False
    assert manifest["multicast_certification"]["feature_available"] is True
    assert manifest["multicast_certification"]["persistent_writes"] is False
    assert manifest["multicast_certification"]["hardware_status"] == "NOT_RUN"
    assert manifest["store_protection_observer"]["autoload"] is False
    assert manifest["store_protection_observer"]["feature_default"] is False
    assert manifest["store_protection_observer"]["read_commands_only"] is True
    assert manifest["store_protection_observer"]["program"] is False
    assert manifest["store_protection_observer"]["erase"] is False
    source_manifest = json.loads((F297 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["store_protection_observer"] == source_manifest["store_protection_observer"]
    assert manifest["native_qtn_control"] == source_manifest["native_qtn_control"]
    assert manifest["native_rtl_control"] == source_manifest["native_rtl_control"]
    assert set(manifest["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {
        "etc/lyoko/frontend.env",
        "etc/lyoko/capabilities.json",
        "etc/openmitrastar/release",
        "usr/share/openmitrastar/web/dashboard.html",
        "www/app.js",
        "www/capabilities.css",
    }
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F298 / named("f298", suffix)) == sha256(F297 / named("f297", suffix))
