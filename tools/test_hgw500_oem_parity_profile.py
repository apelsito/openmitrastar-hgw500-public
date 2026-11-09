#!/usr/bin/env python3
"""Offline binding gate for the confirmed HGW-500BNA OEM-parity profile."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import re


ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "work/mission-state/w4-rootfs-product"
ROOTFS = PRODUCT / "rootfs"
ROOTFS_IMAGE = PRODUCT / "build/openmitrastar-product-rootfs-v1.squashfs"
ROOTFS_MANIFEST = PRODUCT / "build/manifest.json"
Q3 = ROOT / "work/mission-state/q3-assoc-trace-composite"
Q3_MANIFEST = Q3 / "build/manifest.json"
Q3_ROOTFS_MANIFEST = Q3 / "rootfs-build/manifest.json"
POLICY = ROOT / "work/mission-state/w4-videobridge-policy"
POLICY_MANIFEST = POLICY / "build/manifest.json"


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    product = json.loads(ROOTFS_MANIFEST.read_text(encoding="utf-8"))
    q3 = json.loads(Q3_MANIFEST.read_text(encoding="utf-8"))
    q3_rootfs = json.loads(Q3_ROOTFS_MANIFEST.read_text(encoding="utf-8"))
    policy_manifest = json.loads(POLICY_MANIFEST.read_text(encoding="utf-8"))

    rootfs_sha = digest(ROOTFS_IMAGE)
    assert product["rootfs"]["sha256"] == rootfs_sha
    runtime = product["runtime"]
    assert runtime["network_management"] == "oem-videobridge-static"
    assert runtime["management_ipv4"] == "192.168.1.90"
    assert runtime["management_netmask"] == "255.255.255.0"
    assert runtime["management_gateway"] == "192.168.1.1"
    assert runtime["management_dns"] == "192.168.1.1"
    assert runtime["recovery_ipv4"] == "192.168.1.200"
    assert runtime["local_dhcp_server"] is False
    assert runtime["local_dns_proxy"] is False
    assert runtime["local_nat"] is False
    assert runtime["local_router_firewall"] is False
    assert runtime["videobridge_policy_guard"] == "boot-read-only-fail-closed"
    assert runtime["api"]["port"] == 80
    assert runtime["api"]["management_url"] == "http://192.168.1.90/"
    assert runtime["api"]["diagnostic_port"] == 8080
    assert runtime["api"]["diagnostic_default_enabled"] is False

    defaults = (ROOTFS / "usr/share/openmitrastar/config-schema/v1/defaults.conf").read_text(encoding="ascii")
    for line in (
        "API_ENABLE=0",
        "API_PORT=8080",
        "MANAGEMENT_STATICIP=1",
        "MANAGEMENT_IPV4=192.168.1.90",
        "MANAGEMENT_NETMASK=255.255.255.0",
        "MANAGEMENT_GATEWAY=192.168.1.1",
        "MANAGEMENT_DNS=192.168.1.1",
        "MANAGEMENT_RECOVERY_IPV4=192.168.1.200",
    ):
        assert line in defaults
    assert "port=80" in (ROOTFS / "etc/minihttpd-oem.conf").read_text(encoding="ascii")
    assert "OMAPI_DIAGNOSTIC" in (ROOTFS / "etc/init.d/S45-api").read_text(encoding="ascii")
    parity = (ROOTFS / "etc/openmitrastar/oem-parity.conf").read_text(encoding="ascii")
    assert "OPENMITRASTAR_LOCAL_DNS_PROXY=0" in parity
    assert (ROOTFS / "usr/sbin/om-videobridge-policy").is_file()
    assert (ROOTFS / "etc/init.d/S33-videobridge-policy").is_file()

    for daemon in ("dnsmasq", "udhcpd", "dhcpd", "named", "iptables", "nft"):
        assert not any((ROOTFS / directory / daemon).exists() for directory in ("bin", "sbin", "usr/bin", "usr/sbin"))
    network_sources = "\n".join(
        path.read_text(encoding="utf-8", errors="replace")
        for base in (ROOTFS / "etc/init.d", ROOTFS / "usr/sbin")
        for path in base.glob("*")
        if path.is_file()
    )
    assert not re.search(r"(?i)(MASQUERADE|\bSNAT\b|\bDNAT\b|iptables|\bnft\b)", network_sources)

    q3_image_sha = q3["artifacts"]["webformat"]["sha256"]
    assert q3_image_sha == q3["artifacts"]["tftp_copy"]["sha256"]
    assert q3["candidate_eligible"] is False
    assert q3["flash_supported"] is False
    for capability in (
        "backup_restore", "http_80", "https_443_optional_external_pem",
        "getinfo_16667", "origin_mtd5_read_only_import",
    ):
        assert q3["capabilities"][capability] is True

    policy_q3 = policy_manifest["q3_composition"]
    assert policy_manifest["candidate_eligible"] is False
    assert policy_manifest["hardware_actions"] is False
    assert policy_manifest["network_actions"] is False
    assert policy_manifest["flash_actions"] is False
    assert policy_manifest["persistent_writes"] is False
    assert policy_q3["source_sha256"] == q3_rootfs["rootfs"]["sha256"]
    assert policy_q3["two_builds_identical"] is True
    assert policy_q3["source_unchanged"] is True
    for key in (
        "local_dhcp_server", "local_dns_proxy", "nat", "router_firewall",
        "ipv4_forwarding", "udp67_listener", "udp53_listener",
    ):
        assert policy_manifest["enforces"][key] is False

    print(
        "W4_OEM_PARITY_PROFILE_PASS "
        f"rootfs_sha256={rootfs_sha} q3_candidate_sha256={q3_image_sha} "
        f"q3_policy_rootfs_sha256={policy_q3['rootfs_sha256']} "
        "management=192.168.1.90/24 recovery=192.168.1.200 "
        "upstream=192.168.1.1 web=80 diagnostic=8080-disabled "
        "dhcp_server=0 dns_proxy=0 nat=0 router_firewall=0 ip_forward=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
