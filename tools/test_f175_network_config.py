from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs/kernel-port/f175-network-capabilities-config-20260901"


def test_fragment_is_minimal() -> None:
    fragment = (ROOT / "configs/lyoko/f175-bridge-multicast.config").read_text(encoding="ascii").splitlines()
    enabled = {line for line in fragment if line.endswith("=y")}
    assert enabled == {"CONFIG_IP_MULTICAST=y", "CONFIG_BRIDGE_IGMP_SNOOPING=y"}
    assert "# CONFIG_IP_MROUTE is not set" in fragment


def test_resolved_config_contract() -> None:
    manifest_path = OUT / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    config = (OUT / manifest["resolved_config"]).read_text(encoding="utf-8")
    assert manifest["firmware_candidate"] is False
    assert manifest["hardware_actions"] == {"router": False, "uart": False, "mtd": False}
    assert "CONFIG_BRIDGE=y\n" in config
    assert "CONFIG_VLAN_8021Q=y\n" in config
    assert "CONFIG_IP_MULTICAST=y\n" in config
    assert "CONFIG_BRIDGE_IGMP_SNOOPING=y\n" in config
    assert "# CONFIG_IP_MROUTE is not set\n" in config
