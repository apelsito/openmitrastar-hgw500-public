#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OVERLAY = ROOT / "work" / "mission-state" / "router-lyoko-v0"

RECOVERED_BOOT_STATES = {
    "TX7_RAM_RECOVERED_2G_CLIENT_GATE_ACTIVE",
    "TX7_RAM_RECOVERED_2G_NO_CLIENT_SOAK_COMPLETE",
    "TX11_RAM_BOOTED_2G_AP_ENABLED_AUTH_ASSOC_BLOCKED",
    "TX13_RAM_BOOTED_2G_AP_ENABLED_AUTH_TX_NO_ASSOC_REQ",
}


@dataclass(frozen=True)
class CoverageFinding:
    kind: str
    surface: str
    detail: str


@dataclass(frozen=True)
class Surface:
    id: str
    requirement: str
    html_ids: tuple[str, ...] = ()
    js_tokens: tuple[str, ...] = ()
    files: tuple[str, ...] = ()
    bindings: tuple[str, ...] = ()
    truth_gates: tuple[str, ...] = ()
    forbidden_gate_statuses: tuple[str, ...] = ()


SURFACES: tuple[Surface, ...] = (
    Surface(
        id="router.kernel_linux510",
        requirement="Linux 5.10 visible as the Lyoko core without claiming full completion.",
        html_ids=("kernel",),
        js_tokens=("system?.kernel",),
        truth_gates=("phase1.kernel-linux510",),
    ),
    Surface(
        id="router.ethernet_ssh_recovery",
        requirement="Ethernet, SSH and post-TX7 recovery are represented as runtime-gated, not assumed stable.",
        html_ids=("runtime-bridge", "runtime-recovery", "reentry-checkpoint"),
        js_tokens=("renderRuntimeBridge", "renderRuntimeRecovery", "management_path_proven", "PHYSICAL_POWER_CYCLE_REQUIRED"),
        files=("rootfs/var/www/lyoko-data/safe-mode.json", "rootfs/var/www/lyoko-data/AELITA_REENTRY_CHECKPOINT_20260822.md"),
        bindings=("live.runtime_bridge", "live.runtime_recovery", "static.reentry"),
        truth_gates=("phase1.current-post-tx7-recovery", "phase1.bridge-ethernet-ssh"),
    ),
    Surface(
        id="router.realtek_2g",
        requirement="2.4 GHz Realtek AP/client/data path exists as a strict client/data gate.",
        html_ids=("runtime-clients", "sectors"),
        js_tokens=("renderRuntimeClients", "authorized_client_present", "be_queue_rp_progress", "client_data_gate"),
        files=("rootfs/var/www/lyoko-data/REALTEK_TX_TAXONOMY.md",),
        bindings=("live.runtime_clients",),
        truth_gates=("phase2.realtek-2g-complete",),
        forbidden_gate_statuses=("PROVEN",),
    ),
    Surface(
        id="router.quantenna_5g",
        requirement="5 GHz Quantenna is visible as a damaged/blocked sector until the MuC/TQE fault is retested.",
        html_ids=("runtime-events", "event-taxonomy", "sectors"),
        js_tokens=("quantenna", "Misaligned Access", "xana.quantenna.misaligned_access"),
        files=("rootfs/var/www/lyoko-data/event-taxonomy.json",),
        bindings=("live.runtime_events",),
        truth_gates=("phase2.quantenna-5g",),
        forbidden_gate_statuses=("PROVEN",),
    ),
    Surface(
        id="router.persistence_flash",
        requirement="Flash/persistence is represented only as blocked/partial until slot, rollback and readback gates pass.",
        html_ids=("aelita-memory-contract", "runtime-recovery"),
        js_tokens=("writes_device_now", "flash_write_enabled", "write_target_selected"),
        files=("rootfs/var/www/lyoko-data/aelita-memory.json", "rootfs/var/www/lyoko-data/safe-mode.json"),
        bindings=("static.aelita_memory", "live.runtime_recovery"),
        truth_gates=("phase2.lab-persistence",),
        forbidden_gate_statuses=("PROVEN",),
    ),
    Surface(
        id="lyoko.visual_dashboard",
        requirement="Visual Router-Lyoko dashboard with sectors, cards and styling.",
        html_ids=("sectors", "sector-map", "towers", "telemetry-pulse"),
        js_tokens=("function render(", "card("),
        files=("rootfs/var/www/lyoko.html", "rootfs/var/www/lyoko.css", "rootfs/var/www/lyoko.js"),
    ),
    Surface(
        id="lyoko.telemetry_api",
        requirement="Local observe-only API and runtime telemetry contract.",
        html_ids=("runtime-status", "telemetry-contract"),
        js_tokens=('fetch("/api/lyoko"', 'fetch("/api/lyoko-control"', "AUTO_REFRESH_SECONDS"),
        files=("rootfs/var/www/api/lyoko", "rootfs/var/www/api/lyoko-control", "rootfs/var/www/lyoko-data/telemetry-contract.json"),
        bindings=("live.runtime_status", "live.system", "live.sectors"),
    ),
    Surface(
        id="lyoko.towers_services",
        requirement="Towers map to observable real services without executing control.",
        html_ids=("runtime-towers", "towers"),
        js_tokens=("renderRuntimeTowers", "control_enabled", "writes_device"),
        bindings=("live.runtime_towers",),
    ),
    Surface(
        id="lyoko.missions_history",
        requirement="Mission history and latest mission memory are rendered from versioned static data.",
        html_ids=("mission-history", "mission-memory", "mission-gates"),
        js_tokens=("renderMissionHistory", "renderMissionMemory", "aelita-mission-log.jsonl", "LATEST_MISSION.md"),
        files=("rootfs/var/www/lyoko-data/aelita-mission-log.jsonl", "rootfs/var/www/lyoko-data/LATEST_MISSION.md"),
    ),
    Surface(
        id="lyoko.aelita_persona_memory",
        requirement="Aelita memory/dialogue is staged, evidence-bound and incapable of claiming hardware from static data.",
        html_ids=("aelita-alerts", "aelita-dialogue", "aelita-memory-contract"),
        js_tokens=("renderAelitaAlerts", "renderAelitaDialogue", "renderAelitaMemoryContract"),
        files=("rootfs/var/www/lyoko-data/aelita-memory.json", "rootfs/var/www/lyoko-data/aelita-dialogue.json"),
        bindings=("static.aelita_memory",),
    ),
    Surface(
        id="lyoko.safe_mode_control_policy",
        requirement="Safe mode and control policy are observe-only/fail-closed.",
        html_ids=("control-policy", "guards", "runtime-recovery"),
        js_tokens=("renderControlPolicy", "renderControlContract", "control_enabled"),
        files=("rootfs/var/www/lyoko-data/control-policy.json", "rootfs/var/www/lyoko-data/safe-mode.json"),
        bindings=("static.control_policy", "live.runtime_recovery"),
    ),
    Surface(
        id="lyoko.xana_alerts",
        requirement="Aelita/XANA alerts are derived from audit/runtime evidence without raw logs.",
        html_ids=("aelita-alerts", "runtime-events", "event-taxonomy"),
        js_tokens=("renderAelitaAlerts", "activeXanaEvents", "raw_logs_exposed"),
        files=("rootfs/var/www/lyoko-data/event-taxonomy.json", "rootfs/var/www/lyoko-data/goal-audit.json"),
        bindings=("live.runtime_events", "static.goal_audit"),
    ),
)


def rel_path(raw: str) -> Path:
    rel = Path(*raw.split("/"))
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError(f"unsafe relative path: {raw}")
    return rel


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def add(findings: list[CoverageFinding], kind: str, surface: str, detail: str) -> None:
    findings.append(CoverageFinding(kind=kind, surface=surface, detail=detail))


def file_text(overlay: Path, rel: str) -> str:
    return (overlay / rel_path(rel)).read_text(encoding="utf-8", errors="replace")


def verify_surface(surface: Surface, overlay: Path, html: str, js: str, manifest_files: set[str], binding_ids: set[str], gate_status: dict[str, str], findings: list[CoverageFinding]) -> None:
    for html_id in surface.html_ids:
        if f'id="{html_id}"' not in html:
            add(findings, "missing_html_surface", surface.id, f"missing id={html_id}")
    for token in surface.js_tokens:
        if token not in js:
            add(findings, "missing_js_binding", surface.id, f"missing token {token}")
    for rel in surface.files:
        if rel not in manifest_files:
            add(findings, "missing_manifest_file", surface.id, f"{rel} is not in manifest.json")
        if not (overlay / rel_path(rel)).is_file():
            add(findings, "missing_overlay_file", surface.id, f"{rel} is missing")
    for binding in surface.bindings:
        if binding not in binding_ids:
            add(findings, "missing_evidence_binding", surface.id, f"{binding} is not present in evidence-bindings.json")
    for gate in surface.truth_gates:
        status = gate_status.get(gate)
        if status is None:
            add(findings, "missing_truth_gate", surface.id, f"{gate} is missing from mission-truth.json")
        elif status in surface.forbidden_gate_statuses:
            add(findings, "hardware_overclaim", surface.id, f"{gate} is {status} but this surface still requires live proof")


def verify_non_overclaim(goal_audit: dict[str, Any], truth: dict[str, Any], findings: list[CoverageFinding]) -> None:
    summary = goal_audit.get("summary") or {}
    boot_state = summary.get("boot_state")
    recovered_readonly = (
        boot_state in RECOVERED_BOOT_STATES
        and summary.get("hardware_blocked") is False
    )
    if goal_audit.get("achieved") is not False:
        add(findings, "goal_overclaim", "objective", "goal-audit.json must not mark achieved=true before hardware gates")
    if goal_audit.get("status") not in {"BLOCKED", "PENDING", "PARTIAL"}:
        add(findings, "goal_status_overclaim", "objective", "goal status must not imply completion")
    if summary.get("hardware_blocked") is not True and not recovered_readonly:
        add(findings, "hardware_block_missing", "objective", "hardware_blocked must remain true while post-TX7 recovery is unresolved")
    allowed_next_gates = (
        {"phase1.bridge-ethernet-ssh", "phase2.realtek-2g-complete"}
        if recovered_readonly
        else {"phase1.current-post-tx7-recovery"}
    )
    if summary.get("next_gate") not in allowed_next_gates:
        add(findings, "wrong_next_gate", "objective", "next gate must remain post-TX7 recovery")

    truth_summary = truth.get("summary") or {}
    if truth_summary.get("next_gate") not in allowed_next_gates:
        add(findings, "truth_next_gate_drift", "objective", "mission truth next gate must remain post-TX7 recovery")


def build_report(overlay: Path) -> dict[str, Any]:
    overlay = overlay.resolve()
    findings: list[CoverageFinding] = []

    html_path = overlay / "rootfs" / "var" / "www" / "lyoko.html"
    js_path = overlay / "rootfs" / "var" / "www" / "lyoko.js"
    manifest_path = overlay / "manifest.json"
    bindings_path = overlay / "rootfs" / "var" / "www" / "lyoko-data" / "evidence-bindings.json"
    truth_path = overlay / "rootfs" / "var" / "www" / "lyoko-data" / "mission-truth.json"
    audit_path = overlay / "rootfs" / "var" / "www" / "lyoko-data" / "goal-audit.json"

    try:
        html = html_path.read_text(encoding="utf-8", errors="replace")
        js = js_path.read_text(encoding="utf-8", errors="replace")
        manifest = load_json(manifest_path)
        bindings_doc = load_json(bindings_path)
        truth = load_json(truth_path)
        goal_audit = load_json(audit_path)
    except Exception as exc:  # noqa: BLE001 - convert into machine-readable failure
        return {
            "schema": "router-lyoko.objective-coverage/v1",
            "classification": "READONLY-OBJECTIVE-COVERAGE-NO-HARDWARE",
            "ok": False,
            "overlay": str(overlay),
            "error": str(exc),
            "findings_count": 1,
            "findings": [
                {
                    "kind": "load_failure",
                    "surface": "objective",
                    "detail": str(exc),
                }
            ],
        }

    manifest_files = set((manifest.get("files") or {}).keys())
    binding_ids = {binding.get("id") for binding in bindings_doc.get("bindings") or []}
    gate_status = {gate.get("id"): gate.get("status") for gate in truth.get("gates") or []}

    for surface in SURFACES:
        verify_surface(surface, overlay, html, js, manifest_files, binding_ids, gate_status, findings)
    verify_non_overclaim(goal_audit, truth, findings)

    surfaces = [
        {
            "id": surface.id,
            "requirement": surface.requirement,
            "truth_gates": list(surface.truth_gates),
            "bindings": list(surface.bindings),
        }
        for surface in SURFACES
    ]
    return {
        "schema": "router-lyoko.objective-coverage/v1",
        "classification": "READONLY-OBJECTIVE-COVERAGE-NO-HARDWARE",
        "ok": not findings,
        "overlay": str(overlay),
        "surfaces_checked": len(SURFACES),
        "surfaces": surfaces,
        "completion_state": {
            "achieved": goal_audit.get("achieved"),
            "status": goal_audit.get("status"),
            "next_gate": (goal_audit.get("summary") or {}).get("next_gate"),
            "hardware_blocked": (goal_audit.get("summary") or {}).get("hardware_blocked"),
            "boot_state": (goal_audit.get("summary") or {}).get("boot_state"),
            "current_access": (goal_audit.get("summary") or {}).get("current_access"),
        },
        "findings_count": len(findings),
        "findings": [asdict(finding) for finding in findings],
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify Router-Lyoko overlay covers the stated router+Lyoko objective without hardware overclaims."
    )
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY)
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    report = build_report(args.overlay)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
