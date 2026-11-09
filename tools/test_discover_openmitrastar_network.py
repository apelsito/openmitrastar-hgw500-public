#!/usr/bin/env python3

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "tools/discover_openmitrastar_network.ps1"


class DiscoverOpenMitraStarNetworkTests(unittest.TestCase):
    def test_discovery_is_read_only_and_checks_expected_router(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn("openmitrastar.network-discovery/v1", text)
        self.assertIn('[string]$RouterHost = "192.168.1.90"', text)
        self.assertIn("Get-NetNeighbor", text)
        self.assertIn("Test-TcpPortFast", text)
        self.assertIn("EXPECTED_ROUTER_NOT_ON_LAN", text)
        self.assertIn("KnownNonRouterHosts", text)
        self.assertIn("UNKNOWN_SSH_HOSTS_PRESENT_NO_EXPECTED_ROUTER", text)
        for forbidden in ("Remove-Item", "Set-Net", "New-Net", "Restart-NetAdapter"):
            self.assertNotIn(forbidden, text)

    def test_discovery_includes_bootbase_and_known_router_addresses(self) -> None:
        text = SCRIPT.read_text(encoding="utf-8")
        self.assertIn('"$SubnetPrefix.90"', text)
        self.assertIn('"$SubnetPrefix.200"', text)
        self.assertIn('"$SubnetPrefix.201"', text)
        self.assertIn('"$SubnetPrefix.202"', text)
        self.assertIn("EXPECTED_ROUTER_SSH_UP", text)
        self.assertIn("EXPECTED_ROUTER_LAYER2_ONLY", text)


if __name__ == "__main__":
    unittest.main()
