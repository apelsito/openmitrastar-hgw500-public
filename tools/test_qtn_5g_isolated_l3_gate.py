#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
EVAL = ROOT / "tools/evaluate_qtn_5g_isolated_l3.py"
WINDOWS = ROOT / "tools/run_qtn_5g_windows_oracle.ps1"
QTN = ROOT / "tools/run_qtn_w3_tx7_client_traffic.py"

spec = importlib.util.spec_from_file_location("isolated_eval", EVAL)
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def good_windows() -> dict:
    return {
        "execution_error": None,
        "test": {
            "mode": "isolated-l3-static",
            "connected": True,
            "static_ipv4_applied": True,
            "ipv4": {"ipv4": "192.168.77.2"},
            "router_ping": {"pass": True},
            "soak": {"requested_seconds": 120, "samples": 24, "connected_samples": 24, "disconnects": 0},
        },
        "restore": {"connected": True, "ipv4": {"ipv4": "192.168.1.63", "dhcp_enabled": True}},
    }


def good_router() -> dict:
    return {
        "isolated_l3": True, "br_5g_expected": 0, "complete": True,
        "management_lost": False, "health_failure": False,
        "association_observed": True, "duration_observed_seconds": 120,
        "wifi_rx_delta": 10, "wifi_tx_delta": 10, "irq8_delta": 100,
        "irq20_delta": 20,
        "last_sample": {"br_eth": 1, "br_2g": 1, "br_5g": 0, "radio2g": 1},
    }


class Qtn5gIsolatedL3GateTests(unittest.TestCase):
    def test_pass(self) -> None:
        result = module.evaluate(good_windows(), good_router(), 120)
        self.assertEqual("PASS", result["status"])
        self.assertTrue(result["network"]["direct_bidirectional_icmp"])

    def test_bridge_or_management_regression_fails(self) -> None:
        router = good_router(); router["last_sample"]["br_5g"] = 1
        self.assertIn("router_wifi0_not_bridged", module.evaluate(good_windows(), router, 120)["failures"])
        router = good_router(); router["management_lost"] = True
        self.assertIn("router_management_continuity", module.evaluate(good_windows(), router, 120)["failures"])

    def test_static_and_restore_are_mandatory(self) -> None:
        windows = good_windows(); windows["test"]["static_ipv4_applied"] = False
        self.assertIn("windows_static_ipv4", module.evaluate(windows, good_router(), 120)["failures"])
        windows = good_windows(); windows["restore"]["ipv4"]["dhcp_enabled"] = False
        self.assertIn("windows_dhcp_restored", module.evaluate(windows, good_router(), 120)["failures"])

    def test_sources_enforce_isolation_and_finally_restore(self) -> None:
        windows = WINDOWS.read_text(encoding="utf-8")
        qtn = QTN.read_text(encoding="utf-8")
        for marker in (
            "Set-NetIPInterface -InterfaceAlias $WifiInterface -AddressFamily IPv4 -Dhcp Disabled",
            "-IPAddress $IsolatedClientIp -PrefixLength 24",
            "Set-NetIPInterface -InterfaceAlias $WifiInterface -AddressFamily IPv4 -Dhcp Enabled",
            "Set-DnsClientServerAddress -InterfaceAlias $WifiInterface -ResetServerAddresses",
        ):
            self.assertIn(marker, windows)
        self.assertIn("test ! -e /sys/class/net/br0/brif/wifi0", qtn)
        self.assertIn("192.168.77.1", qtn)


if __name__ == "__main__":
    unittest.main(verbosity=2)
