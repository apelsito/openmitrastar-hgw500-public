from copy import deepcopy
import hashlib
from pathlib import PurePosixPath

import pytest

from lyoko_web_rootfs_worker import validate_delta, validate_overlay


PATHS = ["etc/lyoko/web-next.env", "usr/share/openmitrastar/web/dashboard.html",
         "www/assets/lyoko-next/ui-ABC123.js", "www/assets/lyoko-next/ui-ABC123.css"]


def fixture_delta():
    expected = {path: {"path": path, "mode": "0644", "bytes": 3, "sha256": "a" * 64} for path in PATHS}
    parents = {str(parent) for path in PATHS for parent in PurePosixPath(path).parents}
    directory = {"type": "dir", "mode": 0o755, "uid": 0, "gid": 0}
    before = {path: dict(directory) for path in parents - {"www/assets/lyoko-next"}}
    before["etc/private"] = {**directory, "mode": 0o700}
    before["tmp"] = {**directory, "mode": 0o1777}
    before["www/dashboard.cgi"] = {"type": "file", "mode": 0o755, "uid": 0, "gid": 0, "bytes": 8, "sha256": "b" * 64}
    before["bin/sh"] = {"type": "symlink", "mode": 0o777, "uid": 0, "gid": 0, "target": "busybox"}
    before[PATHS[1]] = {"type": "file", "mode": 0o644, "uid": 0, "gid": 0, "bytes": 10, "sha256": "b" * 64}
    after = deepcopy(before)
    after["www/assets/lyoko-next"] = dict(directory)
    for path in expected:
        after[path] = {"type": "file", "mode": 0o644, "uid": 0, "gid": 0, "bytes": 3, "sha256": "a" * 64}
    return before, after, expected


def test_exact_overlay_preserves_private_and_sticky_directories():
    before, after, expected = fixture_delta()
    checks = validate_delta(before, after, expected)
    assert checks["changed_files"] == sorted(PATHS)
    assert checks["new_directories"] == ["www/assets/lyoko-next"]


def test_already_identical_brand_is_preserved_instead_of_reported_as_changed():
    before, after, expected = fixture_delta()
    path = "www/assets/movistar-logo.svg"
    row = {"type": "file", "mode": 0o644, "uid": 0, "gid": 0, "bytes": 3, "sha256": "a" * 64}
    before[path] = row.copy(); after[path] = row.copy()
    expected[path] = {"path": path, "bytes": 3, "sha256": "a" * 64, "mode": "0644"}
    checks = validate_delta(before, after, expected)
    assert path in checks["preserved_overlay_files"]
    assert path not in checks["changed_files"]
    expected[path]["sha256"] = "c" * 64
    after[path]["sha256"] = "c" * 64
    with pytest.raises(ValueError, match="brand asset"):
        validate_delta(before, after, expected)


@pytest.mark.parametrize("path,key,value", [
    ("etc/private", "mode", 0o755),
    ("tmp", "mode", 0o755),
    ("www/dashboard.cgi", "uid", 1000),
    ("www/dashboard.cgi", "mode", 0o777),
    ("www/dashboard.cgi", "sha256", "c" * 64),
    ("bin/sh", "target", "different-shell"),
    (PATHS[2], "mode", 0o777),
    (PATHS[2], "sha256", "c" * 64),
])
def test_rejects_metadata_and_content_regressions(path, key, value):
    before, after, expected = fixture_delta()
    after[path][key] = value
    with pytest.raises(ValueError):
        validate_delta(before, after, expected)


def test_rejects_unexpected_added_or_removed_entries():
    before, after, expected = fixture_delta()
    after["unexpected"] = after[PATHS[0]]
    with pytest.raises(ValueError):
        validate_delta(before, after, expected)
    after.pop("unexpected")
    after.pop("bin/sh")
    with pytest.raises(ValueError):
        validate_delta(before, after, expected)


def manifest_fixture(tmp_path):
    rows = []
    for path in PATHS:
        item = tmp_path / path
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_bytes(b"abc")
        rows.append({"path": path, "bytes": 3, "sha256": hashlib.sha256(b"abc").hexdigest(), "mode": "0644"})
    return {"files": rows}


def test_checks_actual_overlay_bytes_and_rejects_unmanifested_files(tmp_path):
    manifest = manifest_fixture(tmp_path)
    assert set(validate_overlay(tmp_path, manifest)) == set(PATHS)
    (tmp_path / PATHS[2]).write_bytes(b"bad")
    with pytest.raises(ValueError, match="hash/size"):
        validate_overlay(tmp_path, manifest)
    (tmp_path / PATHS[2]).write_bytes(b"abc")
    (tmp_path / "unexpected").write_bytes(b"abc")
    with pytest.raises(ValueError, match="unmanifested"):
        validate_overlay(tmp_path, manifest)


@pytest.mark.parametrize("path", ["../escape", "/absolute", "www/../escape", "www\\escape", "etc/secret"])
def test_rejects_paths_outside_the_frontend_allowlist(tmp_path, path):
    manifest = manifest_fixture(tmp_path)
    manifest["files"][0]["path"] = path
    with pytest.raises(ValueError):
        validate_overlay(tmp_path, manifest)
