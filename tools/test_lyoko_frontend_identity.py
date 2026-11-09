from copy import deepcopy
from pathlib import Path

import pytest

from lyoko_frontend_identity import API_PATH, BASE_API_HASHES, check_transform_spec, digest, patch_api, transform_bytes, transform_spec

ROOT = Path(__file__).resolve().parents[1]
F317_API = ROOT / "versions/lyoko-foundation-7.1.0-f317-radiod-observer/overlay" / API_PATH


def test_only_frontend_branch_changes_and_authentication_precedes_bundle():
    before = F317_API.read_bytes()
    assert digest(before) == BASE_API_HASHES["f317"]
    after = patch_api(before)
    start = before.index(b"\nfrontend)\n")
    tail = before[before.index(b"\n\t;;", start):]
    assert after[:start] == before[:start]
    assert after.endswith(tail)
    branch = after[start:len(after)-len(tail)]
    assert branch.index(b"require_read") < branch.index(b"cat /etc/lyoko/web-next.json")
    assert b'"asset_layout":"split-v1"' in branch


def test_unknown_base_and_double_application_are_refused():
    before = F317_API.read_bytes()
    with pytest.raises(ValueError, match="not pinned"):
        patch_api(before + b"\n")
    with pytest.raises(ValueError, match="not pinned"):
        patch_api(patch_api(before))


def test_transform_contract_checks_target_and_exact_result():
    spec = transform_spec()
    before = F317_API.read_bytes()
    after, audit = transform_bytes(before, spec)
    assert digest(after) == audit["after_sha256"]
    bad = deepcopy(spec); bad["path"] = "etc/shadow"
    with pytest.raises(ValueError, match="unsupported"):
        check_transform_spec(bad)
    bad = deepcopy(spec); bad["inputs"][1]["after_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="output differs"):
        transform_bytes(before, bad)


def test_emulator_frontend_uses_the_packaged_identity(tmp_path):
    import json
    from package_lyoko_web_next import package
    from run_lyoko_web_next_emulator import configure_frontend_identity, load_server_module
    destination, manifest, _ = package(tmp_path / "package")
    module = load_server_module()
    configure_frontend_identity(module, destination)
    response = module.frontend_fixture()
    bundle = json.loads((destination / "overlay/etc/lyoko/web-next.json").read_text(encoding="ascii"))
    assert response["runtime"] == "emulator"
    assert response["build_id"] == manifest["build_id"] == bundle["build_id"]
    assert response["bundle"] == bundle
    assert response["assets"]["dashboard_html_sha256"] == next(row["sha256"] for row in bundle["assets"] if row["url"] == "/dashboard.cgi")
