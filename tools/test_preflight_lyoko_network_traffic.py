from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/preflight_lyoko_network_traffic.py"


def test_preflight_is_read_only_and_separates_kernel_from_topology() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "CONFIG_IP_MULTICAST" in source
    assert "CONFIG_BRIDGE_IGMP_SNOOPING" in source
    assert "CONFIG_VLAN_8021Q" in source
    assert "BLOCKED_PREFLIGHT" in source
    assert "BLOCKED_TEST_TOPOLOGY" in source
    assert "no-independent-management-path" in source
    assert '"network_mutation": False' in source
    for forbidden in ("Set-NetAdapterAdvancedProperty", "New-NetIPAddress", "ip link add", "multicast_snooping\" >", "flash_erase", "mtd_debug"):
        assert forbidden not in source
