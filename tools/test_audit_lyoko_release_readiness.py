import audit_lyoko_release_readiness as audit
from pathlib import Path


def test_release_requires_every_requirement_pass() -> None:
    requirements = [
        audit.requirement("a", "A", "PASS", [], ""),
        audit.requirement("b", "B", "NOT_RUN", [], ""),
        audit.requirement("c", "C", "BLOCKED", [], ""),
        audit.requirement("d", "D", "PARTIAL", [], ""),
    ]
    result = audit.summarize(requirements)
    assert result["counts"] == {"PASS": 1, "PARTIAL": 1, "BLOCKED": 1, "NOT_RUN": 1}
    assert result["release_ready"] is False


def test_all_pass_is_release_ready() -> None:
    result = audit.summarize([audit.requirement("a", "A", "PASS", [], "")])
    assert result["release_ready"] is True


def test_audit_tracks_current_integrated_candidates() -> None:
    source = Path(audit.__file__).read_text(encoding="utf-8")
    for marker in ("F194", "F222", "f223-device-bound", "F239", "F241", "F245", "F278", "F279", "F280", "F285", "F286", "f287-device-bound", "f288-device-bound", "f290-device-bound", "F291", "F292", "f293-sequential", "F294", "F295", "F296", "F297", "F300", "F301", "f302-radar-native", "F303", "F306", "F307", "F308", "CURRENT_STATE.json", "mtd3-current-evidence"):
        assert marker in source
    assert '"installed_candidate": {"name": "F301"' in source
    assert '"next_candidate": {"name": "F306"' in source
    assert 'sanitized-association-result.json' in source
    assert 'result-reconciled-20260903T204757Z.json' in source
    assert '"offline_network_successor": {"name": "F297"' in source
    assert '"legacy_multicast_harness": {"name": "F278"' in source
    assert '"offline_store_writer_module": {"name": "F279"' in source
    assert '"offline_store_driver_image": {"name": "F280"' in source
    assert '"latest_product_candidate": {"name": "F306"' in source
    assert '"latest_frontend_source": {"name": "F301"' in source
    assert '"latest_integrated_hold": {"name": "F298"' in source
    assert '"previous_frontend_source": {"name": "F294"' in source
    assert '"latest_store_protection_observer": {"name": "F295"' in source
    assert '"offline_store_protection_hold": {"name": "F296"' in source
    assert '"latest_package_runtime_evidence": {"name": "F292"' in source
    assert "f292-packages-current-20260904T020411Z" in source
    assert "f292-package-lifecycle-20260904T022342Z" in source
    assert '"latest_private_candidate": {"name": "F301"' in source
    assert '"latest_qtn_control_candidate": {"name": "F277"' in source
    assert '"latest_dfs_observability_candidate": {"name": "F239"' in source
    assert '"latest_dfs_replay": {"name": "F307"' in source
    assert '"latest_dfs_observer": {"name": "F308"' in source
    assert 'outputs/kernel-port/f308-radar-observer-v2-20260904/manifest.json' in source
    assert 'docs/OPENMITRASTAR_F308_RADAR_OBSERVER.md' in source
    assert 'outputs/kernel-port/f307-radar-replay-20260904/manifest.json' in source
    assert 'docs/OPENMITRASTAR_F307_RADAR_REPLAY.md' in source
    assert '"latest_network_observability_candidate": {"name": "F241"' in source
    assert 'f276-dual-radio-visibility-20260903/summary.json' in source
    assert 'docs/museum/manifest.json' in source
    assert 'network-capabilities-f*/audit.json' in source
    assert 'network-traffic-preflight-*/preflight.json' in source
    assert '"latest_datapath_candidate": {"name": "F300"' in source
    assert '"latest_soak_plan": {"name": "F306-24h-sequential"' in source
    assert "f306-soak-24h-20260904T162651Z" in source
    assert '"proven_datapath_baseline": {"name": "F300"' in source
    assert '"rejected_datapath_candidates": [' in source


def test_museum_manifest_is_hash_verified() -> None:
    manifest = Path(audit.ROOT / "docs/museum/manifest.json")
    assert audit.museum_manifest_valid(manifest) is True
