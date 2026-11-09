#!/usr/bin/env python3
"""Read-only preflight for Lyoko multicast/IGMP and VLAN traffic gates."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import socket
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def tcp_open(host: str, port: int, timeout: float = 2.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def latest_network_audit() -> Path:
    candidates = list((ROOT / "outputs/certification").glob("network-capabilities-f*/audit.json"))
    if not candidates:
        raise SystemExit("no network capability audit found")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def local_network_inventory() -> dict[str, object]:
    script = r'''
$adapters = Get-NetAdapter | Where-Object Status -eq 'Up' | ForEach-Object {
  $name = $_.Name
  $addresses = @(Get-NetIPAddress -InterfaceIndex $_.ifIndex -AddressFamily IPv4 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty IPAddress)
  $vlan = @(Get-NetAdapterAdvancedProperty -Name $name -ErrorAction SilentlyContinue | Where-Object { $_.DisplayName -match 'VLAN|802.1Q|Priority' } | Select-Object DisplayName,DisplayValue,RegistryKeyword)
  [pscustomobject]@{Name=$name;Description=$_.InterfaceDescription;Status=$_.Status;LinkSpeed=$_.LinkSpeed;IPv4=$addresses;VlanProperties=$vlan}
}
[pscustomobject]@{Adapters=@($adapters)} | ConvertTo-Json -Depth 6 -Compress
'''
    proc = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command", script],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=30,
        check=False,
    )
    if proc.returncode:
        return {"status": "UNAVAILABLE", "adapters": [], "error": proc.stderr.strip()[:512]}
    try:
        payload = json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"status": "UNAVAILABLE", "adapters": [], "error": "invalid-powershell-json"}
    adapters = payload.get("Adapters", [])
    if isinstance(adapters, dict):
        adapters = [adapters]
    return {"status": "PASS", "adapters": adapters}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--router-host", default="192.168.1.90")
    parser.add_argument("--oracle-host", default="192.168.1.63")
    parser.add_argument("--network-audit", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    audit_path = (args.network_audit or latest_network_audit()).resolve()
    audit = json.loads(audit_path.read_text(encoding="ascii"))
    inventory = local_network_inventory()
    adapters = inventory.get("adapters", [])
    lan_adapters = [
        item for item in adapters
        if any(str(address).startswith("192.168.1.") for address in item.get("IPv4", []))
    ]
    vlan_adapters = [item for item in adapters if item.get("VlanProperties")]

    multicast_blockers: list[str] = []
    options = audit.get("kernel_options", {})
    knobs = audit.get("multicast", {}).get("bridge_knobs", {})
    if options.get("CONFIG_IP_MULTICAST") != "y":
        multicast_blockers.append("kernel-ip-multicast")
    if options.get("CONFIG_BRIDGE_IGMP_SNOOPING") != "y":
        multicast_blockers.append("kernel-bridge-igmp")
    if knobs.get("snooping") == "unavailable":
        multicast_blockers.append("bridge-snooping-knob")
    if not tcp_open(args.router_host, 22):
        multicast_blockers.append("router-ssh")
    if not tcp_open(args.oracle_host, 22):
        multicast_blockers.append("oracle-ssh")
    if not lan_adapters:
        multicast_blockers.append("controller-lan-interface")

    vlan_blockers: list[str] = []
    if options.get("CONFIG_VLAN_8021Q") != "y":
        vlan_blockers.append("kernel-8021q")
    if not tcp_open(args.router_host, 22):
        vlan_blockers.append("router-ssh")
    if not vlan_adapters:
        vlan_blockers.append("windows-vlan-capable-interface-unproven")
    if len(lan_adapters) < 1:
        vlan_blockers.append("controller-lan-interface")
    if len(lan_adapters) < 2:
        vlan_blockers.append("no-independent-management-path")

    result = {
        "schema": "openmitrastar.network-traffic-preflight/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "read_only": True,
        "network_audit": str(audit_path),
        "router": {"host": args.router_host, "ssh": tcp_open(args.router_host, 22)},
        "oracle": {"host": args.oracle_host, "ssh": tcp_open(args.oracle_host, 22)},
        "controller": {
            "inventory_status": inventory.get("status"),
            "lan_interfaces": [item.get("Name") for item in lan_adapters],
            "vlan_capable_interfaces": [item.get("Name") for item in vlan_adapters],
            "independent_management_paths": len(lan_adapters),
        },
        "multicast_igmp": {
            "status": "READY" if not multicast_blockers else "BLOCKED_PREFLIGHT",
            "blockers": multicast_blockers,
            "next_test": "wired sender <-> Wi-Fi receiver, then reverse direction, with temporary snooping and automatic rollback",
        },
        "vlan": {
            "status": "READY" if not vlan_blockers else "BLOCKED_TEST_TOPOLOGY",
            "blockers": vlan_blockers,
            "next_test": "use a dedicated second LAN interface for isolated VLAN 4090; never retag the active management interface",
        },
        "hardware_actions": {"router": False, "oracle": False, "network_mutation": False, "flash": False},
    }
    out = args.output_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    (out / "preflight.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
