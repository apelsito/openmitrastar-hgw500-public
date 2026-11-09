from pathlib import Path

import pytest

import lyoko_pkg_remote as remote


ROOT = Path(__file__).resolve().parents[1]
FEED = ROOT / "outputs/packages/lyoko-v1.1"


def test_remote_plan_pins_feed_and_never_persists() -> None:
    plan = remote.plan("install", "lyoko-netdiag", FEED)
    assert plan["architecture"] == "arc700_uclibc_lyoko_v1"
    assert plan["host_verification"] == "ed25519+pinned-key+sha256+abi"
    assert plan["remote_stage"].startswith("/run/")
    assert plan["install_root"].startswith("/run/")
    assert plan["persistent_write"] is False
    assert plan["flash"] is False


def test_remote_plan_rejects_unknown_package() -> None:
    with pytest.raises(ValueError, match="package not found"):
        remote.plan("install", "not-in-feed", FEED)


def test_remote_tool_has_explicit_mutation_acknowledgements() -> None:
    text = (ROOT / "tools/lyoko_pkg_remote.py").read_text(encoding="utf-8")
    assert "OPENMITRASTAR_LYOKO_PKG_VOLATILE_INSTALL" in text
    assert "OPENMITRASTAR_LYOKO_PKG_VOLATILE_REMOVE" in text
    for forbidden in ("/persist", "mtd_debug", "flash_erase", "fw_setenv"):
        assert forbidden not in text
