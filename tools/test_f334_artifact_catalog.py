"""Offline regression for the three stale F325 radio catalogue entries."""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess

import pytest

import f325_shadow_contract as previous
import f334_shadow_contract as contract


UNTOUCHED_MODULE = contract.MODULE_DIR + "/unchanged.ko"
UNTOUCHED_FIRMWARE = "lib/firmware/unchanged.bin"
THREE_STALE = {contract.START_PATH, contract.STOP_PATH, contract.DRIVER_CONTRACT_PATH}


def put(root: Path, relative: str, content: bytes) -> None:
    target = root / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def catalog_bytes(entries: dict[str, bytes]) -> bytes:
    return "".join(f"{contract.digest(data)}  /{path}\n" for path, data in entries.items()).encode("ascii")


@pytest.fixture
def fixture(tmp_path, monkeypatch):
    root = tmp_path / "root"
    original = {path: ("original " + path + "\n").encode("ascii")
                for path in sorted(contract.REQUIRED_CATALOG_UPDATES | {UNTOUCHED_MODULE, UNTOUCHED_FIRMWARE})}
    source_catalog = catalog_bytes(original)
    final = {path: ("final " + path + "\n").encode("ascii") for path in contract.ROOTFS_CHANGE_PATHS}
    for module in (previous, contract):
        monkeypatch.setattr(module, "SOURCE_ARTIFACTS", contract.digest(source_catalog))
        monkeypatch.setattr(module, "QDRV_SHA256", contract.digest(final[contract.QDRV_PATH]))
        monkeypatch.setattr(module, "PROVIDER_SHA256", contract.digest(final[contract.PROVIDER_PATH]))
    for path, data in original.items():
        put(root, path, data)
    put(root, contract.ARTIFACTS_PATH, source_catalog)
    assert contract.verify_artifact_catalog(root)["entries"] == len(original)
    for path, data in final.items():
        put(root, path, data)
    return root, source_catalog, final


def repaired(fixture):
    root, source, final = fixture
    fixed = contract.artifacts_bytes(source, final)
    put(root, contract.ARTIFACTS_PATH, fixed)
    return root, fixed


def test_f325_reproduces_exactly_the_three_observed_stale_entries(fixture):
    root, source, _ = fixture
    old_catalog = previous.artifacts_bytes(source)
    put(root, contract.ARTIFACTS_PATH, old_catalog)
    with pytest.raises(ValueError, match="artifact catalogue mismatch") as error:
        contract.verify_artifact_catalog(root)
    mismatches = set(str(error.value).split(": ", 1)[1].split(", "))
    assert mismatches == THREE_STALE


def test_f334_repairs_all_changed_entries_and_preserves_every_other_digest(fixture):
    root, source, final = fixture
    root, fixed = repaired(fixture)
    old_entries = contract.parse_artifact_catalog(source)
    entries = contract.parse_artifact_catalog(fixed)
    assert set(entries) == set(old_entries) | {contract.PROVIDER_PATH}
    for path, old_hash in old_entries.items():
        assert entries[path] == (contract.digest(final[path]) if path in final else old_hash)
    assert entries[contract.PROVIDER_PATH] == contract.PROVIDER_SHA256
    proof = contract.verify_artifact_catalog(root, fixed)
    assert proof == {"status": "PASS", "entries": len(entries),
                     "catalog_sha256": contract.digest(fixed), "all_entries_verified": True}


@pytest.mark.parametrize("path", sorted(contract.REQUIRED_CATALOG_UPDATES | {
    contract.PROVIDER_PATH, UNTOUCHED_MODULE, UNTOUCHED_FIRMWARE,
}))
def test_complete_catalogue_rejects_tamper_even_in_unchanged_files(fixture, path):
    root, fixed = repaired(fixture)
    put(root, path, b"modified after catalogue generation\n")
    with pytest.raises(ValueError, match="artifact catalogue mismatch"):
        contract.verify_artifact_catalog(root, fixed)


@pytest.mark.parametrize("path", [contract.START_PATH, contract.PROVIDER_PATH, UNTOUCHED_FIRMWARE])
def test_missing_catalogued_file_is_refused(fixture, path):
    root, fixed = repaired(fixture)
    (root / path).unlink()
    with pytest.raises(ValueError, match="missing F334 catalogue artifact"):
        contract.verify_artifact_catalog(root, fixed)


@pytest.mark.parametrize("different_digest", [False, True])
def test_duplicate_rows_are_refused_even_when_the_hash_matches(fixture, different_digest):
    _, fixed = repaired(fixture)
    duplicate = fixed.splitlines()[0]
    if different_digest:
        duplicate = b"0" * 64 + duplicate[64:]
    with pytest.raises(ValueError, match="duplicate F334 catalogue path"):
        contract.parse_artifact_catalog(fixed + duplicate + b"\n")


def test_circular_catalogue_self_hash_is_refused(fixture, monkeypatch):
    _, source, final = fixture
    circular = source + ("0" * 64 + "  /" + contract.ARTIFACTS_PATH + "\n").encode("ascii")
    monkeypatch.setattr(contract, "SOURCE_ARTIFACTS", contract.digest(circular))
    with pytest.raises(ValueError, match="self-hash"):
        contract.artifacts_bytes(circular, final)


@pytest.mark.parametrize("path", ["../outside", "usr/../outside", "usr/./file", "usr//file",
                                  "/usr/file", "usr/file/", "usr\\file", "usr/file name", "C:/file"])
def test_noncanonical_paths_cannot_escape_or_alias_catalogue_entries(path):
    content = ("0" * 64 + "  /" + path + "\n").encode("ascii")
    with pytest.raises(ValueError, match="unsafe F334 catalogue path"):
        contract.parse_artifact_catalog(content)


@pytest.mark.parametrize("content", [b"", b"\n", b"not a checksum\n", b"0" * 64 + b"  /usr/file",
                                    b"0" * 64 + b"  /usr/file\r\n", b"f" * 63 + b"  /usr/file\n",
                                    b"F" * 64 + b"  /usr/file\n", b"0" * 64 + b"  /usr/\xff\n"])
def test_malformed_catalogue_is_refused(content):
    with pytest.raises(ValueError):
        contract.parse_artifact_catalog(content)


def test_source_pin_cannot_be_bypassed_by_rehashing(fixture):
    _, source, final = fixture
    with pytest.raises(ValueError, match="source drift"):
        contract.artifacts_bytes(source + b"\n", final)


def test_missing_required_source_member_is_refused(fixture, monkeypatch):
    _, source, final = fixture
    changed = b"\n".join(line for line in source.splitlines()
                          if not line.endswith(b" /" + contract.START_PATH.encode("ascii"))) + b"\n"
    monkeypatch.setattr(contract, "SOURCE_ARTIFACTS", contract.digest(changed))
    with pytest.raises(ValueError, match="catalogue membership"):
        contract.artifacts_bytes(changed, final)


@pytest.mark.parametrize("kind", ["extra", "missing", "self", "nonbytes"])
def test_unapproved_changes_cannot_be_hidden_by_catalogue_refresh(fixture, kind):
    _, source, final = fixture
    changes = dict(final)
    if kind == "extra":
        changes[UNTOUCHED_FIRMWARE] = b"unapproved change"
    elif kind == "missing":
        changes.pop(contract.STOP_PATH)
    elif kind == "self":
        changes[contract.ARTIFACTS_PATH] = source
    else:
        changes[contract.START_PATH] = "not bytes"
    with pytest.raises(ValueError, match="exact final change set"):
        contract.artifacts_bytes(source, changes)


@pytest.mark.parametrize("path", [contract.QDRV_PATH, contract.PROVIDER_PATH])
def test_binary_pins_survive_catalogue_repair(fixture, path):
    _, source, final = fixture
    changes = dict(final)
    changes[path] += b"altered binary"
    with pytest.raises(ValueError, match="source drift"):
        contract.artifacts_bytes(source, changes)


def test_reextracted_catalogue_cannot_be_changed_to_hide_artifact_tampering(fixture):
    root, fixed = repaired(fixture)
    old_content = (root / UNTOUCHED_MODULE).read_bytes()
    new_content = b"unauthorized but internally consistent replacement"
    put(root, UNTOUCHED_MODULE, new_content)
    tampered = fixed.replace(contract.digest(old_content).encode(), contract.digest(new_content).encode())
    put(root, contract.ARTIFACTS_PATH, tampered)
    with pytest.raises(ValueError, match="installed catalogue bytes changed"):
        contract.verify_artifact_catalog(root, fixed)


def test_catalogue_rejects_symlink_targets(fixture, tmp_path):
    root, fixed = repaired(fixture)
    target = root / UNTOUCHED_MODULE
    outside = tmp_path / "outside"
    outside.write_bytes(target.read_bytes())
    target.unlink()
    try:
        target.symlink_to(outside)
    except OSError:
        pytest.skip("host does not permit creating a test symlink")
    with pytest.raises(ValueError, match="symlink or reparse point"):
        contract.verify_artifact_catalog(root, fixed)


@pytest.mark.skipif(os.name != "posix", reason="real SquashFS tools run in the Linux build environment")
def test_complete_catalogue_survives_real_squashfs_roundtrip(fixture, tmp_path):
    if not shutil.which("mksquashfs") or not shutil.which("unsquashfs"):
        pytest.skip("SquashFS tools are unavailable")
    root, fixed = repaired(fixture)
    packed, unpacked = tmp_path / "fixture.squashfs", tmp_path / "unpacked"
    subprocess.run(["mksquashfs", str(root), str(packed), "-noappend", "-all-root",
                    "-comp", "xz", "-processors", "1", "-no-progress"],
                   check=True, capture_output=True, timeout=30)
    subprocess.run(["unsquashfs", "-processors", "1", "-no-progress", "-d", str(unpacked), str(packed)],
                   check=True, capture_output=True, timeout=30)
    assert contract.verify_artifact_catalog(unpacked, fixed) == contract.verify_artifact_catalog(root, fixed)
    put(unpacked, contract.DRIVER_CONTRACT_PATH, b"post-extraction tamper")
    with pytest.raises(ValueError, match="artifact catalogue mismatch"):
        contract.verify_artifact_catalog(unpacked, fixed)


def test_f334_product_identity_preserves_f325_internal_protocol():
    assert contract.PRODUCT_VERSION == "lyoko-foundation-6.9.5-f334-radar-once-f321-device"
    module = Path(contract.__file__).resolve().parents[1] / 'outputs/kernel-port/f334-qdrv-profile-20260921T105936Z/qdrv-f334-external-radar.ko'
    assert contract.QDRV_SHA256 == contract.digest(module.read_bytes())
    assert contract.QDRV_SHA256 != previous.QDRV_SHA256
    assert contract.PROVIDER_SHA256 == previous.PROVIDER_SHA256
    assert contract.PROVIDER_PATH == previous.PROVIDER_PATH
    source = Path(contract.__file__).read_text(encoding="utf-8")
    assert "lifecycle=f325-single-boot-reset-required" in source
    assert "lifecycle=f334" not in source
    assert "f325-diagnostic-profile-locked-reboot-required" in source


def test_f334_loader_keeps_beacon_readbacks_and_rebinds_only_qdrv(monkeypatch):
    source = b'synthetic already-validated F321 bootstrap'
    monkeypatch.setattr(contract, 'SOURCE_START', contract.digest(source))
    donor = Path(contract.__file__).resolve().parents[1] / 'versions/lyoko-foundation-6.9.0-f315-radar-shadow/overlay/usr/sbin/om-radio5-start'
    output = contract.start_bytes(source, donor.read_bytes())
    assert b'expected_qdrv_sha=$(value QDRV_SHA256 "$contract")' in output
    assert previous.QDRV_SHA256.encode() not in output
    assert b'beacon-preflight-readback' in output and b'beacon-v89-wire-readback' in output
    assert b'openmitrastar_beacon_preflight_enable=1' in output
    assert b'openmitrastar_beacon_v89_wire_enable=1' in output
    assert b'shadow_enable=1 shadow_arm=0' in output
