from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "versions/lyoko-foundation-6.0.2-f265-full"
OVERLAY = SOURCE / "overlay"
PRIVATE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware"
DEVICE = "hgw500bna-qcv2-a2-primary"
F264 = PRIVATE / "f264-device-bound"
F265 = PRIVATE / "f265-device-bound"


def named(version: str, suffix: str) -> str:
    return f"openmitrastar-linux510-{version}-{DEVICE}-PRIVATE-NO-FLASH{suffix}"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_radio_contract_is_truthful_and_fail_closed() -> None:
    radioctl = (OVERLAY / "usr/sbin/om-radioctl").read_text(encoding="utf-8")
    transaction = (OVERLAY / "usr/sbin/om-config-transaction").read_text(encoding="utf-8")
    qtnctl = (OVERLAY / "usr/sbin/om-qtnctl").read_text(encoding="utf-8")
    api = (OVERLAY / "usr/libexec/openmitrastar/om-api-v1").read_text(encoding="utf-8")

    assert 'r5_bandwidth=$($qtnctl get bandwidth' in radioctl
    assert '"dfs_backend_ready":%s' in radioctl
    assert '"weather_radar":[120,124,128]' in radioctl
    assert "dfs_stage_ready()" in transaction
    assert "OPENMITRASTAR_QTN_DFS_CONTROL=1" in transaction
    assert "dfs_backend_ready()" in qtnctl
    assert "dfs-radar-backend-unavailable" in qtnctl
    assert "HTTP_X_OM_REGULATORY_ACK" in api
    assert "OPENMITRASTAR_ES_DFS_V1" in api
    assert (OVERLAY / "etc/openmitrastar/features/qtn-dfs-control-v1").read_text(encoding="ascii").strip().endswith("=0")


def test_realtek_preserves_non_width_ht_capabilities() -> None:
    rtlctl = (OVERLAY / "usr/sbin/om-rtlctl").read_text(encoding="utf-8")
    assert "existing_htcap=" in rtlctl
    assert "base_htcap=" in rtlctl
    assert "sed 's/\\[HT40[+-]\\]//g'" in rtlctl
    assert 'htcap="[HT40+]$base_htcap"' in rtlctl
    assert 'htcap="[HT40-]$base_htcap"' in rtlctl


def test_config_store_is_not_presented_as_boot_active() -> None:
    store = (OVERLAY / "usr/sbin/om-config-store").read_text(encoding="utf-8")
    app = (OVERLAY / "www/app.js").read_text(encoding="utf-8")
    assert '"boot_consumer":false' in store
    assert "configStore?.boot_consumer === true" in app


def test_f265_manifest_and_kernel_contract() -> None:
    manifest = json.loads((F265 / "manifest.json").read_text(encoding="ascii"))
    assert manifest["schema"] == "openmitrastar.f265-control-truth/v1"
    assert manifest["candidate_eligible"] is True
    assert manifest["flash_supported"] is True
    assert manifest["dfs_observability"]["server_acknowledgement"] == "OPENMITRASTAR_ES_DFS_V1"
    assert manifest["dfs_observability"]["radar_backend_ready"] is False
    assert manifest["config_store"]["boot_consumer"] is False
    assert manifest["storage"]["store_erased_ff"] is True
    for suffix in (".kernel.lzma", ".config", ".dtb"):
        assert sha256(F265 / named("f265", suffix)) == sha256(F264 / named("f264", suffix))
