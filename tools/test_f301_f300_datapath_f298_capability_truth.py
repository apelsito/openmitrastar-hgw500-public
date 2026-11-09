from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import stat
import subprocess

import pytest

import build_f301_f300_datapath_f298_capability_truth as builder


DEVICE = "hgw500bna-qcv2-a2-primary"
PRIVATE = Path.home() / ".openmitrastar/devices" / DEVICE / "firmware"
F298 = PRIVATE / "f298-device-bound"
F300 = PRIVATE / "f300-device-bound"
F301 = PRIVATE / "f301-device-bound"
FOUNDATION = builder.FOUNDATION_SOURCE.parent
OVERLAY = builder.FOUNDATION_SOURCE


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest(version: str) -> dict:
    return json.loads((PRIVATE / f"{version}-device-bound" / "manifest.json").read_text(encoding="ascii"))


@pytest.fixture(scope="session")
def extracted() -> dict[str, Path]:
    root = builder.ROOT / ".codex_tmp/test-f301-corrected-rootfs"
    f300 = root / "f300"
    f301 = root / "f301"
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    builder.extract_rootfs(F300 / named("f300", ".rootfs.squashfs"), f300, "podman-mem9-tidb")
    builder.extract_rootfs(F301 / named("f301", ".rootfs.squashfs"), f301, "podman-mem9-tidb")
    yield {"f300": f300, "f301": f301}
    if root.exists():
        shutil.rmtree(root)


def parse_env(path: Path) -> dict[str, str]:
    return dict(line.split("=", 1) for line in path.read_text(encoding="ascii").splitlines() if "=" in line)


def test_source_overlay_is_minimal_and_versioned() -> None:
    actual = {
        path.relative_to(OVERLAY).as_posix()
        for path in OVERLAY.rglob("*")
        if path.is_file()
    }
    assert actual == builder.EXPECTED_ROOTFS_DIFFERENCES - {
        "etc/openmitrastar/release",
        "usr/libexec/openmitrastar/om-oem-cgi",
    }
    assert FOUNDATION.name == "lyoko-foundation-6.6.1-f301-f300-capability-truth"


def test_capability_registry_uses_f300_physical_evidence() -> None:
    registry = json.loads((OVERLAY / "etc/lyoko/capabilities.json").read_text(encoding="utf-8"))
    items = {item["id"]: item for item in registry["items"]}
    assert registry["source"] == "lyoko-f301-f300-evidence-registry"
    assert len(items) == 23
    assert all(item["mode"] == "developer" for item in items.values())
    assert "F300 físico" in items["wifi.2g.ap"]["evidence"]
    assert "27,929/14,861 Mbps" in items["wifi.2g.ap"]["evidence"]
    assert "F300 físico" in items["wifi.5g.ap"]["evidence"]
    assert "120 s" in items["wifi.5g.ap"]["evidence"]
    assert items["diagnostics.rx-demand"]["state"] == "available"
    assert "streak 2" in items["diagnostics.rx-demand"]["evidence"]
    assert "2510 ms" in items["diagnostics.emac"]["evidence"]


def test_dashboard_and_frontend_identity_are_f301() -> None:
    html = (OVERLAY / "usr/share/openmitrastar/web/dashboard.html").read_text(encoding="utf-8")
    env = parse_env(OVERLAY / "etc/lyoko/frontend.env")
    assert 'content="6.6.1"' in html
    for asset in ("app.css", "layout-fixes.css", "capabilities.css", "app.js"):
        assert f"{asset}?v=6.6.1-f301" in html
    assert env["LYOKO_UI_VERSION"] == "6.6.1"
    assert env["LYOKO_UI_SOURCE"] == "lyoko-foundation-6.6.1-f301-f300-capability-truth"


def test_frontend_hashes_cover_every_relevant_css_and_js(extracted: dict[str, Path]) -> None:
    root = extracted["f301"]
    env = parse_env(root / "etc/lyoko/frontend.env")
    total = 0
    for key, relative in builder.FRONTEND_ASSETS.items():
        path = root / relative
        assert env[key] == sha256(path)
        total += path.stat().st_size
    assert int(env["LYOKO_UI_ASSET_BYTES"]) == total


def test_api_publishes_explicit_asset_hash_labels() -> None:
    api = (OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")
    for label in (
        "dashboard_html_sha256",
        "app_js_sha256",
        "app_css_sha256",
        "capabilities_css_sha256",
        "layout_fixes_css_sha256",
        "login_html_sha256",
        "login_css_sha256",
    ):
        assert label in api
    for key in builder.FRONTEND_ASSETS:
        assert key in api


def test_app_understands_f300_hardware_demand_metrics_and_zero_age() -> None:
    js = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    for field in (
        "rx_restart_reason_hw_demand",
        "mac_rx_frames_delta",
        "mac_rx_progress_streak",
        "mac_rx_progress_streak_max",
        "rx_restart_last_mac_rx_progress_streak",
        "rx_restart_last_trigger_pokes",
    ):
        assert field in js
    assert "current.restartMacProgressAgeMs >= 0" in js
    assert "current.restartMacProgressAgeMs > 0" not in js
    assert "current.macRxFramesValid && restartProgressAgeValid && restartProgressEvidence" in js
    assert "current.restartMacProgressStreak >= 2" in js
    syntax = subprocess.run(["node", "--check", str(OVERLAY / "www/app.js")], capture_output=True, text=True)
    assert syntax.returncode == 0, syntax.stderr


def test_f301_manifest_declares_corrected_composition() -> None:
    f298 = manifest("f298")
    f300 = manifest("f300")
    f301 = manifest("f301")
    assert f301["schema"] == "openmitrastar.f301-f300-datapath-f301-capability-truth/v2"
    assert f301["classification"] == "PRIVATE_DEVICE_BOUND_INTEGRATED_HARDWARE_TEST_CANDIDATE"
    assert f301["candidate_eligible"] is True
    assert f301["release_eligible"] is False
    assert f301["flash_supported"] is True
    assert f301["physical_validation"]["status"] == "NOT_RUN"
    assert f301["source"]["f300_kernel_lzma_sha256"] == f300["artifacts"]["kernel_lzma"]["sha256"]
    assert f301["source"]["f300_rootfs_sha256"] == f300["artifacts"]["rootfs_squashfs"]["sha256"]
    assert f301["source"]["f298_feature_contract_source"] == f298["artifacts"]["rootfs_squashfs"]["sha256"]
    assert f301["integration"]["f300_kernel_artifacts_byte_identical"] is True
    assert f301["integration"]["f300_rootfs_is_functional_base"] is True
    assert f301["integration"]["additional_kernel_changes"] == []
    assert set(f301["integration"]["additional_rootfs_changes"]) == builder.EXPECTED_ROOTFS_CHANGES
    assert f301["developer_console"]["firmware_line"] == "F301 Full"
    assert f301["developer_console"]["ui_version"] == "6.6.1"


def test_all_kernel_side_artifacts_are_byte_identical_to_f300() -> None:
    for suffix in (
        ".uncompressed.uImage",
        ".kernel.raw.bin",
        ".kernel.lzma",
        ".config",
        ".dtb",
        ".vmlinux",
    ):
        assert sha256(F301 / named("f301", suffix)) == sha256(F300 / named("f300", suffix))


def test_rootfs_is_f300_plus_only_expected_paths(extracted: dict[str, Path]) -> None:
    f301 = manifest("f301")
    assert sha256(F301 / named("f301", ".rootfs.squashfs")) != sha256(F300 / named("f300", ".rootfs.squashfs"))
    assert sha256(F301 / named("f301", ".rootfs.squashfs")) != sha256(F298 / named("f298", ".rootfs.squashfs"))
    diff = f301["foundation_assets"]["rootfs_diff"]
    assert set(diff["changed_paths"]) == builder.EXPECTED_ROOTFS_CHANGES
    assert diff["new"]["lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage"]["mode"] == 0o755
    for name, expected_mode in builder.EXPECTED_MODES.items():
        assert diff["new"][name]["mode"] == expected_mode
    packed_modes = builder.squashfs_modes(F301 / named("f301", ".rootfs.squashfs"), "podman-mem9-tidb")
    for name, expected_mode in builder.EXPECTED_MODES.items():
        assert packed_modes[name] == expected_mode


def test_radio_payload_is_byte_identical_to_f300(extracted: dict[str, Path]) -> None:
    f301 = manifest("f301")
    f300_inventory = builder.tree_inventory(extracted["f300"], "podman-mem9-tidb")
    f301_inventory = builder.tree_inventory(extracted["f301"], "podman-mem9-tidb")
    f300_radio = builder.radio_hashes(builder.file_hashes(f300_inventory))
    f301_radio = builder.radio_hashes(builder.file_hashes(f301_inventory))
    assert len(f300_radio) > 50
    assert f301_radio == f300_radio
    assert f301["integration"]["radio_payload_file_count"] == len(f300_radio)
    assert f301["integration"]["radio_payload_sha256"] == builder.map_digest(f300_radio)


def test_packaged_runtime_has_no_obsolete_f298_or_pending_f293_labels(extracted: dict[str, Path]) -> None:
    builder.validate_runtime_text(extracted["f301"], "podman-mem9-tidb")


def test_store_observer_disabled_and_multicast_harness_guarded(extracted: dict[str, Path]) -> None:
    root = extracted["f301"]
    feature = (root / "etc/openmitrastar/features/store-protection-observer-v1").read_text(encoding="ascii")
    assert "OPENMITRASTAR_STORE_PROTECTION_OBSERVER=0" in feature
    assert "OPENMITRASTAR_STORE_PROTECTION_AUTOLOAD=0" in feature
    assert "OPENMITRASTAR_STORE_PROTECTION_WRITE_CAPABLE=0" in feature
    init_text = "\n".join(path.read_text(encoding="utf-8") for path in (root / "etc/init.d").iterdir() if path.is_file())
    assert "qtn-topaz-store-protection-observer" not in init_text
    multicast = (root / "usr/sbin/om-multicast-cert").read_text(encoding="utf-8")
    for marker in ("OPENMITRASTAR_MULTICAST_CERT_V1", "rollback-watchdog", "acquire_lock", "restore_values"):
        assert marker in multicast
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "/dev/mtd"):
        assert forbidden not in multicast


def test_f300_datapath_and_control_contracts_are_preserved() -> None:
    f300 = manifest("f300")
    f301 = manifest("f301")
    assert f301["binary_contract"] == f300["binary_contract"]
    assert f301["inherited_f300_contracts"] == f300["contracts"]
    for key in ("native_qtn_control", "native_rtl_control", "config_apply", "transaction_hardening"):
        assert f301[key] == f300[key]
    assert f301["binary_contract"]["early_restart_samples"] == 2
    assert f301["binary_contract"]["fallback_restart_pokes"] == 16


def test_private_identity_and_security_are_unchanged() -> None:
    f300 = manifest("f300")
    f301 = manifest("f301")
    assert f301["device_identity"] == f300["device_identity"]
    assert f301["web_identity"] == f300["web_identity"]
    assert f301["web_security"] == f300["web_security"]
    known_hosts = (F301 / "known_hosts.f301").read_text(encoding="ascii")
    assert known_hosts.startswith("192.168.1.90 ssh-ed25519 ")
    assert f301["device_identity"]["fingerprint"] not in known_hosts


def test_candidate_layout_hashes_and_bootbase_contract() -> None:
    f301 = manifest("f301")
    candidate = F301 / f301["artifacts"]["webformat"]["file"]
    rootfs = F301 / named("f301", ".rootfs.squashfs")
    data = candidate.read_bytes()
    assert candidate.stat().st_size == f301["artifacts"]["webformat"]["bytes"]
    assert sha256(candidate) == f301["artifacts"]["webformat"]["sha256"]
    assert data[builder.ROOTFS_OFFSET:] == rootfs.read_bytes()
    assert data[builder.ROOTFS_OFFSET:builder.ROOTFS_OFFSET + 4] == b"hsqs"
    assert candidate.stat().st_size <= builder.STORE_SLOT_OFFSET
    assert f301["contracts"]["bootbase"] == "PASS"
    assert f301["contracts"]["slot_fit"] is True
    assert f301["contracts"]["hardware_boot"] == "NOT_RUN"
    assert f301["contracts"]["flash"] is False
    assert json.loads((F301 / "bootbase-contract.json").read_text(encoding="utf-8"))["result"] == "PASS"


def test_sha256sums_cover_every_packaged_artifact() -> None:
    sums = {}
    for line in (F301 / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        digest, name = line.split("  ", 1)
        sums[name] = digest
    files = {
        path.name
        for path in F301.iterdir()
        if path.is_file() and path.name != "SHA256SUMS" and not path.name.startswith("known_hosts.f301")
    }
    assert set(sums) == files
    for name in files:
        assert sums[name] == sha256(F301 / name)


def test_offline_builder_contains_no_hardware_transport() -> None:
    source = Path(builder.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "COM3",
        "plink",
        "ssh.exe",
        "tftp.exe",
        "Start-Tftp",
        "flash_erase",
        "mtd_debug",
        "reboot",
        "power-cycle",
    ):
        assert forbidden not in source
    assert '"hardware_actions": {"router": False, "uart": False, "ssh": False, "tftp": False, "flash": False}' in source


def test_authenticated_dashboard_route_is_built_into_f301() -> None:
    source = Path(builder.__file__).read_text(encoding="utf-8")
    assert "redirect /dashboard.cgi" in source
    assert "Location: /dashboard.cgi" in source
    assert "dashboard.cgi) title='Lyoko'; view='dashboard'" in source
    assert "cat /usr/share/openmitrastar/web/dashboard.html" in source
    assert '"usr/libexec/openmitrastar/om-oem-cgi": 0o755' in source
