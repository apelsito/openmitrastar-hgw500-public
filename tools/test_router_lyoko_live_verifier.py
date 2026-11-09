#!/usr/bin/env python3

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERIFIER = ROOT / "tools/verify_router_lyoko_live.py"


def sample_payload(**overrides):
    payload = {
        "ok": True,
        "telemetry": {
            "schema": "router-lyoko.runtime-telemetry/v1",
            "classification": "RUNTIME-OBSERVE-ONLY-NO-CONTROL",
            "captured_at_epoch": 1785024000,
            "fresh_after_seconds": 15,
            "stale_after_seconds": 30,
            "runtime_sources": [
                "uname",
                "/proc/uptime",
                "/proc/meminfo",
                "/proc/interrupts",
                "/sys/class/net",
                "/proc/modules",
            ],
            "static_snapshot_is_hardware_proof": False,
        },
        "persona": {"name": "Aelita", "state": "ram-materialized", "rule": "narrative follows telemetry"},
        "system": {
            "model": "HGW-500BNA-QCv2",
            "kernel": "5.10.260-openmitrastar-radiohw",
            "uptime_seconds": "123",
            "mem_total_kb": "65536",
            "mem_available_kb": "32768",
            "load_1m": "0.03",
        },
        "sectors": {
            "core": {"label": "Sector Core", "state": "visible"},
            "bridge": {
                "label": "Sector Bridge",
                "state": "up",
                "eth0_carrier": "1",
                "br0_state": "up",
                "irq20": "1234",
                "emac_polling_fallback": "not_seen",
            },
            "realtek": {
                "label": "Sector Realtek 2.4 GHz",
                "state": "up",
                "rtl_pci": "loaded",
                "rtl8192ee": "loaded",
                "hostapd": "running",
            },
            "quantenna": {
                "label": "Sector Quantenna 5 GHz",
                "state": "missing",
                "qdrv": "missing",
                "wlan": "missing",
                "muc_memory_fault_recent": "not_seen",
            },
            "memory": {"label": "Sector Memory", "state": "read-only", "flash_write_enabled": False},
        },
        "towers": {
            "ssh": {"label": "Tower SSH", "state": "running", "service": "dropbear"},
            "http": {"label": "Tower Interface", "state": "running", "service": "mini_httpd"},
            "logs": {"label": "Tower Logs", "state": "running", "service": "syslogd"},
            "radio2g_ap": {"label": "Tower Realtek AP", "state": "running", "service": "hostapd"},
        },
        "runtime_status": {
            "schema": "router-lyoko.runtime-status/v1",
            "classification": "READONLY-RUNTIME-COVERAGE-NO-CONTROL",
            "coverage": ["system", "ports", "radios", "clients", "bridge", "recovery"],
            "system": {
                "kernel": "5.10.260-openmitrastar-radiohw",
                "uptime_seconds": "123",
                "mem_total_kb": "65536",
                "mem_available_kb": "32768",
                "load_1m": "0.03",
            },
            "ports": {
                "eth0": {"operstate": "up", "carrier": "1", "ipv4": "192.168.1.90/24"},
                "br0": {"operstate": "up", "carrier": "unknown", "ipv4": "192.168.1.90/24"},
                "wlan0": {"operstate": "up", "carrier": "1", "ipv4": ""},
                "wifi0": {"operstate": "missing", "carrier": "unknown", "ipv4": ""},
            },
            "radios": {
                "realtek_2g": {
                    "iface": "wlan0",
                    "operstate": "up",
                    "carrier": "1",
                    "modules": {"rtl_pci": "loaded", "rtl8192ee": "loaded"},
                    "ap_service": "running",
                },
                "quantenna_5g": {
                    "iface": "wifi0",
                    "operstate": "missing",
                    "carrier": "unknown",
                    "modules": {"qdrv": "missing", "wlan": "missing"},
                    "muc_memory_fault_recent": "not_seen",
                },
            },
            "clients": {
                "wlan0": {"source": "iw_station_dump_if_available", "associated_count": "0"},
                "wifi0": {"source": "iw_station_dump_if_available", "associated_count": "unknown"},
            },
            "bridge": {
                "iface": "br0",
                "operstate": "up",
                "ipv4": "192.168.1.90/24",
                "eth0_carrier": "1",
                "irq20": "1234",
                "emac_polling_fallback": "not_seen",
            },
            "recovery": {
                "route": "UART/TFTP/OEM recovery remains externally gated",
                "flash_write_enabled": False,
                "destructive_actions_allowed": False,
                "mtd_entries": "7",
            },
        },
        "runtime_bridge": {
            "schema": "router-lyoko.runtime-bridge/v1",
            "classification": "READONLY-RUNTIME-BRIDGE-MANAGEMENT-NO-CONTROL",
            "sources": ["/sys/class/net", "/proc/interrupts", "pidof", "ip_addr_if_available", "dmesg_tail_classified"],
            "raw_logs_exposed": False,
            "control_surface_exposed": False,
            "bridge": {
                "iface": "br0",
                "operstate": "up",
                "ipv4": "192.168.1.90/24",
                "ipv4_present": "seen",
            },
            "uplink": {
                "iface": "eth0",
                "operstate": "up",
                "carrier": "1",
                "link_observed": "seen",
                "ipv4": "192.168.1.90/24",
                "ipv4_present": "seen",
            },
            "management": {
                "ssh_service": "dropbear",
                "ssh_state": "running",
                "ssh_service_observed": "seen",
                "irq20": "1234",
                "irq20_present": "seen",
                "emac_polling_fallback": "not_seen",
                "management_path_gate": "proven",
                "management_path_proven": True,
            },
        },
        "runtime_recovery": {
            "schema": "router-lyoko.runtime-recovery/v1",
            "classification": "READONLY-RUNTIME-RECOVERY-GUARDS-NO-CONTROL",
            "sources": ["proc_cmdline_classified", "proc_mtd_count", "policy_guard", "external_operator_gate"],
            "raw_cmdline_exposed": False,
            "control_surface_exposed": False,
            "current_boot": {
                "classification": "ram_or_initramfs",
                "ram_boot_observed": "seen",
                "persistent_boot_observed": "not_seen",
            },
            "guards": {
                "flash_write_enabled": False,
                "destructive_actions_allowed": False,
                "bootenv_write_enabled": False,
                "network_reconfigure_allowed": False,
                "module_mutation_allowed": False,
            },
            "fallbacks": {
                "uart_tftp_oem_route": "externally_gated",
                "requires_operator_ack": True,
                "device_can_self_recover": False,
            },
            "mtd": {
                "entries": "7",
                "write_target_selected": False,
            },
            "recovery_gate": {
                "runtime_guards_proven": True,
                "hardware_recovery_proven_current_boot": False,
                "next_required_external_gate": "phase1.current-post-tx7-recovery",
            },
        },
        "runtime_towers": {
            "schema": "router-lyoko.runtime-towers/v1",
            "classification": "READONLY-RUNTIME-SERVICE-TOWERS-NO-CONTROL",
            "sources": ["pidof"],
            "control_surface_exposed": False,
            "towers": {
                "ssh": {
                    "label": "Tower SSH",
                    "sector": "bridge",
                    "role": "secure operator channel",
                    "service": "dropbear",
                    "process": "dropbear",
                    "state": "running",
                    "evidence": "pidof",
                    "control_enabled": False,
                    "writes_device": False,
                },
                "http": {
                    "label": "Tower Interface",
                    "sector": "interface",
                    "role": "local dashboard/API host",
                    "service": "mini_httpd",
                    "process": "mini_httpd",
                    "state": "running",
                    "evidence": "pidof",
                    "control_enabled": False,
                    "writes_device": False,
                },
                "logs": {
                    "label": "Tower Logs",
                    "sector": "core",
                    "role": "diagnostic heartbeat",
                    "service": "syslogd",
                    "process": "syslogd",
                    "state": "running",
                    "evidence": "pidof",
                    "control_enabled": False,
                    "writes_device": False,
                },
                "radio2g_ap": {
                    "label": "Tower Realtek AP",
                    "sector": "realtek",
                    "role": "2.4 GHz access-point supervisor",
                    "service": "hostapd",
                    "process": "hostapd",
                    "state": "running",
                    "evidence": "pidof",
                    "control_enabled": False,
                    "writes_device": False,
                },
            },
        },
        "runtime_events": {
            "schema": "router-lyoko.runtime-events/v1",
            "classification": "READONLY-RUNTIME-EVENT-SUMMARY-NO-RAW-LOGS-NO-CONTROL",
            "sources": [
                "dmesg_tail_classified",
                "/proc/interrupts",
                "/sys/class/net",
                "/proc/modules",
                "iw_station_dump_if_available",
            ],
            "raw_logs_exposed": False,
            "events": [
                {
                    "id": "bridge.emac_polling_fallback",
                    "sector": "bridge",
                    "severity": "warning",
                    "state": "not_seen",
                    "evidence": "classified_flag_only",
                },
                {
                    "id": "bridge.irq20_missing",
                    "sector": "bridge",
                    "severity": "critical",
                    "state": "not_seen",
                    "evidence": "runtime_counter_classified",
                },
                {
                    "id": "realtek.no_associated_clients",
                    "sector": "realtek",
                    "severity": "warning",
                    "state": "seen",
                    "evidence": "runtime_counter_classified",
                },
                {
                    "id": "quantenna.muc_memory_fault",
                    "sector": "quantenna",
                    "severity": "critical",
                    "state": "not_seen",
                    "evidence": "classified_flag_only",
                },
                {
                    "id": "quantenna.no_associated_clients",
                    "sector": "quantenna",
                    "severity": "warning",
                    "state": "unknown",
                    "evidence": "runtime_counter_classified",
                },
                {
                    "id": "recovery.flash_write_guarded",
                    "sector": "recovery",
                    "severity": "info",
                    "state": "seen",
                    "evidence": "policy_guard",
                },
            ],
        },
        "runtime_clients": {
            "schema": "router-lyoko.runtime-clients/v1",
            "classification": "READONLY-RUNTIME-CLIENT-DATA-PATH-NO-CONTROL",
            "sources": ["iw_station_dump_if_available"],
            "raw_station_dump_exposed": False,
            "control_surface_exposed": False,
            "interfaces": {
                "wlan0": {
                    "radio": "realtek_2g",
                    "iface": "wlan0",
                    "source": "iw_station_dump_if_available",
                    "associated_count": "0",
                    "authorized_count": "unknown",
                    "authorized_client_present": "unknown",
                    "rx_bytes_total": "unknown",
                    "tx_bytes_total": "unknown",
                    "rx_packets_total": "unknown",
                    "tx_packets_total": "unknown",
                    "bidirectional_traffic_observed": "unknown",
                    "be_queue_rp_progress": "unknown",
                    "client_data_gate": "no_client",
                    "data_path_proven": False,
                },
                "wifi0": {
                    "radio": "quantenna_5g",
                    "iface": "wifi0",
                    "source": "iw_station_dump_if_available",
                    "associated_count": "unknown",
                    "authorized_count": "unknown",
                    "authorized_client_present": "unknown",
                    "rx_bytes_total": "unknown",
                    "tx_bytes_total": "unknown",
                    "rx_packets_total": "unknown",
                    "tx_packets_total": "unknown",
                    "bidirectional_traffic_observed": "unknown",
                    "be_queue_rp_progress": "unknown",
                    "client_data_gate": "unknown",
                    "data_path_proven": False,
                },
            },
        },
        "mission_data": {
            "classification": "STATIC-READONLY-SNAPSHOT-NO-HARDWARE-PROOF",
            "mission_truth": {"present": True, "bytes": 12000},
            "event_taxonomy": {"present": True, "bytes": 3000},
            "goal_audit": {"present": True, "bytes": 4000},
            "safe_mode": {"present": True, "bytes": 2000},
            "aelita_mission_log": {"present": True, "bytes": 25000},
            "aelita_dialogue": {"present": True, "bytes": 2500},
            "aelita_memory": {"present": True, "bytes": 3000},
            "evidence_bindings": {"present": True, "bytes": 5000},
            "telemetry_contract": {"present": True, "bytes": 2000},
            "control_policy": {"present": True, "bytes": 4000},
        },
        "guards": {
            "mtd_write": False,
            "bootenv_write": False,
            "network_reconfigure": False,
            "module_mutation": False,
        },
    }
    for dotted, value in overrides.items():
        cur = payload
        parts = dotted.split("__")
        for part in parts[:-1]:
            cur = cur[part]
        cur[parts[-1]] = value
    return payload


def run_verifier(payload, *args):
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "lyoko.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        return subprocess.run(
            [sys.executable, str(VERIFIER), "--input-json", str(path), *args],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


class RouterLyokoLiveVerifierTests(unittest.TestCase):
    def test_accepts_valid_live_payload_with_strict_requirements(self):
        proc = run_verifier(
            sample_payload(),
            "--require-kernel-510",
            "--require-bridge-up",
            "--require-ssh-running",
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        report = json.loads(proc.stdout)
        self.assertTrue(report["ok"])
        self.assertTrue(all(check["ok"] for check in report["checks"]))

    def test_rejects_flash_write_enabled(self):
        proc = run_verifier(sample_payload(sectors__memory__flash_write_enabled=True))
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        self.assertFalse(report["ok"])
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("memory.flash_write_disabled", failing)

    def test_rejects_missing_required_sector(self):
        payload = sample_payload()
        payload["sectors"].pop("realtek")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("sectors.realtek.present", failing)
        self.assertIn("sectors.realtek.object", failing)

    def test_rejects_thin_required_sector_object(self):
        payload = sample_payload()
        payload["sectors"]["realtek"] = {"state": "up"}
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("sectors.realtek.label.present", failing)
        self.assertIn("sectors.realtek.rtl_pci.present", failing)
        self.assertIn("sectors.realtek.rtl8192ee.present", failing)
        self.assertIn("sectors.realtek.hostapd.present", failing)

    def test_rejects_invalid_sector_state_values(self):
        payload = sample_payload()
        payload["sectors"]["bridge"]["eth0_carrier"] = "carrier-is-definitely-up"
        payload["sectors"]["bridge"]["irq20"] = "-1"
        payload["sectors"]["quantenna"]["muc_memory_fault_recent"] = "maybe"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("sectors.bridge.eth0_carrier.value", failing)
        self.assertIn("sectors.bridge.irq20.counter", failing)
        self.assertIn("sectors.quantenna.muc_memory_fault_recent.flag", failing)

    def test_rejects_wrong_tower_service_mapping(self):
        payload = sample_payload()
        payload["towers"]["ssh"]["service"] = "telnetd"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("towers.ssh.service", failing)

    def test_rejects_thin_required_tower_object(self):
        payload = sample_payload()
        payload["towers"]["radio2g_ap"] = {"state": "running"}
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("towers.radio2g_ap.label.present", failing)
        self.assertIn("towers.radio2g_ap.service.present", failing)
        self.assertIn("towers.radio2g_ap.service", failing)

    def test_rejects_missing_mission_snapshot_contract(self):
        payload = sample_payload()
        payload.pop("mission_data")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("mission_data.object", failing)

    def test_rejects_unmounted_or_empty_required_mission_snapshot(self):
        payload = sample_payload()
        payload["mission_data"]["mission_truth"]["present"] = False
        payload["mission_data"]["mission_truth"]["bytes"] = 0
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("mission_data.mission_truth.mounted", failing)
        self.assertIn("mission_data.mission_truth.bytes", failing)

    def test_rejects_missing_runtime_telemetry_contract(self):
        payload = sample_payload()
        payload.pop("telemetry")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("telemetry.object", failing)

    def test_rejects_wrong_runtime_telemetry_schema(self):
        proc = run_verifier(
            sample_payload(telemetry__schema="router-lyoko.runtime-telemetry/v0")
        )
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("telemetry.schema", failing)

    def test_rejects_empty_runtime_sources(self):
        proc = run_verifier(sample_payload(telemetry__runtime_sources=[]))
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("telemetry.runtime_sources", failing)

    def test_rejects_missing_required_runtime_source(self):
        payload = sample_payload()
        payload["telemetry"]["runtime_sources"].remove("/proc/interrupts")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("telemetry.runtime_sources./proc/interrupts", failing)

    def test_rejects_invalid_freshness_thresholds(self):
        proc = run_verifier(
            sample_payload(
                telemetry__fresh_after_seconds=30,
                telemetry__stale_after_seconds=15,
            )
        )
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("telemetry.fresh_before_stale", failing)

    def test_rejects_wrong_device_model(self):
        proc = run_verifier(sample_payload(system__model="HGW-500BNA-QCv3"))
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("system.model", failing)

    def test_rejects_invalid_runtime_metrics(self):
        proc = run_verifier(
            sample_payload(
                system__uptime_seconds="unknown",
                system__mem_total_kb="0",
                system__load_1m="unknown",
            )
        )
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("system.uptime_seconds", failing)
        self.assertIn("system.mem_total_kb", failing)
        self.assertIn("system.load_1m", failing)

    def test_rejects_available_memory_greater_than_total(self):
        proc = run_verifier(
            sample_payload(system__mem_total_kb="1024", system__mem_available_kb="2048")
        )
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("system.mem_available_le_total", failing)

    def test_rejects_missing_runtime_status_contract(self):
        payload = sample_payload()
        payload.pop("runtime_status")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_status.object", failing)

    def test_rejects_runtime_status_without_clients_coverage(self):
        payload = sample_payload()
        payload["runtime_status"]["coverage"].remove("clients")
        payload["runtime_status"].pop("clients")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_status.coverage.clients", failing)
        self.assertIn("runtime_status.clients.object", failing)

    def test_rejects_runtime_status_without_recovery_guard(self):
        payload = sample_payload()
        payload["runtime_status"]["recovery"]["flash_write_enabled"] = True
        payload["runtime_status"]["recovery"]["destructive_actions_allowed"] = True
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_status.recovery.flash_write_disabled", failing)
        self.assertIn("runtime_status.recovery.no_destructive_actions", failing)

    def test_rejects_invalid_runtime_status_port_and_client_values(self):
        payload = sample_payload()
        payload["runtime_status"]["ports"]["wlan0"]["carrier"] = "associated"
        payload["runtime_status"]["clients"]["wlan0"]["associated_count"] = "-1"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_status.ports.wlan0.carrier", failing)
        self.assertIn("runtime_status.clients.wlan0.associated_count", failing)

    def test_rejects_missing_runtime_bridge_contract(self):
        payload = sample_payload()
        payload.pop("runtime_bridge")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_bridge.object", failing)

    def test_rejects_runtime_bridge_raw_or_control_exposure(self):
        payload = sample_payload()
        payload["runtime_bridge"]["raw_logs_exposed"] = True
        payload["runtime_bridge"]["control_surface_exposed"] = True
        payload["runtime_bridge"]["command"] = "ip addr show br0"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_bridge.raw_logs_exposed.false", failing)
        self.assertIn("runtime_bridge.control_surface_exposed.false", failing)
        self.assertIn("runtime_bridge.no_raw_or_control_fields", failing)

    def test_rejects_invalid_runtime_bridge_values(self):
        payload = sample_payload()
        payload["runtime_bridge"]["bridge"]["iface"] = "eth0"
        payload["runtime_bridge"]["uplink"]["carrier"] = "linked"
        payload["runtime_bridge"]["management"]["irq20"] = "-1"
        payload["runtime_bridge"]["management"]["management_path_gate"] = "carrier_is_enough"
        payload["runtime_bridge"]["management"]["management_path_proven"] = "true"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_bridge.bridge.iface", failing)
        self.assertIn("runtime_bridge.uplink.carrier", failing)
        self.assertIn("runtime_bridge.management.irq20", failing)
        self.assertIn("runtime_bridge.management.management_path_gate", failing)
        self.assertIn("runtime_bridge.management.management_path_proven.boolean", failing)

    def test_rejects_inconsistent_runtime_bridge_proven_claim(self):
        payload = sample_payload()
        payload["runtime_bridge"]["uplink"]["link_observed"] = "not_seen"
        payload["runtime_bridge"]["management"]["management_path_gate"] = "proven"
        payload["runtime_bridge"]["management"]["management_path_proven"] = True
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_bridge.management.proven_requires_eth0_link", failing)

    def test_strict_management_path_gate_rejects_carrier_only(self):
        payload = sample_payload()
        payload["runtime_bridge"]["bridge"]["ipv4"] = ""
        payload["runtime_bridge"]["bridge"]["ipv4_present"] = "not_seen"
        payload["runtime_bridge"]["management"]["ssh_state"] = "stopped"
        payload["runtime_bridge"]["management"]["ssh_service_observed"] = "not_seen"
        payload["runtime_bridge"]["management"]["management_path_gate"] = "carrier_only"
        payload["runtime_bridge"]["management"]["management_path_proven"] = False
        proc = run_verifier(payload, "--require-management-path")
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("management_path.br0_ip", failing)
        self.assertIn("management_path.ssh", failing)
        self.assertIn("management_path.proven", failing)

    def test_strict_management_path_gate_accepts_link_ip_irq_ssh(self):
        proc = run_verifier(sample_payload(), "--require-management-path")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_rejects_missing_runtime_recovery_contract(self):
        payload = sample_payload()
        payload.pop("runtime_recovery")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_recovery.object", failing)

    def test_rejects_runtime_recovery_raw_or_control_exposure(self):
        payload = sample_payload()
        payload["runtime_recovery"]["raw_cmdline_exposed"] = True
        payload["runtime_recovery"]["control_surface_exposed"] = True
        payload["runtime_recovery"]["command"] = "printenv"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_recovery.raw_cmdline_exposed.false", failing)
        self.assertIn("runtime_recovery.control_surface_exposed.false", failing)
        self.assertIn("runtime_recovery.no_raw_or_control_fields", failing)

    def test_rejects_runtime_recovery_write_or_self_recover_claims(self):
        payload = sample_payload()
        payload["runtime_recovery"]["guards"]["flash_write_enabled"] = True
        payload["runtime_recovery"]["guards"]["bootenv_write_enabled"] = True
        payload["runtime_recovery"]["guards"]["network_reconfigure_allowed"] = True
        payload["runtime_recovery"]["guards"]["module_mutation_allowed"] = True
        payload["runtime_recovery"]["fallbacks"]["device_can_self_recover"] = True
        payload["runtime_recovery"]["mtd"]["write_target_selected"] = True
        payload["runtime_recovery"]["recovery_gate"]["hardware_recovery_proven_current_boot"] = True
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_recovery.guards.flash_write_enabled.false", failing)
        self.assertIn("runtime_recovery.guards.bootenv_write_enabled.false", failing)
        self.assertIn("runtime_recovery.guards.network_reconfigure_allowed.false", failing)
        self.assertIn("runtime_recovery.guards.module_mutation_allowed.false", failing)
        self.assertIn("runtime_recovery.fallbacks.device_can_self_recover.false", failing)
        self.assertIn("runtime_recovery.mtd.write_target_selected.false", failing)
        self.assertIn("runtime_recovery.recovery_gate.hardware_recovery_proven_current_boot.false", failing)

    def test_rejects_invalid_runtime_recovery_values(self):
        payload = sample_payload()
        payload["runtime_recovery"]["current_boot"]["classification"] = "definitely_flash"
        payload["runtime_recovery"]["current_boot"]["ram_boot_observed"] = "maybe"
        payload["runtime_recovery"]["fallbacks"]["uart_tftp_oem_route"] = "self_healing"
        payload["runtime_recovery"]["fallbacks"]["requires_operator_ack"] = False
        payload["runtime_recovery"]["mtd"]["entries"] = "-1"
        payload["runtime_recovery"]["recovery_gate"]["runtime_guards_proven"] = False
        payload["runtime_recovery"]["recovery_gate"]["next_required_external_gate"] = "skip-to-flash"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_recovery.current_boot.classification", failing)
        self.assertIn("runtime_recovery.current_boot.ram_boot_observed", failing)
        self.assertIn("runtime_recovery.fallbacks.uart_tftp_oem_route", failing)
        self.assertIn("runtime_recovery.fallbacks.requires_operator_ack", failing)
        self.assertIn("runtime_recovery.mtd.entries", failing)
        self.assertIn("runtime_recovery.recovery_gate.runtime_guards_proven", failing)
        self.assertIn("runtime_recovery.recovery_gate.next_required_external_gate", failing)

    def test_strict_recovery_guards_accepts_readonly_external_gate(self):
        proc = run_verifier(sample_payload(), "--require-recovery-guards")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_strict_recovery_guards_rejects_write_target_or_self_recover(self):
        payload = sample_payload()
        payload["runtime_recovery"]["mtd"]["write_target_selected"] = True
        payload["runtime_recovery"]["fallbacks"]["device_can_self_recover"] = True
        proc = run_verifier(payload, "--require-recovery-guards")
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("recovery_guards.no_mtd_write_target", failing)
        self.assertIn("recovery_guards.no_self_recover_claim", failing)

    def test_rejects_missing_runtime_towers_contract(self):
        payload = sample_payload()
        payload.pop("runtime_towers")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_towers.object", failing)

    def test_rejects_runtime_towers_control_or_write_enabled(self):
        payload = sample_payload()
        payload["runtime_towers"]["control_surface_exposed"] = True
        payload["runtime_towers"]["towers"]["ssh"]["control_enabled"] = True
        payload["runtime_towers"]["towers"]["ssh"]["writes_device"] = True
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_towers.control_surface_exposed.false", failing)
        self.assertIn("runtime_towers.towers.ssh.control_disabled", failing)
        self.assertIn("runtime_towers.towers.ssh.writes_disabled", failing)

    def test_rejects_runtime_towers_wrong_service_mapping(self):
        payload = sample_payload()
        payload["runtime_towers"]["towers"]["ssh"]["service"] = "telnetd"
        payload["runtime_towers"]["towers"]["ssh"]["process"] = "telnetd"
        payload["runtime_towers"]["towers"]["ssh"]["evidence"] = "shell_command"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_towers.towers.ssh.service", failing)
        self.assertIn("runtime_towers.towers.ssh.process", failing)
        self.assertIn("runtime_towers.towers.ssh.evidence", failing)

    def test_rejects_missing_runtime_events_contract(self):
        payload = sample_payload()
        payload.pop("runtime_events")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_events.object", failing)

    def test_rejects_runtime_events_raw_log_exposure(self):
        payload = sample_payload()
        payload["runtime_events"]["raw_logs_exposed"] = True
        payload["runtime_events"]["events"][0]["message"] = "raw dmesg line must never be exported"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_events.raw_logs_exposed.false", failing)
        self.assertIn("runtime_events.events.0.no_raw_log_fields", failing)

    def test_rejects_runtime_events_missing_required_event(self):
        payload = sample_payload()
        payload["runtime_events"]["events"] = [
            event
            for event in payload["runtime_events"]["events"]
            if event["id"] != "quantenna.muc_memory_fault"
        ]
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_events.required.quantenna.muc_memory_fault", failing)

    def test_rejects_invalid_runtime_event_values(self):
        payload = sample_payload()
        payload["runtime_events"]["events"][0]["severity"] = "panic"
        payload["runtime_events"]["events"][0]["state"] = "maybe"
        payload["runtime_events"]["events"][0]["evidence"] = "raw_log_excerpt"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_events.events.0.severity", failing)
        self.assertIn("runtime_events.events.0.state", failing)
        self.assertIn("runtime_events.events.0.evidence", failing)

    def test_rejects_missing_runtime_clients_contract(self):
        payload = sample_payload()
        payload.pop("runtime_clients")
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_clients.object", failing)

    def test_rejects_runtime_clients_raw_or_control_exposure(self):
        payload = sample_payload()
        payload["runtime_clients"]["raw_station_dump_exposed"] = True
        payload["runtime_clients"]["control_surface_exposed"] = True
        payload["runtime_clients"]["interfaces"]["wlan0"]["raw_station_dump"] = "Station aa:bb:cc:dd:ee:ff"
        payload["runtime_clients"]["interfaces"]["wlan0"]["command"] = "iw dev wlan0 station dump"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_clients.raw_station_dump_exposed.false", failing)
        self.assertIn("runtime_clients.control_surface_exposed.false", failing)
        self.assertIn("runtime_clients.interfaces.wlan0.no_raw_or_control_fields", failing)

    def test_rejects_invalid_runtime_client_values(self):
        payload = sample_payload()
        client = payload["runtime_clients"]["interfaces"]["wlan0"]
        client["associated_count"] = "-1"
        client["authorized_client_present"] = "maybe"
        client["bidirectional_traffic_observed"] = "sort-of"
        client["be_queue_rp_progress"] = "maybe"
        client["client_data_gate"] = "ssid_visible"
        client["data_path_proven"] = "false"
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_clients.interfaces.wlan0.associated_count", failing)
        self.assertIn("runtime_clients.interfaces.wlan0.authorized_client_present", failing)
        self.assertIn("runtime_clients.interfaces.wlan0.bidirectional_traffic_observed", failing)
        self.assertIn("runtime_clients.interfaces.wlan0.be_queue_rp_progress", failing)
        self.assertIn("runtime_clients.interfaces.wlan0.client_data_gate", failing)
        self.assertIn("runtime_clients.interfaces.wlan0.data_path_proven.boolean", failing)

    def test_rejects_inconsistent_runtime_client_proven_claim(self):
        payload = sample_payload()
        client = payload["runtime_clients"]["interfaces"]["wlan0"]
        client["associated_count"] = "1"
        client["authorized_count"] = "1"
        client["authorized_client_present"] = "seen"
        client["bidirectional_traffic_observed"] = "seen"
        client["be_queue_rp_progress"] = "unknown"
        client["client_data_gate"] = "proven"
        client["data_path_proven"] = True
        proc = run_verifier(payload)
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("runtime_clients.interfaces.wlan0.proven_requires_be_queue", failing)

    def test_strict_realtek_client_data_gate_rejects_association_only(self):
        payload = sample_payload()
        client = payload["runtime_clients"]["interfaces"]["wlan0"]
        client["associated_count"] = "1"
        client["authorized_count"] = "1"
        client["authorized_client_present"] = "seen"
        client["rx_packets_total"] = "10"
        client["tx_packets_total"] = "12"
        client["bidirectional_traffic_observed"] = "seen"
        client["client_data_gate"] = "traffic_without_be_queue"
        proc = run_verifier(payload, "--require-realtek-client-data-path")
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("realtek.client_data_path.be_queue_rp", failing)
        self.assertIn("realtek.client_data_path.proven", failing)

    def test_strict_realtek_client_data_gate_accepts_authorized_bidirectional_be_progress(self):
        payload = sample_payload()
        client = payload["runtime_clients"]["interfaces"]["wlan0"]
        client["associated_count"] = "1"
        client["authorized_count"] = "1"
        client["authorized_client_present"] = "seen"
        client["rx_bytes_total"] = "2048"
        client["tx_bytes_total"] = "4096"
        client["rx_packets_total"] = "10"
        client["tx_packets_total"] = "12"
        client["bidirectional_traffic_observed"] = "seen"
        client["be_queue_rp_progress"] = "seen"
        client["client_data_gate"] = "proven"
        client["data_path_proven"] = True
        proc = run_verifier(payload, "--require-realtek-client-data-path")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_rejects_static_snapshot_as_runtime_hardware_proof(self):
        proc = run_verifier(
            sample_payload(telemetry__static_snapshot_is_hardware_proof=True)
        )
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("telemetry.static_not_hardware_proof", failing)

    def test_rejects_mission_snapshot_as_hardware_proof(self):
        proc = run_verifier(
            sample_payload(mission_data__classification="STATIC-SNAPSHOT-HARDWARE-PASS")
        )
        self.assertNotEqual(proc.returncode, 0)
        report = json.loads(proc.stdout)
        failing = {check["id"] for check in report["checks"] if not check["ok"]}
        self.assertIn("mission_data.classification", failing)

    def test_strict_bridge_gate_is_optional_and_explicit(self):
        payload = sample_payload(sectors__bridge__state="down", sectors__bridge__eth0_carrier="0")
        loose = run_verifier(payload)
        strict = run_verifier(payload, "--require-bridge-up")
        self.assertEqual(loose.returncode, 0, loose.stdout)
        self.assertNotEqual(strict.returncode, 0, strict.stdout)


if __name__ == "__main__":
    unittest.main()
