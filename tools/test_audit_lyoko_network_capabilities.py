from __future__ import annotations

import audit_lyoko_network_capabilities as audit


def test_config_value_distinguishes_enabled_disabled_and_missing() -> None:
    text = "CONFIG_VLAN_8021Q=y\n# CONFIG_IP_MULTICAST is not set\n"
    assert audit.config_value(text, "CONFIG_VLAN_8021Q") == "y"
    assert audit.config_value(text, "CONFIG_IP_MULTICAST") == "n"
    assert audit.config_value(text, "CONFIG_BRIDGE_IGMP_SNOOPING") == "unknown"


def test_parse_kv_ignores_unstructured_and_lowercase_lines() -> None:
    parsed = audit.parse_kv("KERNEL=5.10\nnoise\nBRIDGE_MEMBERS=eth0,wlan0\nsecret=value\n")
    assert parsed == {"KERNEL": "5.10", "BRIDGE_MEMBERS": "eth0,wlan0"}


def test_nonnegative_int_fails_closed() -> None:
    assert audit.nonnegative_int("12") == 12
    assert audit.nonnegative_int("") == 0
    assert audit.nonnegative_int("IGMP_V6_GROUPS=12") == 0
