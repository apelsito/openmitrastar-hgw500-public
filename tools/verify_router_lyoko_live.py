#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any


DEFAULT_URL = "http://192.168.1.90/api/lyoko"

REQUIRED_SECTORS = ("core", "bridge", "realtek", "quantenna", "memory")
REQUIRED_TOWERS = ("ssh", "http", "logs", "radio2g_ap")
REQUIRED_SECTOR_FIELDS = {
    "core": ("label", "state"),
    "bridge": ("label", "state", "eth0_carrier", "br0_state", "irq20", "emac_polling_fallback"),
    "realtek": ("label", "state", "rtl_pci", "rtl8192ee", "hostapd"),
    "quantenna": ("label", "state", "qdrv", "wlan", "muc_memory_fault_recent"),
    "memory": ("label", "state", "flash_write_enabled"),
}
EXPECTED_TOWER_SERVICES = {
    "ssh": "dropbear",
    "http": "mini_httpd",
    "logs": "syslogd",
    "radio2g_ap": "hostapd",
}
REQUIRED_GUARDS_FALSE = (
    "mtd_write",
    "bootenv_write",
    "network_reconfigure",
    "module_mutation",
)
REQUIRED_MISSION_DATA = (
    "mission_truth",
    "event_taxonomy",
    "goal_audit",
    "safe_mode",
    "aelita_mission_log",
    "aelita_dialogue",
    "aelita_memory",
    "evidence_bindings",
    "telemetry_contract",
    "control_policy",
)
REQUIRED_RUNTIME_SOURCES = (
    "uname",
    "/proc/uptime",
    "/proc/meminfo",
    "/proc/interrupts",
    "/sys/class/net",
    "/proc/modules",
)
EXPECTED_MODEL = "HGW-500BNA-QCv2"
EXPECTED_TELEMETRY_SCHEMA = "router-lyoko.runtime-telemetry/v1"
EXPECTED_RUNTIME_STATUS_SCHEMA = "router-lyoko.runtime-status/v1"
EXPECTED_RUNTIME_BRIDGE_SCHEMA = "router-lyoko.runtime-bridge/v1"
EXPECTED_RUNTIME_RECOVERY_SCHEMA = "router-lyoko.runtime-recovery/v1"
EXPECTED_RUNTIME_EVENTS_SCHEMA = "router-lyoko.runtime-events/v1"
EXPECTED_RUNTIME_TOWERS_SCHEMA = "router-lyoko.runtime-towers/v1"
EXPECTED_RUNTIME_CLIENTS_SCHEMA = "router-lyoko.runtime-clients/v1"
REQUIRED_RUNTIME_STATUS_SECTIONS = ("system", "ports", "radios", "clients", "bridge", "recovery")
REQUIRED_RUNTIME_BRIDGE_SOURCES = (
    "/sys/class/net",
    "/proc/interrupts",
    "pidof",
)
REQUIRED_RUNTIME_BRIDGE_SECTIONS = ("bridge", "uplink", "management")
REQUIRED_RUNTIME_RECOVERY_SOURCES = (
    "proc_cmdline_classified",
    "proc_mtd_count",
    "policy_guard",
    "external_operator_gate",
)
REQUIRED_RUNTIME_RECOVERY_SECTIONS = ("current_boot", "guards", "fallbacks", "mtd", "recovery_gate")
REQUIRED_PORTS = ("eth0", "br0", "wlan0", "wifi0")
REQUIRED_RADIOS = ("realtek_2g", "quantenna_5g")
REQUIRED_CLIENT_INTERFACES = ("wlan0", "wifi0")
EXPECTED_RUNTIME_CLIENT_RADIOS = {"wlan0": "realtek_2g", "wifi0": "quantenna_5g"}
REQUIRED_RUNTIME_CLIENT_SOURCES = ("iw_station_dump_if_available",)
REQUIRED_RUNTIME_CLIENT_FIELDS = (
    "radio",
    "iface",
    "source",
    "associated_count",
    "authorized_count",
    "authorized_client_present",
    "rx_bytes_total",
    "tx_bytes_total",
    "rx_packets_total",
    "tx_packets_total",
    "bidirectional_traffic_observed",
    "be_queue_rp_progress",
    "client_data_gate",
    "data_path_proven",
)
REQUIRED_RUNTIME_TOWER_SOURCES = ("pidof",)
REQUIRED_RUNTIME_TOWER_FIELDS = (
    "label",
    "sector",
    "role",
    "service",
    "process",
    "state",
    "evidence",
    "control_enabled",
    "writes_device",
)
REQUIRED_RUNTIME_EVENT_SOURCES = (
    "dmesg_tail_classified",
    "/proc/interrupts",
    "/sys/class/net",
    "/proc/modules",
)
REQUIRED_RUNTIME_EVENT_IDS = (
    "bridge.emac_polling_fallback",
    "bridge.irq20_missing",
    "realtek.no_associated_clients",
    "quantenna.muc_memory_fault",
    "recovery.flash_write_guarded",
)
OPERSTATE_VALUES = {"up", "down", "unknown", "dormant", "notpresent", "lowerlayerdown", "testing", "missing"}
LINK_CARRIER_VALUES = {"0", "1", "unknown"}
MODULE_VALUES = {"loaded", "missing"}
DMESG_FLAG_VALUES = {"seen", "not_seen"}
SERVICE_STATE_VALUES = {"running", "stopped"}
TOWER_EVIDENCE_VALUES = {"pidof"}
EVENT_SEVERITY_VALUES = {"info", "warning", "critical"}
EVENT_STATE_VALUES = {"seen", "not_seen", "unknown"}
EVENT_EVIDENCE_VALUES = {"classified_flag_only", "runtime_counter_classified", "policy_guard"}
FORBIDDEN_RUNTIME_EVENT_FIELDS = {"raw_log", "raw_logs", "log", "logs", "line", "lines", "message", "messages", "command", "control"}
CLIENT_SIGNAL_VALUES = {"seen", "not_seen", "unknown"}
CLIENT_GATE_VALUES = {
    "proven",
    "no_client",
    "associated_only_not_proven",
    "associated_not_authorized_proof",
    "traffic_without_be_queue",
    "unknown",
}
BRIDGE_SIGNAL_VALUES = {"seen", "not_seen", "unknown"}
BRIDGE_GATE_VALUES = {
    "proven",
    "carrier_only",
    "ip_without_ssh",
    "ssh_without_bridge_proof",
    "degraded_polling_fallback",
    "blocked_or_missing",
    "unknown",
}
BOOT_CLASSIFICATION_VALUES = {"ram_or_initramfs", "persistent_or_block_root", "unknown"}
FORBIDDEN_RUNTIME_CLIENT_FIELDS = {
    "raw_station_dump",
    "station_dump",
    "mac",
    "macs",
    "client_mac",
    "client_macs",
    "command",
    "control",
}
FORBIDDEN_RUNTIME_BRIDGE_FIELDS = {
    "raw_log",
    "raw_logs",
    "log",
    "logs",
    "line",
    "lines",
    "message",
    "messages",
    "command",
    "control",
}
FORBIDDEN_RUNTIME_RECOVERY_FIELDS = {
    "raw_cmdline",
    "cmdline",
    "raw_log",
    "raw_logs",
    "log",
    "logs",
    "line",
    "lines",
    "message",
    "messages",
    "command",
    "control",
}


@dataclass(frozen=True)
class Check:
    id: str
    ok: bool
    detail: str


def get_path(doc: dict[str, Any], dotted: str) -> Any:
    cur: Any = doc
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return None
        cur = cur[part]
    return cur


def parse_nonnegative_int(value: Any) -> int | None:
    try:
        text = str(value).strip()
        if not text or not text.isdigit():
            return None
        parsed = int(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def parse_nonnegative_float(value: Any) -> float | None:
    try:
        text = str(value).strip()
        if not text:
            return None
        parsed = float(text)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def nonempty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def normalized_text(value: Any) -> str:
    return str(value).strip()


def is_service_state(value: Any) -> bool:
    text = normalized_text(value)
    return text in SERVICE_STATE_VALUES or text.startswith("running:")


def is_irq_counter(value: Any) -> bool:
    text = normalized_text(value)
    return text == "missing" or text.isdigit()


def is_client_count(value: Any) -> bool:
    text = normalized_text(value)
    return text == "unknown" or text.isdigit()


def load_payload(args: argparse.Namespace) -> tuple[dict[str, Any], str]:
    if args.input_json:
        path = Path(args.input_json)
        return json.loads(path.read_text(encoding="utf-8")), f"file:{path}"
    if args.stdin:
        return json.loads(sys.stdin.read()), "stdin"

    req = urllib.request.Request(
        args.url,
        headers={
            "Accept": "application/json",
            "Cache-Control": "no-cache",
            "User-Agent": "openmitrastar-router-lyoko-verifier/1",
        },
        method="GET",
    )
    started = time.monotonic()
    with urllib.request.urlopen(req, timeout=args.timeout) as response:
        body = response.read(args.max_bytes + 1)
        elapsed_ms = int((time.monotonic() - started) * 1000)
        if len(body) > args.max_bytes:
            raise RuntimeError(f"response exceeded max bytes: {args.max_bytes}")
        ctype = response.headers.get("Content-Type", "")
        payload = json.loads(body.decode("utf-8"))
        return payload, f"url:{args.url} status={response.status} content_type={ctype} elapsed_ms={elapsed_ms}"


def validate(
    doc: dict[str, Any],
    *,
    require_kernel_510: bool,
    require_bridge_up: bool,
    require_ssh_running: bool,
    require_management_path: bool,
    require_recovery_guards: bool,
    require_realtek_client_data_path: bool,
) -> list[Check]:
    checks: list[Check] = []

    checks.append(Check("json.ok", doc.get("ok") is True, "`ok` must be true"))
    checks.append(
        Check(
            "persona.aelita",
            get_path(doc, "persona.name") == "Aelita",
            "persona.name must be Aelita",
        )
    )
    checks.append(
        Check(
            "persona.truth_rule",
            "telemetry" in str(get_path(doc, "persona.rule") or "").lower(),
            "persona.rule must tie narrative to telemetry",
        )
    )

    telemetry = doc.get("telemetry")
    checks.append(Check("telemetry.object", isinstance(telemetry, dict), "telemetry must be an object"))
    if isinstance(telemetry, dict):
        checks.append(
            Check(
                "telemetry.schema",
                telemetry.get("schema") == EXPECTED_TELEMETRY_SCHEMA,
                f"telemetry.schema must be {EXPECTED_TELEMETRY_SCHEMA}",
            )
        )
        checks.append(
            Check(
                "telemetry.observe_only",
                telemetry.get("classification") == "RUNTIME-OBSERVE-ONLY-NO-CONTROL",
                "telemetry must be observe-only",
            )
        )
        checks.append(
            Check(
                "telemetry.captured_at_epoch",
                isinstance(telemetry.get("captured_at_epoch"), int) and telemetry.get("captured_at_epoch", 0) >= 0,
                "telemetry.captured_at_epoch must be a non-negative integer",
            )
        )
        checks.append(
            Check(
                "telemetry.static_not_hardware_proof",
                telemetry.get("static_snapshot_is_hardware_proof") is False,
                "static snapshots must not be marked as hardware proof",
            )
        )
        runtime_sources = telemetry.get("runtime_sources")
        checks.append(
            Check(
                "telemetry.runtime_sources",
                isinstance(runtime_sources, list) and bool(runtime_sources),
                "telemetry.runtime_sources must be a non-empty list",
            )
        )
        if isinstance(runtime_sources, list):
            source_set = {str(source) for source in runtime_sources}
            for required_source in REQUIRED_RUNTIME_SOURCES:
                checks.append(
                    Check(
                        f"telemetry.runtime_sources.{required_source}",
                        required_source in source_set,
                        f"telemetry.runtime_sources must include {required_source}",
                    )
                )
        fresh_after = parse_nonnegative_int(telemetry.get("fresh_after_seconds"))
        stale_after = parse_nonnegative_int(telemetry.get("stale_after_seconds"))
        checks.append(
            Check(
                "telemetry.fresh_after_seconds",
                fresh_after is not None and fresh_after > 0,
                "telemetry.fresh_after_seconds must be a positive integer",
            )
        )
        checks.append(
            Check(
                "telemetry.stale_after_seconds",
                stale_after is not None and stale_after > 0,
                "telemetry.stale_after_seconds must be a positive integer",
            )
        )
        if fresh_after is not None and stale_after is not None:
            checks.append(
                Check(
                    "telemetry.fresh_before_stale",
                    fresh_after < stale_after,
                    "telemetry.fresh_after_seconds must be less than stale_after_seconds",
                )
            )

    model = str(get_path(doc, "system.model") or "")
    checks.append(Check("system.model", model == EXPECTED_MODEL, f"system.model must be {EXPECTED_MODEL}, got {model!r}"))
    kernel = str(get_path(doc, "system.kernel") or "")
    if require_kernel_510:
        checks.append(Check("system.kernel_510", "5.10" in kernel, f"kernel must contain 5.10, got {kernel!r}"))
    else:
        checks.append(Check("system.kernel_present", bool(kernel), "system.kernel must be present"))

    uptime = parse_nonnegative_int(get_path(doc, "system.uptime_seconds"))
    mem_total = parse_nonnegative_int(get_path(doc, "system.mem_total_kb"))
    mem_available = parse_nonnegative_int(get_path(doc, "system.mem_available_kb"))
    load_1m = parse_nonnegative_float(get_path(doc, "system.load_1m"))
    checks.append(Check("system.uptime_seconds", uptime is not None, "system.uptime_seconds must be a non-negative integer"))
    checks.append(Check("system.mem_total_kb", mem_total is not None and mem_total > 0, "system.mem_total_kb must be a positive integer"))
    checks.append(Check("system.mem_available_kb", mem_available is not None, "system.mem_available_kb must be a non-negative integer"))
    checks.append(Check("system.load_1m", load_1m is not None, "system.load_1m must be a non-negative number"))
    if mem_total is not None and mem_available is not None:
        checks.append(
            Check(
                "system.mem_available_le_total",
                mem_available <= mem_total,
                "system.mem_available_kb must not exceed system.mem_total_kb",
            )
        )

    runtime_status = doc.get("runtime_status")
    checks.append(
        Check(
            "runtime_status.object",
            isinstance(runtime_status, dict),
            "runtime_status must be an object",
        )
    )
    if isinstance(runtime_status, dict):
        checks.append(
            Check(
                "runtime_status.schema",
                runtime_status.get("schema") == EXPECTED_RUNTIME_STATUS_SCHEMA,
                f"runtime_status.schema must be {EXPECTED_RUNTIME_STATUS_SCHEMA}",
            )
        )
        checks.append(
            Check(
                "runtime_status.classification",
                runtime_status.get("classification") == "READONLY-RUNTIME-COVERAGE-NO-CONTROL",
                "runtime_status must be classified as read-only/no-control",
            )
        )
        coverage = runtime_status.get("coverage")
        checks.append(
            Check(
                "runtime_status.coverage",
                isinstance(coverage, list) and bool(coverage),
                "runtime_status.coverage must be a non-empty list",
            )
        )
        if isinstance(coverage, list):
            coverage_set = {str(item) for item in coverage}
            for section in REQUIRED_RUNTIME_STATUS_SECTIONS:
                checks.append(
                    Check(
                        f"runtime_status.coverage.{section}",
                        section in coverage_set,
                        f"runtime_status.coverage must include {section}",
                    )
                )

        status_system = runtime_status.get("system")
        checks.append(Check("runtime_status.system.object", isinstance(status_system, dict), "runtime_status.system must be an object"))
        if isinstance(status_system, dict):
            checks.append(Check("runtime_status.system.kernel", nonempty_text(status_system.get("kernel")), "runtime_status.system.kernel must be non-empty text"))
            checks.append(Check("runtime_status.system.uptime_seconds", parse_nonnegative_int(status_system.get("uptime_seconds")) is not None, "runtime_status.system.uptime_seconds must be a non-negative integer"))
            status_mem_total = parse_nonnegative_int(status_system.get("mem_total_kb"))
            status_mem_available = parse_nonnegative_int(status_system.get("mem_available_kb"))
            checks.append(Check("runtime_status.system.mem_total_kb", status_mem_total is not None and status_mem_total > 0, "runtime_status.system.mem_total_kb must be a positive integer"))
            checks.append(Check("runtime_status.system.mem_available_kb", status_mem_available is not None, "runtime_status.system.mem_available_kb must be a non-negative integer"))
            checks.append(Check("runtime_status.system.load_1m", parse_nonnegative_float(status_system.get("load_1m")) is not None, "runtime_status.system.load_1m must be a non-negative number"))
            if status_mem_total is not None and status_mem_available is not None:
                checks.append(
                    Check(
                        "runtime_status.system.mem_available_le_total",
                        status_mem_available <= status_mem_total,
                        "runtime_status.system.mem_available_kb must not exceed mem_total_kb",
                    )
                )

        ports = runtime_status.get("ports")
        checks.append(Check("runtime_status.ports.object", isinstance(ports, dict), "runtime_status.ports must be an object"))
        if isinstance(ports, dict):
            for port in REQUIRED_PORTS:
                port_doc = ports.get(port)
                checks.append(Check(f"runtime_status.ports.{port}.object", isinstance(port_doc, dict), f"runtime_status.ports.{port} must be an object"))
                if isinstance(port_doc, dict):
                    checks.append(
                        Check(
                            f"runtime_status.ports.{port}.operstate",
                            normalized_text(port_doc.get("operstate")) in OPERSTATE_VALUES,
                            f"runtime_status.ports.{port}.operstate must be a known Linux operstate or missing",
                        )
                    )
                    checks.append(
                        Check(
                            f"runtime_status.ports.{port}.carrier",
                            normalized_text(port_doc.get("carrier")) in LINK_CARRIER_VALUES,
                            f"runtime_status.ports.{port}.carrier must be 0, 1, or unknown",
                        )
                    )
                    checks.append(
                        Check(
                            f"runtime_status.ports.{port}.ipv4.present",
                            isinstance(port_doc.get("ipv4"), str),
                            f"runtime_status.ports.{port}.ipv4 must be present as text",
                        )
                    )

        radios = runtime_status.get("radios")
        checks.append(Check("runtime_status.radios.object", isinstance(radios, dict), "runtime_status.radios must be an object"))
        if isinstance(radios, dict):
            for radio in REQUIRED_RADIOS:
                radio_doc = radios.get(radio)
                checks.append(Check(f"runtime_status.radios.{radio}.object", isinstance(radio_doc, dict), f"runtime_status.radios.{radio} must be an object"))
                if isinstance(radio_doc, dict):
                    checks.append(Check(f"runtime_status.radios.{radio}.iface", nonempty_text(radio_doc.get("iface")), f"runtime_status.radios.{radio}.iface must be non-empty text"))
                    checks.append(
                        Check(
                            f"runtime_status.radios.{radio}.operstate",
                            normalized_text(radio_doc.get("operstate")) in OPERSTATE_VALUES,
                            f"runtime_status.radios.{radio}.operstate must be a known Linux operstate or missing",
                        )
                    )
                    checks.append(
                        Check(
                            f"runtime_status.radios.{radio}.carrier",
                            normalized_text(radio_doc.get("carrier")) in LINK_CARRIER_VALUES,
                            f"runtime_status.radios.{radio}.carrier must be 0, 1, or unknown",
                        )
                    )
                    modules = radio_doc.get("modules")
                    checks.append(Check(f"runtime_status.radios.{radio}.modules.object", isinstance(modules, dict), f"runtime_status.radios.{radio}.modules must be an object"))
                    if isinstance(modules, dict):
                        required_modules = ("rtl_pci", "rtl8192ee") if radio == "realtek_2g" else ("qdrv", "wlan")
                        for module in required_modules:
                            checks.append(
                                Check(
                                    f"runtime_status.radios.{radio}.modules.{module}",
                                    normalized_text(modules.get(module)) in MODULE_VALUES,
                                    f"runtime_status.radios.{radio}.modules.{module} must be loaded or missing",
                                )
                            )
                    if radio == "realtek_2g":
                        checks.append(
                            Check(
                                "runtime_status.radios.realtek_2g.ap_service",
                                is_service_state(radio_doc.get("ap_service")),
                                "runtime_status.radios.realtek_2g.ap_service must be running, running:<detail>, or stopped",
                            )
                        )
                    else:
                        checks.append(
                            Check(
                                "runtime_status.radios.quantenna_5g.muc_memory_fault_recent",
                                normalized_text(radio_doc.get("muc_memory_fault_recent")) in DMESG_FLAG_VALUES,
                                "runtime_status.radios.quantenna_5g.muc_memory_fault_recent must be seen or not_seen",
                            )
                        )

        clients = runtime_status.get("clients")
        checks.append(Check("runtime_status.clients.object", isinstance(clients, dict), "runtime_status.clients must be an object"))
        if isinstance(clients, dict):
            for iface in REQUIRED_CLIENT_INTERFACES:
                client_doc = clients.get(iface)
                checks.append(Check(f"runtime_status.clients.{iface}.object", isinstance(client_doc, dict), f"runtime_status.clients.{iface} must be an object"))
                if isinstance(client_doc, dict):
                    checks.append(Check(f"runtime_status.clients.{iface}.source", nonempty_text(client_doc.get("source")), f"runtime_status.clients.{iface}.source must be non-empty text"))
                    checks.append(
                        Check(
                            f"runtime_status.clients.{iface}.associated_count",
                            is_client_count(client_doc.get("associated_count")),
                            f"runtime_status.clients.{iface}.associated_count must be a non-negative integer or unknown",
                        )
                    )

        status_bridge = runtime_status.get("bridge")
        checks.append(Check("runtime_status.bridge.object", isinstance(status_bridge, dict), "runtime_status.bridge must be an object"))
        if isinstance(status_bridge, dict):
            checks.append(Check("runtime_status.bridge.iface", status_bridge.get("iface") == "br0", "runtime_status.bridge.iface must be br0"))
            checks.append(
                Check(
                    "runtime_status.bridge.operstate",
                    normalized_text(status_bridge.get("operstate")) in OPERSTATE_VALUES,
                    "runtime_status.bridge.operstate must be a known Linux operstate or missing",
                )
            )
            checks.append(Check("runtime_status.bridge.ipv4.present", isinstance(status_bridge.get("ipv4"), str), "runtime_status.bridge.ipv4 must be present as text"))
            checks.append(
                Check(
                    "runtime_status.bridge.eth0_carrier",
                    normalized_text(status_bridge.get("eth0_carrier")) in LINK_CARRIER_VALUES,
                    "runtime_status.bridge.eth0_carrier must be 0, 1, or unknown",
                )
            )
            checks.append(Check("runtime_status.bridge.irq20", is_irq_counter(status_bridge.get("irq20")), "runtime_status.bridge.irq20 must be a non-negative counter or missing"))
            checks.append(
                Check(
                    "runtime_status.bridge.emac_polling_fallback",
                    normalized_text(status_bridge.get("emac_polling_fallback")) in DMESG_FLAG_VALUES,
                    "runtime_status.bridge.emac_polling_fallback must be seen or not_seen",
                )
            )

        recovery = runtime_status.get("recovery")
        checks.append(Check("runtime_status.recovery.object", isinstance(recovery, dict), "runtime_status.recovery must be an object"))
        if isinstance(recovery, dict):
            checks.append(Check("runtime_status.recovery.route", nonempty_text(recovery.get("route")), "runtime_status.recovery.route must be non-empty text"))
            checks.append(
                Check(
                    "runtime_status.recovery.flash_write_disabled",
                    recovery.get("flash_write_enabled") is False,
                    "runtime_status.recovery.flash_write_enabled must be false",
                )
            )
            checks.append(
                Check(
                    "runtime_status.recovery.no_destructive_actions",
                    recovery.get("destructive_actions_allowed") is False,
                    "runtime_status.recovery.destructive_actions_allowed must be false",
                )
            )
            checks.append(
                Check(
                    "runtime_status.recovery.mtd_entries",
                    parse_nonnegative_int(recovery.get("mtd_entries")) is not None,
                    "runtime_status.recovery.mtd_entries must be a non-negative integer",
                )
                )

    runtime_bridge = doc.get("runtime_bridge")
    checks.append(
        Check(
            "runtime_bridge.object",
            isinstance(runtime_bridge, dict),
            "runtime_bridge must be an object",
        )
    )
    if isinstance(runtime_bridge, dict):
        checks.append(
            Check(
                "runtime_bridge.schema",
                runtime_bridge.get("schema") == EXPECTED_RUNTIME_BRIDGE_SCHEMA,
                f"runtime_bridge.schema must be {EXPECTED_RUNTIME_BRIDGE_SCHEMA}",
            )
        )
        checks.append(
            Check(
                "runtime_bridge.classification",
                runtime_bridge.get("classification") == "READONLY-RUNTIME-BRIDGE-MANAGEMENT-NO-CONTROL",
                "runtime_bridge must be classified as read-only/bridge-management/no-control",
            )
        )
        checks.append(
            Check(
                "runtime_bridge.raw_logs_exposed.false",
                runtime_bridge.get("raw_logs_exposed") is False,
                "runtime_bridge.raw_logs_exposed must be false",
            )
        )
        checks.append(
            Check(
                "runtime_bridge.control_surface_exposed.false",
                runtime_bridge.get("control_surface_exposed") is False,
                "runtime_bridge.control_surface_exposed must be false",
            )
        )
        forbidden_fields = FORBIDDEN_RUNTIME_BRIDGE_FIELDS.intersection(runtime_bridge)
        checks.append(
            Check(
                "runtime_bridge.no_raw_or_control_fields",
                not forbidden_fields,
                "runtime_bridge must not expose raw logs, commands or control fields",
            )
        )
        sources = runtime_bridge.get("sources")
        checks.append(
            Check(
                "runtime_bridge.sources",
                isinstance(sources, list) and bool(sources),
                "runtime_bridge.sources must be a non-empty list",
            )
        )
        if isinstance(sources, list):
            source_set = {str(source) for source in sources}
            for required_source in REQUIRED_RUNTIME_BRIDGE_SOURCES:
                checks.append(
                    Check(
                        f"runtime_bridge.sources.{required_source}",
                        required_source in source_set,
                        f"runtime_bridge.sources must include {required_source}",
                    )
                )

        for section in REQUIRED_RUNTIME_BRIDGE_SECTIONS:
            checks.append(
                Check(
                    f"runtime_bridge.{section}.object",
                    isinstance(runtime_bridge.get(section), dict),
                    f"runtime_bridge.{section} must be an object",
                )
            )

        bridge_doc = runtime_bridge.get("bridge")
        if isinstance(bridge_doc, dict):
            checks.append(Check("runtime_bridge.bridge.iface", bridge_doc.get("iface") == "br0", "runtime_bridge.bridge.iface must be br0"))
            checks.append(
                Check(
                    "runtime_bridge.bridge.operstate",
                    normalized_text(bridge_doc.get("operstate")) in OPERSTATE_VALUES,
                    "runtime_bridge.bridge.operstate must be a known Linux operstate or missing",
                )
            )
            checks.append(Check("runtime_bridge.bridge.ipv4.present", isinstance(bridge_doc.get("ipv4"), str), "runtime_bridge.bridge.ipv4 must be present as text"))
            checks.append(
                Check(
                    "runtime_bridge.bridge.ipv4_present",
                    normalized_text(bridge_doc.get("ipv4_present")) in BRIDGE_SIGNAL_VALUES,
                    "runtime_bridge.bridge.ipv4_present must be seen, not_seen, or unknown",
                )
            )

        uplink_doc = runtime_bridge.get("uplink")
        if isinstance(uplink_doc, dict):
            checks.append(Check("runtime_bridge.uplink.iface", uplink_doc.get("iface") == "eth0", "runtime_bridge.uplink.iface must be eth0"))
            checks.append(
                Check(
                    "runtime_bridge.uplink.operstate",
                    normalized_text(uplink_doc.get("operstate")) in OPERSTATE_VALUES,
                    "runtime_bridge.uplink.operstate must be a known Linux operstate or missing",
                )
            )
            checks.append(
                Check(
                    "runtime_bridge.uplink.carrier",
                    normalized_text(uplink_doc.get("carrier")) in LINK_CARRIER_VALUES,
                    "runtime_bridge.uplink.carrier must be 0, 1, or unknown",
                )
            )
            checks.append(
                Check(
                    "runtime_bridge.uplink.link_observed",
                    normalized_text(uplink_doc.get("link_observed")) in BRIDGE_SIGNAL_VALUES,
                    "runtime_bridge.uplink.link_observed must be seen, not_seen, or unknown",
                )
            )
            checks.append(Check("runtime_bridge.uplink.ipv4.present", isinstance(uplink_doc.get("ipv4"), str), "runtime_bridge.uplink.ipv4 must be present as text"))
            checks.append(
                Check(
                    "runtime_bridge.uplink.ipv4_present",
                    normalized_text(uplink_doc.get("ipv4_present")) in BRIDGE_SIGNAL_VALUES,
                    "runtime_bridge.uplink.ipv4_present must be seen, not_seen, or unknown",
                )
            )

        management_doc = runtime_bridge.get("management")
        if isinstance(management_doc, dict):
            checks.append(Check("runtime_bridge.management.ssh_service", management_doc.get("ssh_service") == "dropbear", "runtime_bridge.management.ssh_service must be dropbear"))
            checks.append(
                Check(
                    "runtime_bridge.management.ssh_state",
                    is_service_state(management_doc.get("ssh_state")),
                    "runtime_bridge.management.ssh_state must be running, running:<detail>, or stopped",
                )
            )
            for field in ("ssh_service_observed", "irq20_present", "emac_polling_fallback"):
                allowed = DMESG_FLAG_VALUES if field == "emac_polling_fallback" else BRIDGE_SIGNAL_VALUES
                checks.append(
                    Check(
                        f"runtime_bridge.management.{field}",
                        normalized_text(management_doc.get(field)) in allowed,
                        f"runtime_bridge.management.{field} must be seen, not_seen, or unknown",
                    )
                )
            checks.append(Check("runtime_bridge.management.irq20", is_irq_counter(management_doc.get("irq20")), "runtime_bridge.management.irq20 must be a non-negative counter or missing"))
            gate = normalized_text(management_doc.get("management_path_gate"))
            proven = management_doc.get("management_path_proven")
            checks.append(
                Check(
                    "runtime_bridge.management.management_path_gate",
                    gate in BRIDGE_GATE_VALUES,
                    "runtime_bridge.management.management_path_gate must be a known bridge gate state",
                )
            )
            checks.append(
                Check(
                    "runtime_bridge.management.management_path_proven.boolean",
                    isinstance(proven, bool),
                    "runtime_bridge.management.management_path_proven must be boolean",
                )
            )
            if proven is True or gate == "proven":
                checks.append(
                    Check(
                        "runtime_bridge.management.proven_requires_eth0_link",
                        get_path(doc, "runtime_bridge.uplink.link_observed") == "seen",
                        "runtime_bridge cannot be proven without eth0 link observed",
                    )
                )
                checks.append(
                    Check(
                        "runtime_bridge.management.proven_requires_br0_ip",
                        get_path(doc, "runtime_bridge.bridge.ipv4_present") == "seen",
                        "runtime_bridge cannot be proven without br0 IPv4",
                    )
                )
                checks.append(
                    Check(
                        "runtime_bridge.management.proven_requires_irq20",
                        management_doc.get("irq20_present") == "seen",
                        "runtime_bridge cannot be proven without IRQ20 present",
                    )
                )
                checks.append(
                    Check(
                        "runtime_bridge.management.proven_requires_ssh",
                        management_doc.get("ssh_service_observed") == "seen",
                        "runtime_bridge cannot be proven without dropbear running",
                    )
                )
                checks.append(
                    Check(
                        "runtime_bridge.management.proven_requires_no_poll_fallback",
                        management_doc.get("emac_polling_fallback") == "not_seen",
                        "runtime_bridge cannot be proven while EMAC polling fallback is observed",
                    )
                )
                checks.append(
                    Check(
                        "runtime_bridge.management.proven_gate_consistent",
                        proven is True and gate == "proven",
                        "runtime_bridge management_path_proven and management_path_gate must agree",
                    )
                )

    runtime_recovery = doc.get("runtime_recovery")
    checks.append(
        Check(
            "runtime_recovery.object",
            isinstance(runtime_recovery, dict),
            "runtime_recovery must be an object",
        )
    )
    if isinstance(runtime_recovery, dict):
        checks.append(
            Check(
                "runtime_recovery.schema",
                runtime_recovery.get("schema") == EXPECTED_RUNTIME_RECOVERY_SCHEMA,
                f"runtime_recovery.schema must be {EXPECTED_RUNTIME_RECOVERY_SCHEMA}",
            )
        )
        checks.append(
            Check(
                "runtime_recovery.classification",
                runtime_recovery.get("classification") == "READONLY-RUNTIME-RECOVERY-GUARDS-NO-CONTROL",
                "runtime_recovery must be classified as read-only/recovery-guards/no-control",
            )
        )
        checks.append(
            Check(
                "runtime_recovery.raw_cmdline_exposed.false",
                runtime_recovery.get("raw_cmdline_exposed") is False,
                "runtime_recovery.raw_cmdline_exposed must be false",
            )
        )
        checks.append(
            Check(
                "runtime_recovery.control_surface_exposed.false",
                runtime_recovery.get("control_surface_exposed") is False,
                "runtime_recovery.control_surface_exposed must be false",
            )
        )
        forbidden_fields = FORBIDDEN_RUNTIME_RECOVERY_FIELDS.intersection(runtime_recovery)
        checks.append(
            Check(
                "runtime_recovery.no_raw_or_control_fields",
                not forbidden_fields,
                "runtime_recovery must not expose raw cmdline/logs, commands or control fields",
            )
        )
        sources = runtime_recovery.get("sources")
        checks.append(
            Check(
                "runtime_recovery.sources",
                isinstance(sources, list) and bool(sources),
                "runtime_recovery.sources must be a non-empty list",
            )
        )
        if isinstance(sources, list):
            source_set = {str(source) for source in sources}
            for required_source in REQUIRED_RUNTIME_RECOVERY_SOURCES:
                checks.append(
                    Check(
                        f"runtime_recovery.sources.{required_source}",
                        required_source in source_set,
                        f"runtime_recovery.sources must include {required_source}",
                    )
                )

        for section in REQUIRED_RUNTIME_RECOVERY_SECTIONS:
            checks.append(
                Check(
                    f"runtime_recovery.{section}.object",
                    isinstance(runtime_recovery.get(section), dict),
                    f"runtime_recovery.{section} must be an object",
                )
            )

        current_boot = runtime_recovery.get("current_boot")
        if isinstance(current_boot, dict):
            checks.append(
                Check(
                    "runtime_recovery.current_boot.classification",
                    normalized_text(current_boot.get("classification")) in BOOT_CLASSIFICATION_VALUES,
                    "runtime_recovery.current_boot.classification must be a known boot classification",
                )
            )
            for field in ("ram_boot_observed", "persistent_boot_observed"):
                checks.append(
                    Check(
                        f"runtime_recovery.current_boot.{field}",
                        normalized_text(current_boot.get(field)) in BRIDGE_SIGNAL_VALUES,
                        f"runtime_recovery.current_boot.{field} must be seen, not_seen, or unknown",
                    )
                )

        recovery_guards = runtime_recovery.get("guards")
        if isinstance(recovery_guards, dict):
            for field in (
                "flash_write_enabled",
                "destructive_actions_allowed",
                "bootenv_write_enabled",
                "network_reconfigure_allowed",
                "module_mutation_allowed",
            ):
                checks.append(
                    Check(
                        f"runtime_recovery.guards.{field}.false",
                        recovery_guards.get(field) is False,
                        f"runtime_recovery.guards.{field} must be false",
                    )
                )

        fallbacks = runtime_recovery.get("fallbacks")
        if isinstance(fallbacks, dict):
            checks.append(
                Check(
                    "runtime_recovery.fallbacks.uart_tftp_oem_route",
                    fallbacks.get("uart_tftp_oem_route") == "externally_gated",
                    "runtime_recovery.fallbacks.uart_tftp_oem_route must be externally_gated",
                )
            )
            checks.append(
                Check(
                    "runtime_recovery.fallbacks.requires_operator_ack",
                    fallbacks.get("requires_operator_ack") is True,
                    "runtime_recovery.fallbacks.requires_operator_ack must be true",
                )
            )
            checks.append(
                Check(
                    "runtime_recovery.fallbacks.device_can_self_recover.false",
                    fallbacks.get("device_can_self_recover") is False,
                    "runtime_recovery.fallbacks.device_can_self_recover must be false",
                )
            )

        mtd = runtime_recovery.get("mtd")
        if isinstance(mtd, dict):
            checks.append(
                Check(
                    "runtime_recovery.mtd.entries",
                    parse_nonnegative_int(mtd.get("entries")) is not None,
                    "runtime_recovery.mtd.entries must be a non-negative integer",
                )
            )
            checks.append(
                Check(
                    "runtime_recovery.mtd.write_target_selected.false",
                    mtd.get("write_target_selected") is False,
                    "runtime_recovery.mtd.write_target_selected must be false",
                )
            )

        recovery_gate = runtime_recovery.get("recovery_gate")
        if isinstance(recovery_gate, dict):
            checks.append(
                Check(
                    "runtime_recovery.recovery_gate.runtime_guards_proven",
                    recovery_gate.get("runtime_guards_proven") is True,
                    "runtime_recovery.recovery_gate.runtime_guards_proven must be true",
                )
            )
            checks.append(
                Check(
                    "runtime_recovery.recovery_gate.hardware_recovery_proven_current_boot.false",
                    recovery_gate.get("hardware_recovery_proven_current_boot") is False,
                    "runtime_recovery must not claim hardware recovery is proven by this runtime endpoint",
                )
            )
            checks.append(
                Check(
                    "runtime_recovery.recovery_gate.next_required_external_gate",
                    recovery_gate.get("next_required_external_gate") == "phase1.current-post-tx7-recovery",
                    "runtime_recovery.recovery_gate.next_required_external_gate must point to post-TX7 recovery",
                )
            )

    runtime_events = doc.get("runtime_events")
    checks.append(
        Check(
            "runtime_events.object",
            isinstance(runtime_events, dict),
            "runtime_events must be an object",
        )
    )
    if isinstance(runtime_events, dict):
        checks.append(
            Check(
                "runtime_events.schema",
                runtime_events.get("schema") == EXPECTED_RUNTIME_EVENTS_SCHEMA,
                f"runtime_events.schema must be {EXPECTED_RUNTIME_EVENTS_SCHEMA}",
            )
        )
        checks.append(
            Check(
                "runtime_events.classification",
                runtime_events.get("classification") == "READONLY-RUNTIME-EVENT-SUMMARY-NO-RAW-LOGS-NO-CONTROL",
                "runtime_events must be classified as read-only/no-raw-logs/no-control",
            )
        )
        checks.append(
            Check(
                "runtime_events.raw_logs_exposed.false",
                runtime_events.get("raw_logs_exposed") is False,
                "runtime_events.raw_logs_exposed must be false",
            )
        )
        sources = runtime_events.get("sources")
        checks.append(
            Check(
                "runtime_events.sources",
                isinstance(sources, list) and bool(sources),
                "runtime_events.sources must be a non-empty list",
            )
        )
        if isinstance(sources, list):
            source_set = {str(source) for source in sources}
            for required_source in REQUIRED_RUNTIME_EVENT_SOURCES:
                checks.append(
                    Check(
                        f"runtime_events.sources.{required_source}",
                        required_source in source_set,
                        f"runtime_events.sources must include {required_source}",
                    )
                )

        events = runtime_events.get("events")
        checks.append(
            Check(
                "runtime_events.events",
                isinstance(events, list) and bool(events),
                "runtime_events.events must be a non-empty list",
            )
        )
        if isinstance(events, list):
            event_ids: set[str] = set()
            for idx, event in enumerate(events):
                prefix = f"runtime_events.events.{idx}"
                checks.append(Check(f"{prefix}.object", isinstance(event, dict), f"{prefix} must be an object"))
                if not isinstance(event, dict):
                    continue
                event_ids.add(str(event.get("id")))
                forbidden_fields = FORBIDDEN_RUNTIME_EVENT_FIELDS.intersection(event)
                checks.append(
                    Check(
                        f"{prefix}.no_raw_log_fields",
                        not forbidden_fields,
                        f"{prefix} must not expose raw log/control fields",
                    )
                )
                checks.append(Check(f"{prefix}.id", nonempty_text(event.get("id")), f"{prefix}.id must be non-empty text"))
                checks.append(Check(f"{prefix}.sector", nonempty_text(event.get("sector")), f"{prefix}.sector must be non-empty text"))
                checks.append(
                    Check(
                        f"{prefix}.severity",
                        normalized_text(event.get("severity")) in EVENT_SEVERITY_VALUES,
                        f"{prefix}.severity must be info, warning, or critical",
                    )
                )
                checks.append(
                    Check(
                        f"{prefix}.state",
                        normalized_text(event.get("state")) in EVENT_STATE_VALUES,
                        f"{prefix}.state must be seen, not_seen, or unknown",
                    )
                )
                checks.append(
                    Check(
                        f"{prefix}.evidence",
                        normalized_text(event.get("evidence")) in EVENT_EVIDENCE_VALUES,
                        f"{prefix}.evidence must be classified_flag_only, runtime_counter_classified, or policy_guard",
                    )
                )
            for required_id in REQUIRED_RUNTIME_EVENT_IDS:
                checks.append(
                    Check(
                        f"runtime_events.required.{required_id}",
                        required_id in event_ids,
                        f"runtime_events.events must include {required_id}",
                    )
                )

    runtime_clients = doc.get("runtime_clients")
    checks.append(
        Check(
            "runtime_clients.object",
            isinstance(runtime_clients, dict),
            "runtime_clients must be an object",
        )
    )
    if isinstance(runtime_clients, dict):
        checks.append(
            Check(
                "runtime_clients.schema",
                runtime_clients.get("schema") == EXPECTED_RUNTIME_CLIENTS_SCHEMA,
                f"runtime_clients.schema must be {EXPECTED_RUNTIME_CLIENTS_SCHEMA}",
            )
        )
        checks.append(
            Check(
                "runtime_clients.classification",
                runtime_clients.get("classification") == "READONLY-RUNTIME-CLIENT-DATA-PATH-NO-CONTROL",
                "runtime_clients must be classified as read-only/client-data-path/no-control",
            )
        )
        checks.append(
            Check(
                "runtime_clients.raw_station_dump_exposed.false",
                runtime_clients.get("raw_station_dump_exposed") is False,
                "runtime_clients.raw_station_dump_exposed must be false",
            )
        )
        checks.append(
            Check(
                "runtime_clients.control_surface_exposed.false",
                runtime_clients.get("control_surface_exposed") is False,
                "runtime_clients.control_surface_exposed must be false",
            )
        )
        sources = runtime_clients.get("sources")
        checks.append(
            Check(
                "runtime_clients.sources",
                isinstance(sources, list) and bool(sources),
                "runtime_clients.sources must be a non-empty list",
            )
        )
        if isinstance(sources, list):
            source_set = {str(source) for source in sources}
            for required_source in REQUIRED_RUNTIME_CLIENT_SOURCES:
                checks.append(
                    Check(
                        f"runtime_clients.sources.{required_source}",
                        required_source in source_set,
                        f"runtime_clients.sources must include {required_source}",
                    )
                )

        interfaces = runtime_clients.get("interfaces")
        checks.append(Check("runtime_clients.interfaces.object", isinstance(interfaces, dict), "runtime_clients.interfaces must be an object"))
        if isinstance(interfaces, dict):
            for iface, expected_radio in EXPECTED_RUNTIME_CLIENT_RADIOS.items():
                client_doc = interfaces.get(iface)
                checks.append(Check(f"runtime_clients.interfaces.{iface}.object", isinstance(client_doc, dict), f"runtime_clients.interfaces.{iface} must be an object"))
                if not isinstance(client_doc, dict):
                    continue
                forbidden_fields = FORBIDDEN_RUNTIME_CLIENT_FIELDS.intersection(client_doc)
                checks.append(
                    Check(
                        f"runtime_clients.interfaces.{iface}.no_raw_or_control_fields",
                        not forbidden_fields,
                        f"runtime_clients.interfaces.{iface} must not expose raw station dumps, MACs, commands or control fields",
                    )
                )
                for field in REQUIRED_RUNTIME_CLIENT_FIELDS:
                    checks.append(
                        Check(
                            f"runtime_clients.interfaces.{iface}.{field}.present",
                            field in client_doc,
                            f"runtime_clients.interfaces.{iface} must expose {field}",
                        )
                    )
                checks.append(
                    Check(
                        f"runtime_clients.interfaces.{iface}.iface",
                        client_doc.get("iface") == iface,
                        f"runtime_clients.interfaces.{iface}.iface must be {iface}",
                    )
                )
                checks.append(
                    Check(
                        f"runtime_clients.interfaces.{iface}.radio",
                        client_doc.get("radio") == expected_radio,
                        f"runtime_clients.interfaces.{iface}.radio must be {expected_radio}",
                    )
                )
                checks.append(
                    Check(
                        f"runtime_clients.interfaces.{iface}.source",
                        normalized_text(client_doc.get("source")) in REQUIRED_RUNTIME_CLIENT_SOURCES,
                        f"runtime_clients.interfaces.{iface}.source must be iw_station_dump_if_available",
                    )
                )
                for field in (
                    "associated_count",
                    "authorized_count",
                    "rx_bytes_total",
                    "tx_bytes_total",
                    "rx_packets_total",
                    "tx_packets_total",
                ):
                    checks.append(
                        Check(
                            f"runtime_clients.interfaces.{iface}.{field}",
                            is_client_count(client_doc.get(field)),
                            f"runtime_clients.interfaces.{iface}.{field} must be a non-negative integer or unknown",
                        )
                    )
                for field in (
                    "authorized_client_present",
                    "bidirectional_traffic_observed",
                    "be_queue_rp_progress",
                ):
                    checks.append(
                        Check(
                            f"runtime_clients.interfaces.{iface}.{field}",
                            normalized_text(client_doc.get(field)) in CLIENT_SIGNAL_VALUES,
                            f"runtime_clients.interfaces.{iface}.{field} must be seen, not_seen, or unknown",
                        )
                    )
                client_data_gate = normalized_text(client_doc.get("client_data_gate"))
                checks.append(
                    Check(
                        f"runtime_clients.interfaces.{iface}.client_data_gate",
                        client_data_gate in CLIENT_GATE_VALUES,
                        f"runtime_clients.interfaces.{iface}.client_data_gate must be a known client gate state",
                    )
                )
                data_path_proven = client_doc.get("data_path_proven")
                checks.append(
                    Check(
                        f"runtime_clients.interfaces.{iface}.data_path_proven.boolean",
                        isinstance(data_path_proven, bool),
                        f"runtime_clients.interfaces.{iface}.data_path_proven must be boolean",
                    )
                )
                if data_path_proven is True or client_data_gate == "proven":
                    checks.append(
                        Check(
                            f"runtime_clients.interfaces.{iface}.proven_requires_authorized",
                            client_doc.get("authorized_client_present") == "seen",
                            f"runtime_clients.interfaces.{iface} cannot be proven without an authorized client",
                        )
                    )
                    checks.append(
                        Check(
                            f"runtime_clients.interfaces.{iface}.proven_requires_bidirectional_traffic",
                            client_doc.get("bidirectional_traffic_observed") == "seen",
                            f"runtime_clients.interfaces.{iface} cannot be proven without bidirectional traffic",
                        )
                    )
                    checks.append(
                        Check(
                            f"runtime_clients.interfaces.{iface}.proven_requires_be_queue",
                            client_doc.get("be_queue_rp_progress") == "seen",
                            f"runtime_clients.interfaces.{iface} cannot be proven without BE queue RP progress",
                        )
                    )
                    checks.append(
                        Check(
                            f"runtime_clients.interfaces.{iface}.proven_gate_consistent",
                            data_path_proven is True and client_data_gate == "proven",
                            f"runtime_clients.interfaces.{iface} data_path_proven and client_data_gate must agree",
                        )
                    )

    runtime_towers = doc.get("runtime_towers")
    checks.append(
        Check(
            "runtime_towers.object",
            isinstance(runtime_towers, dict),
            "runtime_towers must be an object",
        )
    )
    if isinstance(runtime_towers, dict):
        checks.append(
            Check(
                "runtime_towers.schema",
                runtime_towers.get("schema") == EXPECTED_RUNTIME_TOWERS_SCHEMA,
                f"runtime_towers.schema must be {EXPECTED_RUNTIME_TOWERS_SCHEMA}",
            )
        )
        checks.append(
            Check(
                "runtime_towers.classification",
                runtime_towers.get("classification") == "READONLY-RUNTIME-SERVICE-TOWERS-NO-CONTROL",
                "runtime_towers must be classified as read-only/no-control",
            )
        )
        checks.append(
            Check(
                "runtime_towers.control_surface_exposed.false",
                runtime_towers.get("control_surface_exposed") is False,
                "runtime_towers.control_surface_exposed must be false",
            )
        )
        sources = runtime_towers.get("sources")
        checks.append(
            Check(
                "runtime_towers.sources",
                isinstance(sources, list) and bool(sources),
                "runtime_towers.sources must be a non-empty list",
            )
        )
        if isinstance(sources, list):
            source_set = {str(source) for source in sources}
            for required_source in REQUIRED_RUNTIME_TOWER_SOURCES:
                checks.append(
                    Check(
                        f"runtime_towers.sources.{required_source}",
                        required_source in source_set,
                        f"runtime_towers.sources must include {required_source}",
                    )
                )

        towers_doc = runtime_towers.get("towers")
        checks.append(Check("runtime_towers.towers.object", isinstance(towers_doc, dict), "runtime_towers.towers must be an object"))
        if isinstance(towers_doc, dict):
            for tower, expected_service in EXPECTED_TOWER_SERVICES.items():
                tower_doc = towers_doc.get(tower)
                checks.append(Check(f"runtime_towers.towers.{tower}.object", isinstance(tower_doc, dict), f"runtime_towers.towers.{tower} must be an object"))
                if not isinstance(tower_doc, dict):
                    continue
                for field in REQUIRED_RUNTIME_TOWER_FIELDS:
                    checks.append(
                        Check(
                            f"runtime_towers.towers.{tower}.{field}.present",
                            field in tower_doc,
                            f"runtime_towers.towers.{tower} must expose {field}",
                        )
                    )
                checks.append(
                    Check(
                        f"runtime_towers.towers.{tower}.service",
                        tower_doc.get("service") == expected_service,
                        f"runtime_towers.towers.{tower}.service must be {expected_service}",
                    )
                )
                checks.append(
                    Check(
                        f"runtime_towers.towers.{tower}.process",
                        tower_doc.get("process") == expected_service,
                        f"runtime_towers.towers.{tower}.process must be {expected_service}",
                    )
                )
                checks.append(
                    Check(
                        f"runtime_towers.towers.{tower}.state",
                        is_service_state(tower_doc.get("state")),
                        f"runtime_towers.towers.{tower}.state must be running, running:<detail>, or stopped",
                    )
                )
                checks.append(
                    Check(
                        f"runtime_towers.towers.{tower}.evidence",
                        normalized_text(tower_doc.get("evidence")) in TOWER_EVIDENCE_VALUES,
                        f"runtime_towers.towers.{tower}.evidence must be pidof",
                    )
                )
                checks.append(
                    Check(
                        f"runtime_towers.towers.{tower}.control_disabled",
                        tower_doc.get("control_enabled") is False,
                        f"runtime_towers.towers.{tower}.control_enabled must be false",
                    )
                )
                checks.append(
                    Check(
                        f"runtime_towers.towers.{tower}.writes_disabled",
                        tower_doc.get("writes_device") is False,
                        f"runtime_towers.towers.{tower}.writes_device must be false",
                    )
                )

    sectors = doc.get("sectors")
    checks.append(Check("sectors.object", isinstance(sectors, dict), "sectors must be an object"))
    if isinstance(sectors, dict):
        for sector in REQUIRED_SECTORS:
            checks.append(Check(f"sectors.{sector}.present", sector in sectors, f"sector {sector} must be present"))
            sector_doc = sectors.get(sector)
            checks.append(
                Check(
                    f"sectors.{sector}.object",
                    isinstance(sector_doc, dict),
                    f"sector {sector} must be an object",
                )
            )
            if isinstance(sector_doc, dict):
                for field in REQUIRED_SECTOR_FIELDS[sector]:
                    checks.append(
                        Check(
                            f"sectors.{sector}.{field}.present",
                            field in sector_doc,
                            f"sector {sector} must expose {field}",
                        )
                    )
                checks.append(
                    Check(
                        f"sectors.{sector}.label",
                        nonempty_text(sector_doc.get("label")),
                        f"sector {sector} label must be non-empty text",
                    )
                )
                checks.append(
                    Check(
                        f"sectors.{sector}.state",
                        nonempty_text(sector_doc.get("state")),
                        f"sector {sector} state must be non-empty text",
                    )
                )

        if isinstance(sectors.get("core"), dict):
            checks.append(
                Check(
                    "sectors.core.state.visible",
                    sectors["core"].get("state") == "visible",
                    "core sector state must be visible",
                )
            )
        if isinstance(sectors.get("bridge"), dict):
            bridge = sectors["bridge"]
            checks.append(
                Check(
                    "sectors.bridge.state.operstate",
                    normalized_text(bridge.get("state")) in OPERSTATE_VALUES,
                    "bridge state must be a known Linux operstate or missing",
                )
            )
            checks.append(
                Check(
                    "sectors.bridge.eth0_carrier.value",
                    normalized_text(bridge.get("eth0_carrier")) in LINK_CARRIER_VALUES,
                    "bridge eth0_carrier must be 0, 1, or unknown",
                )
            )
            checks.append(
                Check(
                    "sectors.bridge.br0_state.operstate",
                    normalized_text(bridge.get("br0_state")) in OPERSTATE_VALUES,
                    "bridge br0_state must be a known Linux operstate or missing",
                )
            )
            checks.append(
                Check(
                    "sectors.bridge.irq20.counter",
                    is_irq_counter(bridge.get("irq20")),
                    "bridge irq20 must be a non-negative counter or missing",
                )
            )
            checks.append(
                Check(
                    "sectors.bridge.emac_polling_fallback.flag",
                    normalized_text(bridge.get("emac_polling_fallback")) in DMESG_FLAG_VALUES,
                    "bridge emac_polling_fallback must be seen or not_seen",
                )
            )
        if isinstance(sectors.get("realtek"), dict):
            realtek = sectors["realtek"]
            checks.append(
                Check(
                    "sectors.realtek.state.operstate",
                    normalized_text(realtek.get("state")) in OPERSTATE_VALUES,
                    "realtek state must be a known Linux operstate or missing",
                )
            )
            for field in ("rtl_pci", "rtl8192ee"):
                checks.append(
                    Check(
                        f"sectors.realtek.{field}.module_state",
                        normalized_text(realtek.get(field)) in MODULE_VALUES,
                        f"realtek {field} must be loaded or missing",
                    )
                )
            checks.append(
                Check(
                    "sectors.realtek.hostapd.service_state",
                    is_service_state(realtek.get("hostapd")),
                    "realtek hostapd must be running, running:<detail>, or stopped",
                )
            )
        if isinstance(sectors.get("quantenna"), dict):
            quantenna = sectors["quantenna"]
            checks.append(
                Check(
                    "sectors.quantenna.state.operstate",
                    normalized_text(quantenna.get("state")) in OPERSTATE_VALUES,
                    "quantenna state must be a known Linux operstate or missing",
                )
            )
            for field in ("qdrv", "wlan"):
                checks.append(
                    Check(
                        f"sectors.quantenna.{field}.module_state",
                        normalized_text(quantenna.get(field)) in MODULE_VALUES,
                        f"quantenna {field} must be loaded or missing",
                    )
                )
            checks.append(
                Check(
                    "sectors.quantenna.muc_memory_fault_recent.flag",
                    normalized_text(quantenna.get("muc_memory_fault_recent")) in DMESG_FLAG_VALUES,
                    "quantenna muc_memory_fault_recent must be seen or not_seen",
                )
            )
        if isinstance(sectors.get("memory"), dict):
            checks.append(
                Check(
                    "sectors.memory.state.read_only",
                    sectors["memory"].get("state") == "read-only",
                    "memory sector state must stay read-only",
                )
            )

    towers = doc.get("towers")
    checks.append(Check("towers.object", isinstance(towers, dict), "towers must be an object"))
    if isinstance(towers, dict):
        for tower in REQUIRED_TOWERS:
            checks.append(Check(f"towers.{tower}.present", tower in towers, f"tower {tower} must be present"))
            tower_doc = towers.get(tower)
            checks.append(
                Check(
                    f"towers.{tower}.object",
                    isinstance(tower_doc, dict),
                    f"tower {tower} must be an object",
                )
            )
            if isinstance(tower_doc, dict):
                for field in ("label", "service", "state"):
                    checks.append(
                        Check(
                            f"towers.{tower}.{field}.present",
                            field in tower_doc,
                            f"tower {tower} must expose {field}",
                        )
                    )
                checks.append(
                    Check(
                        f"towers.{tower}.label",
                        nonempty_text(tower_doc.get("label")),
                        f"tower {tower} label must be non-empty text",
                    )
                )
                checks.append(
                    Check(
                        f"towers.{tower}.service",
                        tower_doc.get("service") == EXPECTED_TOWER_SERVICES[tower],
                        f"tower {tower} service must be {EXPECTED_TOWER_SERVICES[tower]}",
                    )
                )
                checks.append(
                    Check(
                        f"towers.{tower}.state",
                        is_service_state(tower_doc.get("state")),
                        f"tower {tower} state must be running, running:<detail>, or stopped",
                    )
                )

    mission_data = doc.get("mission_data")
    checks.append(
        Check(
            "mission_data.object",
            isinstance(mission_data, dict),
            "mission_data must be an object",
        )
    )
    if isinstance(mission_data, dict):
        checks.append(
            Check(
                "mission_data.classification",
                mission_data.get("classification") == "STATIC-READONLY-SNAPSHOT-NO-HARDWARE-PROOF",
                "mission_data must be marked as a read-only static snapshot, not hardware proof",
            )
        )
        for item in REQUIRED_MISSION_DATA:
            value = mission_data.get(item)
            checks.append(
                Check(
                    f"mission_data.{item}.present",
                    isinstance(value, dict) and "present" in value and "bytes" in value,
                    f"mission_data.{item} must expose present/bytes",
                )
            )
            if isinstance(value, dict):
                checks.append(
                    Check(
                        f"mission_data.{item}.mounted",
                        value.get("present") is True,
                        f"mission_data.{item} must be present in the mounted static snapshot",
                    )
                )
                checks.append(
                    Check(
                        f"mission_data.{item}.bytes",
                        isinstance(value.get("bytes"), int) and value.get("bytes", 0) > 0,
                        f"mission_data.{item} must have non-zero bytes in the mounted static snapshot",
                    )
                )

    guards = doc.get("guards")
    checks.append(Check("guards.object", isinstance(guards, dict), "guards must be an object"))
    if isinstance(guards, dict):
        for guard in REQUIRED_GUARDS_FALSE:
            checks.append(
                Check(
                    f"guards.{guard}.false",
                    guards.get(guard) is False,
                    f"guard {guard} must be false",
                )
            )

    flash_write_enabled = get_path(doc, "sectors.memory.flash_write_enabled")
    checks.append(
        Check(
            "memory.flash_write_disabled",
            flash_write_enabled is False,
            "sectors.memory.flash_write_enabled must be false",
        )
    )

    bridge_state = str(get_path(doc, "sectors.bridge.state") or "")
    bridge_carrier = str(get_path(doc, "sectors.bridge.eth0_carrier") or "")
    if require_bridge_up:
        checks.append(
            Check(
                "bridge.up",
                bridge_state == "up" or bridge_carrier == "1",
                f"bridge must be up or carrier=1, got state={bridge_state!r} carrier={bridge_carrier!r}",
            )
        )

    if require_ssh_running:
        ssh_state = str(get_path(doc, "towers.ssh.state") or "")
        checks.append(
            Check(
                "tower.ssh.running",
                ssh_state == "running" or ssh_state.startswith("running:"),
                f"SSH tower must be running, got {ssh_state!r}",
            )
        )

    if require_management_path:
        management_doc = get_path(doc, "runtime_bridge.management")
        checks.append(
            Check(
                "management_path.required_object",
                isinstance(management_doc, dict),
                "strict management gate requires runtime_bridge.management",
            )
        )
        if isinstance(management_doc, dict):
            checks.append(
                Check(
                    "management_path.eth0_link",
                    get_path(doc, "runtime_bridge.uplink.link_observed") == "seen",
                    "strict management gate requires eth0 carrier observed",
                )
            )
            checks.append(
                Check(
                    "management_path.br0_ip",
                    get_path(doc, "runtime_bridge.bridge.ipv4_present") == "seen",
                    "strict management gate requires br0 IPv4",
                )
            )
            checks.append(
                Check(
                    "management_path.irq20",
                    management_doc.get("irq20_present") == "seen",
                    "strict management gate requires IRQ20 present",
                )
            )
            checks.append(
                Check(
                    "management_path.ssh",
                    management_doc.get("ssh_service_observed") == "seen",
                    "strict management gate requires dropbear running",
                )
            )
            checks.append(
                Check(
                    "management_path.no_polling_fallback",
                    management_doc.get("emac_polling_fallback") == "not_seen",
                    "strict management gate rejects observed EMAC polling fallback",
                )
            )
            checks.append(
                Check(
                    "management_path.proven",
                    management_doc.get("management_path_proven") is True
                    and management_doc.get("management_path_gate") == "proven",
                    "strict management gate requires management_path_proven=true and management_path_gate=proven",
                )
            )

    if require_recovery_guards:
        recovery_doc = doc.get("runtime_recovery")
        checks.append(
            Check(
                "recovery_guards.required_object",
                isinstance(recovery_doc, dict),
                "strict recovery guard requires runtime_recovery",
            )
        )
        if isinstance(recovery_doc, dict):
            checks.append(
                Check(
                    "recovery_guards.no_control_surface",
                    recovery_doc.get("control_surface_exposed") is False,
                    "strict recovery guard requires no control surface",
                )
            )
            checks.append(
                Check(
                    "recovery_guards.no_raw_cmdline",
                    recovery_doc.get("raw_cmdline_exposed") is False,
                    "strict recovery guard requires no raw cmdline exposure",
                )
            )
            for path, check_id in (
                ("runtime_recovery.guards.flash_write_enabled", "recovery_guards.flash_write_disabled"),
                ("runtime_recovery.guards.destructive_actions_allowed", "recovery_guards.no_destructive_actions"),
                ("runtime_recovery.guards.bootenv_write_enabled", "recovery_guards.bootenv_write_disabled"),
                ("runtime_recovery.guards.network_reconfigure_allowed", "recovery_guards.no_network_reconfigure"),
                ("runtime_recovery.guards.module_mutation_allowed", "recovery_guards.no_module_mutation"),
                ("runtime_recovery.mtd.write_target_selected", "recovery_guards.no_mtd_write_target"),
                ("runtime_recovery.fallbacks.device_can_self_recover", "recovery_guards.no_self_recover_claim"),
                ("runtime_recovery.recovery_gate.hardware_recovery_proven_current_boot", "recovery_guards.no_hardware_recovery_claim"),
            ):
                checks.append(
                    Check(
                        check_id,
                        get_path(doc, path) is False,
                        f"strict recovery guard requires {path}=false",
                    )
                )
            checks.append(
                Check(
                    "recovery_guards.operator_ack_required",
                    get_path(doc, "runtime_recovery.fallbacks.requires_operator_ack") is True,
                    "strict recovery guard requires operator ACK for external recovery",
                )
            )
            checks.append(
                Check(
                    "recovery_guards.runtime_guards_proven",
                    get_path(doc, "runtime_recovery.recovery_gate.runtime_guards_proven") is True,
                    "strict recovery guard requires runtime_guards_proven=true",
                )
            )

    if require_realtek_client_data_path:
        realtek_client = get_path(doc, "runtime_clients.interfaces.wlan0")
        checks.append(
            Check(
                "realtek.client_data_path.required_object",
                isinstance(realtek_client, dict),
                "strict Realtek client/data gate requires runtime_clients.interfaces.wlan0",
            )
        )
        if isinstance(realtek_client, dict):
            checks.append(
                Check(
                    "realtek.client_data_path.authorized",
                    realtek_client.get("authorized_client_present") == "seen",
                    "strict Realtek client/data gate requires an authorized client",
                )
            )
            checks.append(
                Check(
                    "realtek.client_data_path.bidirectional_traffic",
                    realtek_client.get("bidirectional_traffic_observed") == "seen",
                    "strict Realtek client/data gate requires bidirectional traffic",
                )
            )
            checks.append(
                Check(
                    "realtek.client_data_path.be_queue_rp",
                    realtek_client.get("be_queue_rp_progress") == "seen",
                    "strict Realtek client/data gate requires BE queue RP progress",
                )
            )
            checks.append(
                Check(
                    "realtek.client_data_path.proven",
                    realtek_client.get("data_path_proven") is True
                    and realtek_client.get("client_data_gate") == "proven",
                    "strict Realtek client/data gate requires data_path_proven=true and client_data_gate=proven",
                )
            )

    return checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Read-only live verifier for Router-Lyoko /api/lyoko."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--url", default=DEFAULT_URL, help=f"Endpoint to fetch (default: {DEFAULT_URL})")
    source.add_argument("--input-json", help="Validate a captured /api/lyoko JSON file.")
    source.add_argument("--stdin", action="store_true", help="Validate JSON from stdin.")
    parser.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout in seconds.")
    parser.add_argument("--max-bytes", type=int, default=128 * 1024, help="Maximum response bytes.")
    parser.add_argument("--require-kernel-510", action="store_true", help="Require system.kernel to contain 5.10.")
    parser.add_argument("--require-bridge-up", action="store_true", help="Require bridge state up or eth0 carrier=1.")
    parser.add_argument("--require-ssh-running", action="store_true", help="Require SSH tower to be running.")
    parser.add_argument("--require-management-path", action="store_true", help="Require eth0 link, br0 IPv4, IRQ20 and dropbear via runtime_bridge.")
    parser.add_argument("--require-recovery-guards", action="store_true", help="Require runtime recovery guards to be read-only, external-gated and no-flash.")
    parser.add_argument("--require-realtek-client-data-path", action="store_true", help="Require authorized 2.4 GHz client, bidirectional traffic and BE queue RP progress.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        doc, source = load_payload(args)
        checks = validate(
            doc,
            require_kernel_510=args.require_kernel_510,
            require_bridge_up=args.require_bridge_up,
            require_ssh_running=args.require_ssh_running,
            require_management_path=args.require_management_path,
            require_recovery_guards=args.require_recovery_guards,
            require_realtek_client_data_path=args.require_realtek_client_data_path,
        )
        ok = all(check.ok for check in checks)
        report = {
            "ok": ok,
            "classification": "READONLY-LIVE-VERIFY-NO-CONTROL",
            "source": source,
            "checks": [asdict(check) for check in checks],
        }
    except (OSError, urllib.error.URLError, json.JSONDecodeError, RuntimeError) as exc:
        report = {
            "ok": False,
            "classification": "READONLY-LIVE-VERIFY-NO-CONTROL",
            "error": str(exc),
        }
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
