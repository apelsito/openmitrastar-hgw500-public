#!/usr/bin/env python3

import csv
import hashlib
import json
import pathlib
import re
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
DOC = ROOT / "docs/HGW500BNA_QCV2_OEM_MOVISTAR_PARITY_MATRIX.md"
TSV = ROOT / "outputs/kernel-port/movistar-parity/capability-matrix.tsv"
MANIFEST = ROOT / "outputs/kernel-port/movistar-parity/manifest.json"
OEM = ROOT / "work/hgw500-rootfs-live/squashfs-root"
HARDWARE_STATE = ROOT / "work/mission-state/HARDWARE_STATE.json"
TX7_MANIFEST = ROOT / "work/mission-state/w2-2g-parity-tx7-hybrid32-v1/build/manifest.json"
TX7_POSTBOOT = ROOT / "outputs/uart-live/w2-tx7-postboot-gate.json"


class MovistarParityMatrixTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = DOC.read_text(encoding="utf-8")
        with TSV.open(encoding="utf-8", newline="") as handle:
            cls.rows = list(csv.DictReader(handle, delimiter="\t"))

    def test_matrix_has_required_schema_and_unique_ids(self):
        self.assertEqual(
            list(self.rows[0]),
            [
                "id",
                "capability",
                "oem_implementation",
                "kernel_userspace_config",
                "linux5_openmitrastar_equivalent",
                "state",
                "test",
            ],
        )
        self.assertGreaterEqual(len(self.rows), 30)
        ids = [row["id"] for row in self.rows]
        self.assertEqual(len(ids), len(set(ids)))

    def test_priority_internet_and_movistar_capabilities_are_present(self):
        capabilities = {row["capability"] for row in self.rows}
        required = {
            "ethernet-emac",
            "topaz-switch",
            "bridge-l2",
            "wan-pppoe",
            "vlan",
            "dhcp-transparent",
            "dhcp-server",
            "dns",
            "nat-routing",
            "firewall",
            "ipv4-management",
            "ipv6",
            "iptv-transport",
            "voip",
            "tr069",
            "leds",
            "buttons",
            "persistence",
            "ui-oem",
        }
        self.assertTrue(required.issubset(capabilities), required - capabilities)

    def test_negative_hgu_boundary_is_explicit(self):
        by_cap = {row["capability"]: row for row in self.rows}
        for capability in ("wan-pppoe", "nat-routing", "voip"):
            self.assertEqual(by_cap[capability]["state"], "N/A_OEM")
        self.assertIn("Implementation=api_fake", self.doc)
        self.assertIn("no son deuda de paridad", self.doc)

    def test_document_and_tsv_do_not_contain_secrets(self):
        combined = self.doc + "\n" + TSV.read_text(encoding="utf-8")
        forbidden = (
            r"(?i)wpa_passphrase\s*=",
            r"(?i)pre[-_ ]?shared[-_ ]?key\s*=",
            r"(?i)<Password\b",
            r"(?i)ConnectionRequestPassword",
            r"(?i)https?://[^\s|]*acs[^\s|]*",
            r"(?i)\.openmitrastar-lab\.psk",
            r"(?i)BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY",
        )
        for pattern in forbidden:
            self.assertIsNone(re.search(pattern, combined), pattern)
        self.assertIn("URL y credenciales omitidas", self.doc)

    def test_cited_oem_files_and_current_evidence_exist(self):
        required = (
            OEM / "etc/default_config.txt",
            OEM / "etc/init.d/S40network",
            OEM / "scripts/qbr",
            OEM / "scripts/start-prod",
            OEM / "etc/config.default.xml",
            OEM / "var/www/top_menu.html",
            OEM / "sbin/tr69c",
            OEM / "usr/sbin/monitor_button",
            ROOT / "work/mission-state/MISSION_STATE.md",
            ROOT / "work/mission-state/HARDWARE_STATE.json",
            ROOT / "work/mission-state/w4-rootfs-product/build/validation.log",
        )
        for path in required:
            self.assertTrue(path.exists(), path)

    def test_real_oem_values_are_still_present(self):
        defaults = (OEM / "etc/default_config.txt").read_text(encoding="utf-8")
        self.assertIn("mode=ap", defaults)
        self.assertIn("staticip=0", defaults)
        self.assertIn("region=es", defaults)
        qbr = (OEM / "scripts/qbr").read_text(encoding="utf-8")
        self.assertIn("brctl setfd br0 0", qbr)
        self.assertIn("brctl setageing br0 7200", qbr)
        config_json = (OEM / "var/www/config.json").read_text(encoding="utf-8")
        self.assertIn('"Implementation":"api_fake"', config_json)

    def test_no_local_dhcp_or_dns_daemon_is_present(self):
        executable_dirs = ("bin", "sbin", "usr/bin", "usr/sbin", "usr/local/bin", "usr/local/sbin")
        for daemon in ("udhcpd", "dnsmasq", "named"):
            for directory in executable_dirs:
                self.assertFalse((OEM / directory / daemon).exists(), f"unexpected {directory}/{daemon}")

    def test_current_linux510_evidence_is_not_downgraded(self):
        hardware = json.loads(HARDWARE_STATE.read_text(encoding="utf-8"))
        tx7 = json.loads(TX7_MANIFEST.read_text(encoding="utf-8"))
        postboot = json.loads(TX7_POSTBOOT.read_text(encoding="utf-8"))

        self.assertEqual(hardware["emac"]["status"], "PROVEN")
        self.assertEqual(hardware["emac"]["interface"], "eth0")
        self.assertEqual(hardware["emac"]["driver"], "qtn-topaz-emac")
        self.assertEqual(hardware["emac"]["irq"], 20)
        self.assertEqual(hardware["emac"]["poll_fallback"], "ENABLED_EXPLICIT_DT")

        self.assertEqual(
            tx7["classification"],
            "RAM-ONLY-W2-2G-PARITY-TX7-HYBRID32-NO-FLASH",
        )
        self.assertFalse(tx7["candidate_eligible"])
        self.assertFalse(tx7["flash_supported"])
        self.assertEqual(tx7["radio2g"]["bridge"], "br0:eth0+wlan0")

        self.assertEqual(postboot["classification"], "RAM-ONLY-TX7-LIVE-CLIENT-GATE-NO-FLASH")
        self.assertFalse(postboot["flash"])
        self.assertTrue(postboot["bridge_eth0_wlan0"])
        self.assertTrue(postboot["hostapd_stable"])
        self.assertTrue(postboot["irq28_progress"])
        self.assertTrue(postboot["no_kernel_oops"])
        self.assertFalse(postboot["associated"])
        self.assertFalse(postboot["authorized"])
        self.assertFalse(postboot["dhcp_lease"])
        self.assertIn("physical client association", postboot["next_gate"])

        image = ROOT / postboot["image"]["path"]
        self.assertEqual(image.stat().st_size, postboot["image"]["bytes"])
        self.assertEqual(hashlib.sha256(image.read_bytes()).hexdigest(), postboot["image"]["sha256"])
        self.assertEqual(
            postboot["image"]["sha256"],
            tx7["artifacts"]["tftp_copy"]["sha256"],
        )

        by_cap = {row["capability"]: row for row in self.rows}
        self.assertEqual(by_cap["bridge-l2"]["state"], "PROVEN_HW")
        self.assertEqual(by_cap["leds"]["state"], "PROVEN_HW")

    def test_manifest_matches_matrix_artifacts(self):
        manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertEqual(manifest["matrix_rows"], len(self.rows))
        self.assertEqual(manifest["hardware_actions"], 0)
        self.assertEqual(manifest["flash_writes"], 0)
        for relative, metadata in manifest["artifacts"].items():
            path = ROOT / relative
            self.assertEqual(path.stat().st_size, metadata["size"], relative)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), metadata["sha256"], relative)


if __name__ == "__main__":
    unittest.main()
