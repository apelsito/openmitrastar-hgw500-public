#!/usr/bin/env python3
"""Build the evidence-backed Track A parity delta for HGW-500BNA-QCv2.

This is deliberately an offline auditor.  It reads the verified dump archive,
the extracted OEM rootfs and the current OpenMitraStar product rootfs.  It does
not contact hardware, expose secret-bearing configuration or write flash.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import pathlib
import re
import sys
import zipfile
from dataclasses import asdict, dataclass


ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_OEM = ROOT / "work/hgw500-rootfs-live/squashfs-root"
DEFAULT_OM = ROOT / "work/mission-state/w4-rootfs-product/rootfs"
DEFAULT_DUMP = ROOT / "hgw500bna-qcv2-firmware-dump-verified.zip"
DEFAULT_OUTPUT = ROOT / "outputs/kernel-port/movistar-parity"
MISSION_STATE = ROOT / "work/mission-state/MISSION_STATE.md"
TRACK_A_DOC = ROOT / "docs/HGW500BNA_QCV2_TRACK_A_PARITY_DELTA.md"


@dataclass(frozen=True)
class Row:
    id: str
    priority: str
    blocks_minimum_internet: bool
    capability: str
    oem_observation: str
    oem_dependency: str
    openmitrastar_implementation: str
    current_state: str
    gap: str
    acceptance_test: str


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_zip_member(archive: zipfile.ZipFile, member: str) -> str:
    digest = hashlib.sha256()
    with archive.open(member) as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_text(path: pathlib.Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def rel(path: pathlib.Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def scan_text_files(paths: list[pathlib.Path], pattern: re.Pattern[str]) -> list[str]:
    hits: list[str] = []
    for base in paths:
        if not base.exists():
            continue
        if base.is_file():
            files = [base]
        else:
            files = []
            for path in base.rglob("*"):
                try:
                    if path.is_file():
                        files.append(path)
                except OSError:
                    # The extracted OEM rootfs preserves device-side symlinks
                    # which are intentionally dangling on the Windows host.
                    continue
            files.sort()
        for path in files:
            try:
                text = read_text(path)
            except OSError:
                continue
            if pattern.search(text):
                hits.append(rel(path))
    return hits


def require_files(root: pathlib.Path, names: list[str]) -> dict[str, bool]:
    return {name: (root / name).is_file() for name in names}


def build_facts(oem: pathlib.Path, om: pathlib.Path, dump_zip: pathlib.Path) -> dict:
    required_oem = [
        "etc/default_config.txt",
        "etc/config.default.xml",
        "etc/init.d/S40network",
        "etc/qwe.conf",
        "scripts/qbr",
        "scripts/start-prod",
        "scripts/start-helpers.sh",
        "scripts/topaz-qvlan",
        "var/www/config.json",
        "var/www/top_menu.html",
    ]
    required_om = [
        "usr/sbin/om-network-base",
        "usr/sbin/om-radio-start",
        "usr/sbin/om-firmware-stage",
        "usr/libexec/openmitrastar/om-oem-cgi",
        "etc/init.d/S44-oem-web",
        "etc/minihttpd-oem.conf",
        "etc/openmitrastar/oem-parity.conf",
        "usr/share/openmitrastar/config-schema/v1/defaults.conf",
    ]

    oem_files = require_files(oem, required_oem)
    om_files = require_files(om, required_om)
    missing = [rel(oem / p) for p, ok in oem_files.items() if not ok]
    missing += [rel(om / p) for p, ok in om_files.items() if not ok]
    if missing:
        raise RuntimeError("required source files missing: " + ", ".join(missing))

    defaults = read_text(oem / "etc/default_config.txt")
    config_xml = read_text(oem / "etc/config.default.xml")
    s40 = read_text(oem / "etc/init.d/S40network")
    qwe = read_text(oem / "etc/qwe.conf")
    qbr = read_text(oem / "scripts/qbr")
    start_prod = read_text(oem / "scripts/start-prod")
    helpers = read_text(oem / "scripts/start-helpers.sh")
    config_json = read_text(oem / "var/www/config.json")
    top_menu = read_text(oem / "var/www/top_menu.html")

    om_network = read_text(om / "usr/sbin/om-network-base")
    om_radio = read_text(om / "usr/sbin/om-radio-start")
    om_cgi = read_text(om / "usr/libexec/openmitrastar/om-oem-cgi")
    om_fw = read_text(om / "usr/sbin/om-firmware-stage")
    om_httpd = read_text(om / "etc/init.d/S44-oem-web")
    om_httpd_conf = read_text(om / "etc/minihttpd-oem.conf")
    om_defaults = read_text(om / "usr/share/openmitrastar/config-schema/v1/defaults.conf")
    om_parity = read_text(om / "etc/openmitrastar/oem-parity.conf")
    om_diag = read_text(om / "etc/init.d/S45-api")
    mission = read_text(MISSION_STATE) if MISSION_STATE.is_file() else ""

    wan_tokens = ("WANDevice", "WANConnectionDevice", "WANIPConnection", "WANPPPConnection")
    wan_counts = {token: config_xml.count(token) for token in wan_tokens}
    voice_count = config_xml.count("VoiceService")
    nat_hits = scan_text_files(
        [oem / "etc/init.d", oem / "scripts"],
        re.compile(r"(?i)(MASQUERADE|\bSNAT\b|\bDNAT\b|iptables.{0,80}(?:-t\s+nat|--table\s+nat))"),
    )
    om_nat_hits = scan_text_files(
        [om / "etc", om / "usr"],
        re.compile(r"(?i)(MASQUERADE|\bSNAT\b|\bDNAT\b|iptables|nft(?:ables)?|ip_forward)"),
    )

    executable_dirs = ("bin", "sbin", "usr/bin", "usr/sbin", "usr/local/bin", "usr/local/sbin")
    daemon_presence = {
        daemon: [rel(oem / directory / daemon) for directory in executable_dirs if (oem / directory / daemon).is_file()]
        for daemon in ("udhcpd", "dnsmasq", "named", "dhcpd")
    }

    oem_routes = {
        name
        for name in (
            "wifi5g_sta.cgi",
            "wifi5g.cgi",
            "wifi24g.cgi",
            "password.cgi",
            "sysinfo.cgi",
            "lan.cgi",
            "firmware.cgi",
            "advanced.cgi",
            "wifi5g_adv.cgi",
            "restoredef.cgi",
            "wizard_help.cgi",
        )
        if name in top_menu and (oem / "var/www" / name).is_file()
    }
    om_routes = {
        path.name for path in (om / "www").glob("*.cgi") if path.is_file()
    }

    dump = {
        "path": rel(dump_zip),
        "sha256": sha256_file(dump_zip),
        "mtd6_member": "hgw500_mtdblock6.bin",
        "mtd6_expected_sha256": None,
        "mtd6_actual_sha256": None,
        "mtd6_verified": False,
    }
    with zipfile.ZipFile(dump_zip) as archive:
        manifest = json.loads(archive.read("dump_manifest.json"))
        mtd6 = next(item for item in manifest if item["idx"] == 6 and item["name"] == "rootfs_live")
        dump["mtd6_expected_sha256"] = mtd6["local_sha256"]
        dump["mtd6_actual_sha256"] = sha256_zip_member(archive, dump["mtd6_member"])
        dump["mtd6_verified"] = (
            dump["mtd6_actual_sha256"] == dump["mtd6_expected_sha256"]
            and bool(mtd6["verified_md5"])
            and bool(mtd6["verified_size"])
        )

    facts = {
        "dump": dump,
        "source_files": {
            "oem": {name: sha256_file(oem / name) for name in required_oem},
            "openmitrastar": {name: sha256_file(om / name) for name in required_om},
        },
        "oem": {
            "role_ap_default": all(token in defaults for token in ("mode=ap", "staticip=0", "region=es")),
            "ui_identifies_dual_adapter": "MLG_Wifi_Plus_Adapter_Duel" in top_menu,
            "bridge_policy": all(
                token in qbr
                for token in ("brctl addbr br0", "brctl setfd br0 0", "brctl setageing br0 7200")
            ),
            "bridge_adds_ethernet_and_wifi": "brctl addif br0 eth1_0" in qbr and "brctl addif br0 wifi0" in qbr,
            "management_fallbacks": "192.168.1.100" in helpers and "192.168.1.200" in helpers,
            "sta_dhcp_client": "dhclient -4 br0" in start_prod,
            "wan_object_counts": wan_counts,
            "voice_service_count": voice_count,
            "generic_ui_api_fake": '"Implementation":"api_fake"' in config_json,
            "generic_ui_manual_pppoe": '"ManualPPPoE": true' in config_json,
            "nat_rule_source_hits": nat_hits,
            "server_daemons": daemon_presence,
            "vlan_control_present": (oem / "scripts/topaz-qvlan").is_file() and "set vlan" in read_text(oem / "scripts/topaz-qvlan"),
            "vlan_default_empty": bool(re.search(r"(?m)^vlanid\.wlan1=\s*$", qwe)),
            "ipv6_disabled_on_emac": "disable_ipv6" in s40,
            "ui_routes": sorted(oem_routes),
        },
        "openmitrastar": {
            "static_management_base": all(
                token in om_network
                for token in ("MANAGEMENT_IPV4", "MANAGEMENT_NETMASK", "MANAGEMENT_GATEWAY", "route add default")
            ),
            "bridge_policy": all(
                token in om_radio
                for token in (
                    'brctl addbr "$br_if"',
                    'brctl addif "$br_if" "$eth_if"',
                    "printf 'bridge=%s\\n' \"$br_if\"",
                    '"/sys/class/net/$br_if/brif/$wifi_if"',
                    'route add default gw "$gateway" dev "$br_if"',
                    "720000",
                )
            ),
            "dhcp_client_present": bool(re.search(r"(?i)\b(?:udhcpc|dhclient)\b", om_network + "\n" + om_radio)),
            "nat_firewall_source_hits": om_nat_hits,
            "ipv6_policy_present": bool(re.search(r"(?i)(disable_ipv6|accept_ra|forwarding.*ipv6|ip6tables|nft)", om_network + "\n" + om_radio)),
            "ui_routes": sorted(om_routes),
            "cgi_dispatcher_routes": sorted(
                name
                for name in (
                    "index.cgi",
                    "logout.cgi",
                    "sysinfo.cgi",
                    "wifi24g.cgi",
                    "wifi5g.cgi",
                    "wifi5g_sta.cgi",
                    "lan.cgi",
                    "advanced.cgi",
                    "wifi5g_adv.cgi",
                    "wizard_help.cgi",
                    "wps24_info.cgi",
                    "wps5g_info.cgi",
                    "firmware.cgi",
                )
                if name in om_cgi
            ),
            "mini_httpd_cgi": all(token in om_httpd + "\n" + om_httpd_conf for token in ("mini_httpd", "cgipat")),
            "normal_management_identity": all(
                token in om_defaults + "\n" + om_parity
                for token in (
                    "MANAGEMENT_STATICIP=1",
                    "MANAGEMENT_IPV4=192.168.1.90",
                    "MANAGEMENT_NETMASK=255.255.255.0",
                    "MANAGEMENT_GATEWAY=192.168.1.1",
                    "MANAGEMENT_DNS=192.168.1.1",
                    "MANAGEMENT_RECOVERY_IPV4=192.168.1.200",
                    "OEM_DEFAULT_STATICIP=0",
                )
            ),
            "normal_web_port_80": "port=80" in om_httpd_conf,
            "diagnostic_port_8080_disabled": (
                "API_ENABLE=0" in om_defaults
                and "API_PORT=8080" in om_defaults
                and "OMAPI_DIAGNOSTIC" in om_diag
            ),
            "firmware_volatile_only": all(
                token in om_fw + "\n" + om_cgi
                for token in ("flash=false", "reboot=false", "volatile", "staged")
            ) and not re.search(r"(?i)(flash_erase|nandwrite|mtd_debug|/dev/mtd)", om_fw + "\n" + om_cgi),
            "defaults_bridge_2g": all(
                token in om_defaults for token in ("PRODUCT_MODE=ap", "RADIO2G_ENABLE=1", "RADIO2G_BRIDGE=1")
            ),
        },
        "runtime_ledger": {
            "bridge_internet_speedtest_recorded": "bridge Internet Speedtest passed" in mission,
            "secure_2g_enabled_recorded": "Product secure AP runner reached `state=ENABLED`" in mission,
            "cgi_hardware_verified": "W4_UI_RUNTIME_HARDWARE_VERIFIED=1" in mission,
        },
    }
    return facts


def build_rows(facts: dict) -> list[Row]:
    oem = facts["oem"]
    om = facts["openmitrastar"]
    runtime = facts["runtime_ledger"]
    no_wan = all(value == 0 for value in oem["wan_object_counts"].values())
    no_servers = all(not paths for paths in oem["server_daemons"].values())
    no_nat = not oem["nat_rule_source_hits"]
    bridge_ported = oem["bridge_policy"] and om["bridge_policy"]

    return [
        Row(
            "A01",
            "P0",
            True,
            "uplink-role",
            "AP/videobridge: upstream HGU remains the IP/WAN endpoint.",
            "etc/default_config.txt; var/www/top_menu.html; scripts/start-prod",
            "PRODUCT_MODE=ap; static management; 2.4 GHz bridge profile.",
            "OEM_ROLE_PROVEN" if oem["role_ap_default"] and oem["ui_identifies_dual_adapter"] else "SOURCE_MISMATCH",
            "Do not label Ethernet as PPPoE WAN; choose transparent uplink as the minimum-Internet product profile.",
            "Cold boot with HGU on Ethernet; client traffic crosses br0 without local address translation.",
        ),
        Row(
            "A02",
            "P0",
            False,
            "wan-pppoe-isp-auth",
            "No WANDevice/WANConnectionDevice/WANIPConnection/WANPPPConnection objects; generic PPPoE UI flag is api_fake.",
            "etc/config.default.xml; var/www/config.json",
            "No routed WAN implementation in the parity profile.",
            "N_A_OEM" if no_wan and oem["generic_ui_api_fake"] else "SOURCE_CONTRADICTION",
            "A routed WAN/PPPoE profile would be a new product feature, not a port of this OEM firmware.",
            "Negative audit remains zero; if a new router profile is requested, certify physical WAN port, ISP auth and reconnect separately.",
        ),
        Row(
            "A03",
            "P1",
            False,
            "vlan",
            "qvlan control exists, but wlan1 VLAN ID is empty in the shipped default.",
            "scripts/topaz-qvlan; scripts/ruby-qvlan; etc/qwe.conf",
            "No VLAN policy in the current product rootfs.",
            "OEM_DORMANT_5_10_MISSING" if oem["vlan_control_present"] and oem["vlan_default_empty"] else "SOURCE_MISMATCH",
            "Port only after a real capture/config shows tags are required; never inject remembered Movistar VLAN IDs.",
            "Explicit opt-in tag/untag test with packet capture, isolation and untagged regression.",
        ),
        Row(
            "A04",
            "P0",
            True,
            "bridge-l2",
            "br0 with forward-delay 0, ageing 7200 s and Ethernet/radio members.",
            "scripts/qbr; etc/init.d/S40network",
            "om-radio-start creates br0, preserves Ethernet MAC, adds eth0+wlan0 and moves management/default route to br0.",
            "PORTED_HW_PARTIAL" if bridge_ported and runtime["bridge_internet_speedtest_recorded"] else "PORTED_OFFLINE",
            "Re-certify the exact current image after cold boot; existing Internet evidence predates the latest CGI/rootfs candidate.",
            ">=10 min WPA2 client soak: upstream DHCP, DNS, HTTPS, MTU, reconnect, br0 counters and SSH remain live.",
        ),
        Row(
            "A05",
            "P0",
            True,
            "dhcp",
            "STA management can run dhclient on br0; downstream clients receive DHCP transparently from the HGU; no local server binary exists.",
            "scripts/start-prod; usr/sbin/dhclient; negative daemon audit",
            "Static management address only; no DHCP client/server in om-network-base or om-radio-start.",
            "TRANSPARENT_PATH_PARTIAL" if oem["sta_dhcp_client"] and no_servers else "SOURCE_MISMATCH",
            "Client DHCP must be captured on the exact candidate; management DHCP/fallback parity is not yet ported.",
            "DORA + renew/rebind from client; prove server identity is upstream and no UDP/67 listener exists locally.",
        ),
        Row(
            "A06",
            "P0",
            True,
            "dns",
            "No DNS daemon in the OEM image; client DNS is part of transparent L2 service.",
            "negative daemon audit; etc/config.default.xml; etc/resolv.conf",
            "No DNS proxy/server; router management resolver is not explicitly provisioned by the product scripts.",
            "TRANSPARENT_UNVERIFIED" if no_servers else "SOURCE_CONTRADICTION",
            "Internet Speedtest is indirect; capture an explicit client DNS answer and router-side resolver behavior.",
            "Client resolves A/AAAA through upstream DNS, then completes HTTPS; record effective resolver and failure behavior.",
        ),
        Row(
            "A07",
            "P1",
            False,
            "nat-routing",
            "iptables is packaged, but OEM init/scripts contain no MASQUERADE/SNAT/DNAT policy.",
            "usr/sbin/iptables; negative scan of etc/init.d and scripts",
            "No NAT/firewall implementation in the current product rootfs.",
            "N_A_OEM" if no_nat else "SOURCE_CONTRADICTION",
            "None for transparent parity. NAT is required only for a separately specified routed-router profile.",
            "Forwarded client retains its address across the bridge; local NAT table remains empty/absent.",
        ),
        Row(
            "A08",
            "P1",
            False,
            "firewall-management",
            "No demonstrated OEM WAN firewall; generic HomeStation assets use api_fake.",
            "var/www/config.json; negative init/scripts scan",
            "SSH and HTTP services exist, but no interface-scoped management filtering is implemented.",
            "HARDENING_GAP" if not om["nat_firewall_source_hits"] else "IMPLEMENTATION_PRESENT_REVIEW_REQUIRED",
            "Add a minimal local-input policy only after bridge stability; it must not filter forwarded DHCP/multicast.",
            "Management allowed only on intended LAN/bridge; forwarded DHCP, DNS, multicast and HTTPS remain unchanged.",
        ),
        Row(
            "A09",
            "P0",
            True,
            "ipv4-management",
            "Persistent IP with AP .100/STA .200 fallback; STA path can acquire DHCP on br0.",
            "scripts/start-helpers.sh; scripts/start-prod; scripts/qbr",
            "Fixed OEM-parity 192.168.1.90/24, gateway/DNS 192.168.1.1; 192.168.1.200 is recovery-only; address moves from eth0 to br0 with the AP.",
            "FIXED_POLICY_PORTED_OFFLINE" if om["static_management_base"] and om["bridge_policy"] and om["normal_management_identity"] else "MISSING",
            "Policy is closed offline; exact-image cold-boot, ARP conflict and recovery reachability remain unverified on hardware.",
            "Normal boot exposes only .90; .200 appears only in recovery; gateway/DNS and br0 survive radio start/stop and IP conflict checks.",
        ),
        Row(
            "A10",
            "P1",
            False,
            "ipv6",
            "OEM disables IPv6 on EMAC members; DHCPv6 config is dormant.",
            "etc/init.d/S40network; etc/dhcp/dhclient-dhcpv6.conf",
            "No explicit IPv6 management/bridge policy in om-network-base or om-radio-start.",
            "POLICY_MISSING" if oem["ipv6_disabled_on_emac"] and not om["ipv6_policy_present"] else "POLICY_PRESENT_REVIEW_REQUIRED",
            "Choose and encode parity: no local IPv6 management service while preserving transparent RA/ND forwarding if required.",
            "No rogue RA/DHCPv6; client RA/ND behavior and IPv6 forwarding across br0 are explicitly measured.",
        ),
        Row(
            "A11",
            "P1",
            False,
            "ui-cgi",
            "OEM menu exposes 2.4/5 GHz, LAN, status, password, firmware, reset, advanced and help CGI routes.",
            "var/www/top_menu.html; var/www/*.cgi; legacy ARC/uClibc web libraries",
            "Native ash dispatcher, address-bound sessions, CSRF, read-only compatibility pages and JSON status/config staging on normal port 80; diagnostic 8080 disabled by default.",
            "PORTED_OFFLINE_HW_PENDING" if om["mini_httpd_cgi"] and om["normal_web_port_80"] and om["diagnostic_port_8080_disabled"] and len(om["cgi_dispatcher_routes"]) >= 13 and not runtime["cgi_hardware_verified"] else "PORTED_HW",
            "language/password/reset aliases and actual hardware HTTP smoke are pending; UI mutation is intentionally staged-only.",
            "On exact RAM image: login, session expiry, CSRF rejection, status, staged config, restart and zero-secret response checks.",
        ),
        Row(
            "A12",
            "P1",
            False,
            "firmware-cgi",
            "OEM firmware.cgi validates and writes the live Linux slot through vendor helpers.",
            "var/www/firmware.cgi; scripts/FWupgrade.sh; validate_image; update_image_flash",
            "firmware.cgi validates and stages a model-bound candidate under /run only; flash=false and reboot=false.",
            "SAFE_STAGE_OFFLINE_HW_PENDING" if om["firmware_volatile_only"] else "UNSAFE_OR_MISSING",
            "Hardware upload smoke is pending; persistent apply remains correctly outside CGI until the flash gate is GO.",
            "Upload valid/invalid images on hardware, verify SHA/CRC/model checks and prove no MTD write, boot change or reboot.",
        ),
    ]


def write_outputs(output: pathlib.Path, facts: dict, rows: list[Row]) -> dict:
    output.mkdir(parents=True, exist_ok=True)
    json_path = output / "track-a-delta.json"
    tsv_path = output / "track-a-delta.tsv"
    audit_path = output / "track-a-audit.json"
    manifest_path = output / "track-a-manifest.json"

    rows_data = [asdict(row) for row in rows]
    payload = {
        "schema": "openmitrastar.track-a-parity-delta/v1",
        "date": "2026-08-20",
        "device": "HGW-500BNA-QCv2 A2",
        "source_firmware": "ES_s00.00_g001_100WNU0b24",
        "minimum_internet_profile": "transparent-videobridge",
        "routed_wan_is_oem_parity": False,
        "rows": rows_data,
    }
    json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    with tsv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows_data[0]), delimiter="\t", lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows_data)
    audit_path.write_text(json.dumps(facts, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    artifacts = {}
    for path in (json_path, tsv_path, audit_path, TRACK_A_DOC):
        artifacts[rel(path)] = {"bytes": path.stat().st_size, "sha256": sha256_file(path)}
    manifest = {
        "schema": "openmitrastar.track-a-parity-manifest/v1",
        "date": "2026-08-20",
        "hardware_actions": 0,
        "flash_writes": 0,
        "rows": len(rows),
        "dump_verified": facts["dump"]["mtd6_verified"],
        "artifacts": artifacts,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def validate(facts: dict, rows: list[Row]) -> list[str]:
    failures: list[str] = []
    if not facts["dump"]["mtd6_verified"]:
        failures.append("verified dump mtd6 hash/manifest mismatch")
    if not all(value == 0 for value in facts["oem"]["wan_object_counts"].values()):
        failures.append("unexpected OEM WAN model objects")
    if facts["oem"]["voice_service_count"] != 0:
        failures.append("unexpected OEM VoiceService object")
    if facts["oem"]["nat_rule_source_hits"]:
        failures.append("unexpected OEM NAT rule in init/scripts")
    if any(facts["oem"]["server_daemons"].values()):
        failures.append("unexpected OEM DHCP/DNS server daemon")
    if not facts["oem"]["bridge_policy"] or not facts["openmitrastar"]["bridge_policy"]:
        failures.append("OEM or OpenMitraStar bridge contract missing")
    if not facts["openmitrastar"]["normal_management_identity"]:
        failures.append("normal .90/recovery .200 OEM-parity identity missing")
    if not facts["openmitrastar"]["normal_web_port_80"]:
        failures.append("normal OEM-parity web port is not 80")
    if not facts["openmitrastar"]["diagnostic_port_8080_disabled"]:
        failures.append("diagnostic port 8080 is not disabled by default")
    if len({row.id for row in rows}) != len(rows):
        failures.append("duplicate matrix row id")
    if not {"wan-pppoe-isp-auth", "vlan", "bridge-l2", "dhcp", "dns", "nat-routing", "firewall-management", "ipv4-management", "ipv6", "ui-cgi"}.issubset({row.capability for row in rows}):
        failures.append("required Track A capability missing")
    serialized = json.dumps([asdict(row) for row in rows], ensure_ascii=False)
    forbidden = (
        r"(?i)wpa_passphrase\s*=",
        r"(?i)pre[-_ ]?shared[-_ ]?key\s*=",
        r"(?i)ConnectionRequestPassword",
        r"(?i)BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY",
        r"(?i)\.openmitrastar-lab\.psk",
    )
    for pattern in forbidden:
        if re.search(pattern, serialized):
            failures.append(f"secret pattern leaked: {pattern}")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--oem-root", type=pathlib.Path, default=DEFAULT_OEM)
    parser.add_argument("--openmitrastar-root", type=pathlib.Path, default=DEFAULT_OM)
    parser.add_argument("--dump", type=pathlib.Path, default=DEFAULT_DUMP)
    parser.add_argument("--output-dir", type=pathlib.Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()

    facts = build_facts(args.oem_root, args.openmitrastar_root, args.dump)
    rows = build_rows(facts)
    failures = validate(facts, rows)
    if failures:
        for failure in failures:
            print(f"W4_TRACK_A_FAIL {failure}", file=sys.stderr)
        return 1
    if not args.check_only:
        manifest = write_outputs(args.output_dir, facts, rows)
        print(
            "W4_TRACK_A_PARITY_PASS "
            f"rows={len(rows)} dump_mtd6_verified=1 "
            f"manifest={rel(args.output_dir / 'track-a-manifest.json')} "
            f"artifacts={len(manifest['artifacts'])}"
        )
    else:
        print(f"W4_TRACK_A_CHECK_PASS rows={len(rows)} dump_mtd6_verified=1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
