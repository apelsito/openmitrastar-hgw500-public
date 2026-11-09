"""Bounded offline checks for F321 identity and protected-runtime boundaries."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import build_f321_classic_ui_candidate as build
from f321_classic_ui_rootfs_worker import SOURCE_RELEASE_HASHES, product_version, release_bytes


RELEASE = b"""OPENMITRASTAR_PRODUCT=openmitrastar
OPENMITRASTAR_MODEL=HGW-500BNA-QCv2
OPENMITRASTAR_PRODUCT_VERSION=lyoko-foundation-6.8.3-f319-spi-owner-claim-device
OPENMITRASTAR_ROOTFS_SCHEMA=1
OPENMITRASTAR_ROOTFS_CLASS=OFFLINE-PRODUCT-INTEGRATION-CANDIDATE-NO-FLASH
OPENMITRASTAR_KERNEL_BASE=5.10.260
OPENMITRASTAR_API_VERSION=v1
OPENMITRASTAR_UI_VERSION=6.8.2
OPENMITRASTAR_BUILD_ID=8ed49ecd05d70ed2
"""


def test_release_transform_changes_only_version_ui_and_build_identity():
    assert hashlib.sha256(RELEASE).hexdigest() == SOURCE_RELEASE_HASHES["f319"]
    updated = release_bytes(RELEASE, "72dd5d1877544af9", "0.2.0-classic", "f319")
    old = dict(line.split("=", 1) for line in RELEASE.decode().splitlines())
    new = dict(line.split("=", 1) for line in updated.decode().splitlines())
    assert {key for key in old if old[key] != new[key]} == {
        "OPENMITRASTAR_PRODUCT_VERSION", "OPENMITRASTAR_UI_VERSION", "OPENMITRASTAR_BUILD_ID"
    }
    assert new["OPENMITRASTAR_PRODUCT_VERSION"] == product_version("f319")


@pytest.mark.parametrize("identity", ["bad", "a" * 17, "a" * 16 + "\n", "$(oops)"])
def test_untrusted_release_identity_is_rejected(identity):
    with pytest.raises(ValueError, match="invalid F321"):
        release_bytes(RELEASE, identity, "0.2.0-classic", "f319")


def test_different_release_base_is_rejected():
    with pytest.raises(ValueError, match="pinned F319"):
        release_bytes(RELEASE.replace(b"f319", b"f320"), "72dd5d1877544af9", "0.2.0-classic", "f319")


def test_radio_change_is_rejected_even_if_changed_files_list_omits_it():
    result = {"checks": {"changed_files": [build.RELEASE_PATH]},
              "before": {"usr/sbin/om-qtnctl": {"sha256": "original", "mode": 0o755}},
              "after": {"usr/sbin/om-qtnctl": {"sha256": "new", "mode": 0o755}}}
    with pytest.raises(ValueError, match="protected runtime"):
        build.verify_candidate_delta(result, {"www/assets/lyoko-next/app-abcd.js"})


def test_extra_module_is_outside_ui_scope():
    result = {"checks": {"changed_files": ["lib/modules/qtn_radar_native.ko"]}, "before": {}, "after": {}}
    with pytest.raises(ValueError, match="outside"):
        build.verify_candidate_delta(result, {"www/assets/lyoko-next/app-abcd.js"})


def test_exact_ui_delta_and_preserved_runtime_are_accepted():
    runtime = {"sha256": "original", "mode": 0o755}
    result = {"checks": {"changed_files": [build.RELEASE_PATH, build.API_PATH, "www/assets/lyoko-next/app-abcd.js"]},
              "before": {"usr/sbin/om-qtnctl": runtime}, "after": {"usr/sbin/om-qtnctl": runtime}}
    build.verify_candidate_delta(result, {"www/assets/lyoko-next/app-abcd.js"})


def test_package_requires_caller_pinned_manifest(tmp_path):
    (tmp_path / "manifest.json").write_text("{}", encoding="ascii")
    with pytest.raises(ValueError, match="manifest hash mismatch"):
        build.validate_package(tmp_path, "0" * 64)


def test_base_rootfs_must_match_bytes_inside_sealed_candidate(tmp_path, monkeypatch):
    manifest = {"artifacts": {"webformat": {"sha256": "pending"}}}
    source_base = "synthetic-base"
    candidate = tmp_path / (source_base + ".webformat.bin")
    rootfs = tmp_path / (source_base + ".rootfs.squashfs")
    candidate.write_bytes(b"HEADERrootfsA")
    rootfs.write_bytes(b"rootfsB")
    monkeypatch.setattr(build, "source_paths", lambda base: (tmp_path, source_base))
    monkeypatch.setattr(build, "ROOTFS_OFFSET", 6)
    monkeypatch.setitem(build.BASE_CANDIDATE_HASHES, "f319", hashlib.sha256(candidate.read_bytes()).hexdigest())
    monkeypatch.setitem(build.SOURCE_ROOTFS_HASHES, "f319", hashlib.sha256(rootfs.read_bytes()).hexdigest())
    (tmp_path / "manifest.json").write_text(json.dumps(manifest), encoding="ascii")
    with pytest.raises(ValueError, match="sidecar"):
        build.validate_base("f319")


def test_f314_release_remains_distinct_from_f319_lineage():
    f314 = RELEASE.replace(b"6.8.3-f319-spi-owner-claim", b"6.8.2-f314-qtn-nondfs-guard").replace(b"8ed49ecd05d70ed2", b"a2775c160f5a9b21")
    assert hashlib.sha256(f314).hexdigest() == SOURCE_RELEASE_HASHES["f314"]
    updated = release_bytes(f314, "72dd5d1877544af9", "0.2.0-classic", "f314")
    assert product_version("f314").encode() in updated
    assert product_version("f314") != product_version("f319")
    with pytest.raises(ValueError, match="pinned F319"):
        release_bytes(f314, "72dd5d1877544af9", "0.2.0-classic", "f319")
