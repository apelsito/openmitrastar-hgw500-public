"""Small offline transformation and shell-fixture checks for F322."""
from __future__ import annotations

from pathlib import Path
import subprocess

import pytest

import f322_shadow_contract as contract
from build_f321_classic_ui_candidate import wsl_path
import test_lyoko_dfs_observation_contract as observation
from test_lyoko_dfs_observation_contract import observer as base_observer


ROOT = Path(__file__).resolve().parents[1]
BASE_OVERLAY = ROOT / "versions/lyoko-foundation-6.8.2-f314-qtn-nondfs-guard/overlay"
DONOR = ROOT / "versions/lyoko-foundation-6.9.0-f315-radar-shadow/overlay/usr/sbin/om-radio5-start"
OBSERVER = ROOT / "versions/lyoko-foundation-6.9.1-f322-shadow/overlay/usr/sbin/om-dfs-status"


def test_bootstrap_reuses_verified_shadow_with_no_auto_arm():
    source = (BASE_OVERLAY / contract.START_PATH).read_bytes()
    output = contract.start_bytes(source, DONOR.read_bytes())
    assert b"shadow_enable=1 shadow_arm=0" in output
    assert b">/sys/module/qtn_radar_shadow_f315/parameters/shadow_arm" not in output
    assert b"grep -qx 'configured=0'" in output
    assert b"grep -qx 'callback_invocations=0'" in output
    assert b"authoritative_enable=1" not in output
    assert b"weather_enable=1" not in output


def test_api_adds_only_authenticated_read_route():
    rootfs = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f321-f314-device-bound/openmitrastar-linux510-f321-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.rootfs.squashfs"
    contract.pinned(rootfs.read_bytes(), contract.SOURCE_ROOTFS, "test F321 rootfs")
    source = subprocess.run(
        ["wsl.exe", "-d", "podman-mem9-tidb", "-u", "root", "-e", "unsquashfs", "-cat", wsl_path(rootfs), contract.API_PATH],
        stdin=subprocess.DEVNULL, capture_output=True, check=True, timeout=30,
    ).stdout
    output = contract.api_bytes(source)
    begin = output.index(b"\nradios/5g/dfs)\n")
    end = output.index(b"\nradios/2g|radios/5g)\n", begin)
    branch = output[begin:end]
    assert b"\trequire_read\n" in branch
    assert b"status 2>/dev/null" in branch
    assert b"stage" not in branch and b"apply" not in branch
    assert output[:begin] + output[end:] == source
    assert b'"asset_layout":"split-v1"' in output


def test_bootstrap_refuses_changed_donor():
    with pytest.raises(ValueError, match="source drift"):
        contract.start_bytes((BASE_OVERLAY / contract.START_PATH).read_bytes(), DONOR.read_bytes() + b"\n")


def test_artifact_catalogue_changes_only_qdrv_and_new_provider(monkeypatch):
    old = ("a" * 64 + "  /" + contract.QDRV_PATH + "\n" + "b" * 64 + "  /lib/modules/untouched.ko\n").encode()
    monkeypatch.setattr(contract, "SOURCE_ARTIFACTS", contract.digest(old))
    result = contract.artifacts_bytes(old)
    assert ("b" * 64 + "  /lib/modules/untouched.ko\n").encode() in result
    assert (contract.QDRV_SHA256 + "  /" + contract.QDRV_PATH).encode() in result
    assert (contract.PROVIDER_SHA256 + "  /" + contract.PROVIDER_PATH).encode() in result
    assert len(result.splitlines()) == 3


@pytest.fixture
def shadow_observer(monkeypatch, base_observer):
    monkeypatch.setattr(observation, "HELPER", OBSERVER)
    root, request = base_observer
    observation.write(root / "proc/status", "schema=openmitrastar.radar-shadow-f315/v1\nbackend_ready=0\ndfs_enable=0\nshadow_arm=0\nconfigured=0\npolling=0\npoll_runs=0\ncallback_invocations=0\nconfig_failures=0\nmmio_write_refusals=0\n")
    observation.write(root / "proc/snapshot", "schema=openmitrastar.radar-shadow-f315/v1\nsequence=0\nregisters_stable=0\nraw_count=0\nprocessed_count=0\nzc_count=0\n")
    return root, request


def test_shadow_is_visible_without_claiming_authority(shadow_observer):
    _, request = shadow_observer
    result = request()
    assert result["available"] is True and result["mode"] == "shadow"
    assert result["acquisition"]["armed"] is False
    assert result["detector"]["running"] is False
    assert result["backend_ready"] is False
    assert result["dfs_tx_authorized"] is None
    assert result["controls"] == {"apply": False, "bypass": False}


def test_acquisition_counts_do_not_become_detector_permission(shadow_observer):
    root, request = shadow_observer
    text = (root / "proc/status").read_text().replace("shadow_arm=0", "shadow_arm=1").replace("configured=0", "configured=1").replace("polling=0", "polling=1").replace("poll_runs=0", "poll_runs=12")
    observation.write(root / "proc/status", text)
    observation.write(root / "proc/snapshot", "schema=openmitrastar.radar-shadow-f315/v1\nsequence=12\nregisters_stable=1\nraw_count=2\nprocessed_count=2\nzc_count=1\n")
    result = request()
    assert result["acquisition"]["armed"] is True
    assert result["acquisition"]["polls"] == 12
    assert result["acquisition"]["raw_pulses"] == 2
    assert result["acquisition"]["physical_rf_detection_proven"] is False
    assert result["acquisition"]["liveness_verified"] is False
    assert result["detector"]["running"] is False
    assert result["tx"]["authorized"] is None


def test_shadow_observer_does_not_accept_native_provider_schema(shadow_observer):
    root, request = shadow_observer
    observation.write(root / "proc/status", "schema=openmitrastar.radar-native-f316/v1\nbackend_ready=1\n")
    result = request()
    assert result["available"] is False
    assert result["backend_ready"] is None
    assert result["acquisition"]["armed"] is None
