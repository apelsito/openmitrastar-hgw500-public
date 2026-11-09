#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, asdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MISSION = ROOT / "work" / "mission-state"
LYOKO = MISSION / "router-lyoko-v0"


STATUS_ORDER = {
    "PROVEN": 0,
    "BLOCKED": 1,
    "PARTIAL": 2,
    "READY": 3,
    "PENDING": 4,
    "FORBIDDEN": 5,
    "UNKNOWN": 6,
}

RECOVERED_BOOT_STATES = (
    r"TX7_RAM_RECOVERED_2G_CLIENT_GATE_ACTIVE",
    r"TX7_RAM_RECOVERED_2G_NO_CLIENT_SOAK_COMPLETE",
    r"TX11_RAM_BOOTED_2G_AP_ENABLED_AUTH_ASSOC_BLOCKED",
    r"TX13_RAM_BOOTED_2G_AP_ENABLED_AUTH_TX_NO_ASSOC_REQ",
    r"TX17_RAM_BOOTED_2G_AP_ENABLED_NO_CLIENT_RX0",
)


@dataclass(frozen=True)
class Evidence:
    path: str
    claim: str
    status: str


@dataclass(frozen=True)
class Gate:
    id: str
    phase: str
    sector: str
    requirement: str
    status: str
    evidence: list[Evidence]
    next_discriminant: str


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT)).replace("\\", "/")


def read(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(encoding="utf-8", errors="ignore")


def evidence(path: Path, claim: str, status: str) -> Evidence:
    return Evidence(path=rel(path), claim=claim, status=status)


def has(text: str, *patterns: str) -> bool:
    return all(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns)


def any_has(text: str, *patterns: str) -> bool:
    return any(re.search(pattern, text, re.IGNORECASE | re.MULTILINE) for pattern in patterns)


def build_gates() -> list[Gate]:
    ledger_path = MISSION / "EVIDENCE_LEDGER.md"
    hardware_state_path = MISSION / "HARDWARE_STATE.json"
    post_tx7_recovery_path = MISSION / "POST_TX7_5G_HANG_RECOVERY_RUNBOOK_20260822.md"
    post_tx7_recovery_tool = ROOT / "tools" / "verify_post_tx7_recovery.ps1"
    post_tx7_recovery_result_verifier = ROOT / "tools" / "verify_post_tx7_recovery_result.py"
    post_tx7_recovery_result_test = ROOT / "tools" / "test_post_tx7_recovery_result_verifier.py"
    resume_post_tx7_tool = ROOT / "tools" / "resume_post_tx7_5g_hang.ps1"
    resume_post_tx7_result_verifier = ROOT / "tools" / "verify_resume_post_tx7_result.py"
    resume_post_tx7_result_test = ROOT / "tools" / "test_resume_post_tx7_result_verifier.py"
    post_tx7_offline_preflight = ROOT / "tools" / "preflight_post_tx7_resume_offline.py"
    post_tx7_offline_preflight_test = ROOT / "tools" / "test_preflight_post_tx7_resume_offline.py"
    w3_tx7_fault_path = MISSION / "W3_TX7_5G_FAULT_20260822.md"
    w1_path = MISSION / "W1_EMAC_DUAL_PHY_AUTONEG_20260821.md"
    tx3_bridge_path = ROOT / "outputs" / "uart-live" / "w2-tx3-live-bridge-ssh-20260822.json"
    tx7_soak_path = ROOT / "outputs" / "uart-live" / "w2-tx7-autoreconnect-soak-20260822.log.json"
    tx7_gate_result_path = ROOT / "outputs" / "uart-live" / "w2-tx7-autoreconnect-soak-20260822.gate-result.json"
    w2_tx2_path = MISSION / "W2_REALTEK_TX2_CHECKPOINT_20260821.md"
    tx7_manifest_path = (
        ROOT
        / "work"
        / "mission-state"
        / "w2-2g-parity-tx7-hybrid32-v1"
        / "build"
        / "manifest.json"
    )
    tx10_controls_checkpoint_path = (
        ROOT / "work" / "mission-state" / "w2-2g-parity-tx10-controls-v1" / "CHECKPOINT.md"
    )
    tx10_controls_manifest_path = (
        ROOT
        / "work"
        / "mission-state"
        / "w2-2g-parity-tx10-controls-v1"
        / "build"
        / "manifest.json"
    )
    tx11_controls_checkpoint_path = (
        ROOT / "work" / "mission-state" / "w2-2g-parity-tx11-green-boot-controls-v1" / "CHECKPOINT.md"
    )
    tx11_controls_manifest_path = (
        ROOT
        / "work"
        / "mission-state"
        / "w2-2g-parity-tx11-green-boot-controls-v1"
        / "build"
        / "manifest.json"
    )
    tx3_manifest_path = (
        ROOT
        / "work"
        / "mission-state"
        / "w2-2g-parity-tx3-aelita-v1"
        / "build"
        / "manifest.json"
    )
    tx3_preassoc_path = ROOT / "outputs" / "uart-live" / "w2-2g-tx3-client-gate-preassoc-20260822.json"
    tx3_preassoc_result_path = (
        ROOT / "outputs" / "uart-live" / "w2-2g-tx3-client-gate-preassoc-20260822.result.json"
    )
    tx2_beacon_fail_path = LYOKO / "REALTEK_TX2_BEACON_FAIL.md"
    realtek_tx_taxonomy_path = LYOKO / "REALTEK_TX_TAXONOMY.md"
    w2_checkpoint_path = MISSION / "w2-2g-parity-v1" / "CHECKPOINT.md"
    w2_matrix_path = MISSION / "w2-2g-parity-v1" / "PARITY_MATRIX.md"
    lyoko_validation_path = LYOKO / "VALIDATION.md"
    lyoko_integrator = ROOT / "tools" / "integrate_router_lyoko_overlay.py"
    lyoko_static_sync = ROOT / "tools" / "sync_router_lyoko_static_data.py"
    lyoko_static_data_test = ROOT / "tools" / "test_router_lyoko_static_data.py"
    lyoko_packager = ROOT / "tools" / "package_router_lyoko_overlay.py"
    lyoko_packager_test = ROOT / "tools" / "test_package_router_lyoko_overlay.py"
    lyoko_integrator_test = ROOT / "tools" / "test_router_lyoko_integrator.py"
    lyoko_no_secrets_verifier = ROOT / "tools" / "verify_router_lyoko_no_secrets.py"
    lyoko_no_secrets_test = ROOT / "tools" / "test_router_lyoko_no_secrets.py"
    lyoko_aelita_memory_guard = ROOT / "tools" / "verify_router_lyoko_aelita_memory.py"
    lyoko_aelita_memory_guard_test = ROOT / "tools" / "test_router_lyoko_aelita_memory.py"
    lyoko_objective_coverage_guard = ROOT / "tools" / "verify_router_lyoko_objective_coverage.py"
    lyoko_objective_coverage_guard_test = ROOT / "tools" / "test_router_lyoko_objective_coverage.py"
    lyoko_live_verifier = ROOT / "tools" / "verify_router_lyoko_live.py"
    lyoko_live_verifier_test = ROOT / "tools" / "test_router_lyoko_live_verifier.py"
    lyoko_static_index_verifier = ROOT / "tools" / "verify_router_lyoko_static_index.py"
    lyoko_served_files_verifier = ROOT / "tools" / "verify_router_lyoko_served_files.py"
    lyoko_served_no_secrets_verifier = ROOT / "tools" / "verify_router_lyoko_served_no_secrets.py"
    lyoko_served_no_secrets_test = ROOT / "tools" / "test_router_lyoko_served_no_secrets_verifier.py"
    lyoko_reentry_result_verifier = ROOT / "tools" / "verify_router_lyoko_reentry_result.py"
    lyoko_reentry_gate = ROOT / "tools" / "verify_router_lyoko_reentry.ps1"
    lyoko_reentry_fixture_test = ROOT / "tools" / "test_router_lyoko_reentry_execution_fixture.py"
    lyoko_reentry_result_test = ROOT / "tools" / "test_router_lyoko_reentry_result_verifier.py"
    lyoko_control_api = LYOKO / "rootfs" / "var" / "www" / "api" / "lyoko-control"
    lyoko_aelita_memory_path = LYOKO / "memory" / "aelita-memory.json"
    lyoko_evidence_bindings_path = LYOKO / "evidence-bindings.json"
    lyoko_telemetry_contract_path = LYOKO / "telemetry-contract.json"
    lyoko_telemetry_contract_guard = ROOT / "tools" / "validate_router_lyoko_telemetry_contract.py"
    lyoko_telemetry_contract_guard_test = ROOT / "tools" / "test_router_lyoko_telemetry_contract.py"
    lyoko_aelita_dialogue_path = LYOKO / "memory" / "aelita-dialogue.json"
    lyoko_event_taxonomy_path = LYOKO / "event-taxonomy.json"
    lyoko_control_policy_path = LYOKO / "control" / "control-policy.json"
    lyoko_control_validator = ROOT / "tools" / "validate_router_lyoko_control_policy.py"

    ledger = read(ledger_path)
    hardware_state = read(hardware_state_path)
    post_tx7_recovery = read(post_tx7_recovery_path)
    post_tx7_recovery_tool_text = read(post_tx7_recovery_tool)
    post_tx7_recovery_result_verifier_text = read(post_tx7_recovery_result_verifier)
    post_tx7_recovery_result_test_text = read(post_tx7_recovery_result_test)
    resume_post_tx7_tool_text = read(resume_post_tx7_tool)
    resume_post_tx7_result_verifier_text = read(resume_post_tx7_result_verifier)
    resume_post_tx7_result_test_text = read(resume_post_tx7_result_test)
    post_tx7_offline_preflight_text = read(post_tx7_offline_preflight)
    post_tx7_offline_preflight_test_text = read(post_tx7_offline_preflight_test)
    w3_tx7_fault = read(w3_tx7_fault_path)
    w1 = read(w1_path)
    tx3_bridge = read(tx3_bridge_path)
    tx7_soak = read(tx7_soak_path)
    tx7_gate_result = read(tx7_gate_result_path)
    w2_tx2 = read(w2_tx2_path)
    tx7_manifest = read(tx7_manifest_path)
    tx10_controls_checkpoint = read(tx10_controls_checkpoint_path)
    tx10_controls_manifest = read(tx10_controls_manifest_path)
    tx11_controls_checkpoint = read(tx11_controls_checkpoint_path)
    tx11_controls_manifest = read(tx11_controls_manifest_path)
    tx3_manifest = read(tx3_manifest_path)
    tx3_preassoc = read(tx3_preassoc_path)
    tx3_preassoc_result = read(tx3_preassoc_result_path)
    tx2_beacon_fail = read(tx2_beacon_fail_path)
    realtek_tx_taxonomy = read(realtek_tx_taxonomy_path)
    w2_checkpoint = read(w2_checkpoint_path)
    w2_matrix = read(w2_matrix_path)
    lyoko_validation = read(lyoko_validation_path)
    lyoko_static_sync_text = read(lyoko_static_sync)
    lyoko_static_data_test_text = read(lyoko_static_data_test)
    lyoko_packager_text = read(lyoko_packager)
    lyoko_packager_test_text = read(lyoko_packager_test)
    lyoko_integrator_text = read(lyoko_integrator)
    lyoko_integrator_test_text = read(lyoko_integrator_test)
    lyoko_no_secrets_verifier_text = read(lyoko_no_secrets_verifier)
    lyoko_no_secrets_test_text = read(lyoko_no_secrets_test)
    lyoko_aelita_memory_guard_text = read(lyoko_aelita_memory_guard)
    lyoko_aelita_memory_guard_test_text = read(lyoko_aelita_memory_guard_test)
    lyoko_objective_coverage_guard_text = read(lyoko_objective_coverage_guard)
    lyoko_objective_coverage_guard_test_text = read(lyoko_objective_coverage_guard_test)
    lyoko_live_verifier_text = read(lyoko_live_verifier)
    lyoko_live_verifier_test_text = read(lyoko_live_verifier_test)
    lyoko_static_index_verifier_text = read(lyoko_static_index_verifier)
    lyoko_served_files_verifier_text = read(lyoko_served_files_verifier)
    lyoko_served_no_secrets_verifier_text = read(lyoko_served_no_secrets_verifier)
    lyoko_served_no_secrets_test_text = read(lyoko_served_no_secrets_test)
    lyoko_reentry_result_verifier_text = read(lyoko_reentry_result_verifier)
    lyoko_reentry_fixture_test_text = read(lyoko_reentry_fixture_test)
    lyoko_reentry_result_test_text = read(lyoko_reentry_result_test)
    lyoko_control_api_text = read(lyoko_control_api)
    aelita_memory_text = read(lyoko_aelita_memory_path)
    evidence_bindings_text = read(lyoko_evidence_bindings_path)
    telemetry_contract_text = read(lyoko_telemetry_contract_path)
    telemetry_contract_guard_text = read(lyoko_telemetry_contract_guard)
    telemetry_contract_guard_test_text = read(lyoko_telemetry_contract_guard_test)
    aelita_dialogue_text = read(lyoko_aelita_dialogue_path)
    event_taxonomy_text = read(lyoko_event_taxonomy_path)
    control_policy_text = read(lyoko_control_policy_path)
    lyoko_reentry_gate_text = read(lyoko_reentry_gate)

    gates: list[Gate] = []
    current_tx7_hang = has(
        hardware_state,
        r"TX7_POST_5G_MISALIGNED_ACCESS_HUNG_WAITING_PHYSICAL_POWER_CYCLE",
        r"NETWORK_UNREACHABLE_UART_SILENT_SYSRQ_FAILED_PHYSICAL_POWER_CYCLE_REQUIRED",
    )
    current_tx7_recovered = has(
        hardware_state,
        r"UART_LIVE_SSH_ICMP_HTTP_ETH0_1G",
        r"PHYSICAL_POWER_CYCLE_PASS_TX7_RECOVERED_READONLY_VERIFIED",
        r"latest_recovery_evidence",
    ) and any_has(hardware_state, *RECOVERED_BOOT_STATES)

    linux_proven = has(ledger, r"Linux 5\.10", r"RAM BOOT PASS|PERSISTENT COLD BOOT PASS")
    gates.append(
        Gate(
            id="phase1.kernel-linux510",
            phase="Fase 1 - Mantener vivo el superordenador",
            sector="Sector Núcleo",
            requirement="Linux 5.10 arranca de forma verificable en el HGW-500BNA-QCv2.",
            status="PROVEN" if linux_proven else "PENDING",
            evidence=[
                evidence(
                    ledger_path,
                    "El ledger contiene boots Linux 5.10 RAM y persistentes con artefactos de UART/SSH.",
                    "PROVEN" if linux_proven else "PENDING",
                )
            ],
            next_discriminant=(
                "Mantener esta prueba ligada al hash exacto de cada nueva imagen RAM."
                if linux_proven
                else "Arrancar una imagen Linux 5.10 exacta y capturar UART plus SSH."
            ),
        )
    )

    recovery_proven = has(ledger, r"UART", r"TFTP|YMODEM", r"OEM|recovery|rollback")
    gates.append(
        Gate(
            id="phase1.recovery-path",
            phase="Fase 1 - Mantener vivo el superordenador",
            sector="Sector Memoria",
            requirement="UART/TFTP/OEM siguen siendo ruta de desvirtualización antes de cualquier flash.",
            status="PROVEN" if recovery_proven else "PENDING",
            evidence=[
                evidence(
                    ledger_path,
                    "El ledger conserva evidencias de Bootbase/UART/TFTP/YMODEM y recuperación Q2/OEM.",
                    "PROVEN" if recovery_proven else "PENDING",
                )
            ],
            next_discriminant="No promover ninguna imagen a flash sin readback, slot inactivo y rollback probado.",
        )
    )

    recovery_gate_ready = (
        post_tx7_recovery_tool.is_file()
        and has(
            post_tx7_recovery_tool_text,
            r"OPENMITRASTAR_POST_TX7_RECOVERY_READONLY",
            r"OMPOSTTX7_RECOVERY_PASS=1",
            r"verify_post_tx7_recovery_result\.py",
            r"result_verifier_ok",
            r"\$PingExit -eq 0",
        )
    )
    recovery_result_verifier_ready = (
        post_tx7_recovery_result_verifier.is_file()
        and has(
            post_tx7_recovery_result_verifier_text,
            r"openmitrastar\.post-tx7-recovery-result/v1",
            r"READONLY-POST-TX7-RECOVERY-RESULT-VERIFY-NO-CONTROL",
            r"pass\.matches_evidence",
            r"ssh_marker\.matches_stdout",
            r"kernel_ok\.matches_stdout",
            r"fatal_found\.matches_stdout",
            r"under_output_dir",
            r"no_secrets",
            r"Findings never include the secret value",
        )
    )
    recovery_result_test_ready = (
        post_tx7_recovery_result_test.is_file()
        and has(
            post_tx7_recovery_result_test_text,
            r"test_accepts_coherent_recovery_pass",
            r"test_rejects_forged_pass_when_ping_failed",
            r"test_rejects_kernel_flag_mismatch",
            r"test_rejects_fatal_marker_forged_as_clean",
            r"test_rejects_mutation_flag_enabled",
            r"test_rejects_evidence_path_escape",
            r"test_rejects_secret_bearing_stdout_without_echoing_secret",
        )
    )
    resume_post_tx7_ready = (
        resume_post_tx7_tool.is_file()
        and has(
            resume_post_tx7_tool_text,
            r"OPENMITRASTAR_RESUME_AFTER_TX7_HANG_READONLY",
            r"verify_post_tx7_recovery\.ps1",
            r"verify_router_lyoko_reentry\.ps1",
            r"verify_resume_post_tx7_result\.py",
            r"resume-result\.json",
            r"result_verifier_ok",
            r"recovery_result_json",
            r"collect_w2_tx11_boot_evidence\.ps1",
            r"run_w2_2g_tx11_gate\.ps1",
        )
    )
    resume_post_tx7_result_ready = (
        resume_post_tx7_result_verifier.is_file()
        and has(
            resume_post_tx7_result_verifier_text,
            r"openmitrastar\.resume-post-tx7-5g-hang-result/v1",
            r"READONLY-RESUME-POST-TX7-RESULT-VERIFY-NO-CONTROL",
            r"openmitrastar\.post-tx7-recovery-result/v1",
            r"router-lyoko\.reentry-live-api-result/v1",
            r"OMTX11_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1",
            r"OM2G_TX11_GATE_PLAN_PASS=1",
            r"pass\.matches_children",
            r"under_output_dir",
            r"no_secrets",
            r"Findings never include the secret value",
        )
    )
    resume_post_tx7_result_test_ready = (
        resume_post_tx7_result_test.is_file()
        and has(
            resume_post_tx7_result_test_text,
            r"test_accepts_coherent_resume_without_lyoko_reentry",
            r"test_accepts_coherent_resume_with_required_lyoko_reentry",
            r"test_rejects_forged_pass_when_recovery_child_failed",
            r"test_rejects_missing_tx11_boot_plan_marker",
            r"test_rejects_missing_tx11_2g_plan_marker",
            r"test_rejects_mutation_flag_enabled",
            r"test_rejects_evidence_path_escape",
            r"test_rejects_secret_bearing_top_level_stdout_without_echoing_secret",
        )
    )
    post_tx7_offline_preflight_ready = (
        post_tx7_offline_preflight.is_file()
        and has(
            post_tx7_offline_preflight_text,
            r"openmitrastar\.post-tx7-offline-preflight/v1",
            r"READONLY-OFFLINE-PREFLIGHT-NO-HARDWARE",
            r"OMPOSTTX7_OFFLINE_PREFLIGHT_PASS=1",
            r"OMPOSTTX7_RECOVERY_PLAN_PASS=1",
            r"OMPOSTTX7_RESUME_PLAN_PASS=1",
            r"OMLYOKO_REENTRY_PLAN_PASS=1",
            r"OMTX11_BOOT_EVIDENCE_COLLECTION_PLAN_PASS=1",
            r"OM2G_TX11_GATE_PLAN_PASS=1",
            r"lyoko_reentry\.requires_recovery_guards",
            r"lyoko_package\.sha256\.expected",
        )
        and post_tx7_offline_preflight_test.is_file()
        and has(
            post_tx7_offline_preflight_test_text,
            r"test_preflight_passes_offline_without_hardware",
            r"test_preflight_rejects_wrong_expected_package_hash",
            r"test_tx7_gate_has_get_file_hash_fallback",
            r"test_preflight_source_contains_no_hardware_execution_flags",
        )
    )
    gates.append(
        Gate(
            id="phase1.current-post-tx7-recovery",
            phase="Fase 1 - Mantener vivo el superordenador",
            sector="Sector Puente",
            requirement="Tras el fault TX7/5G, recuperar gestión por Ethernet/SSH con evidencia fresca antes de cualquier nueva prueba de radio.",
            status="PROVEN" if current_tx7_recovered else "BLOCKED" if current_tx7_hang else "PENDING",
            evidence=[
                evidence(
                    hardware_state_path,
                    "El estado actual declara recovery TX7 read-only verificado con UART/SSH/ICMP/HTTP/eth0 1G."
                    if current_tx7_recovered
                    else "El estado actual declara red inalcanzable, UART silencioso tras SysRq y power-cycle físico requerido.",
                    "PROVEN" if current_tx7_recovered else "BLOCKED" if current_tx7_hang else "PENDING",
                ),
                evidence(
                    post_tx7_recovery_path,
                    "El runbook fija una única acción física y una prueba read-only posterior.",
                    "READY" if post_tx7_recovery_path.is_file() else "PENDING",
                ),
                evidence(
                    post_tx7_recovery_tool,
                    "El verificador post-power-cycle existe, arranca en plan-only, requiere ACK explícito para ping/SSH read-only y autovalida recovery-result.json.",
                    "READY" if recovery_gate_ready else "PENDING",
                ),
                evidence(
                    post_tx7_recovery_result_verifier,
                    "El verificador de resultado post-TX7 compara recovery-result.json contra ping, stdout SSH, marcadores, kernel, eth0, patrones fatales, rutas bajo output_dir, mutaciones falsas y secretos concretos sin imprimir valores.",
                    "READY" if recovery_result_verifier_ready else "PENDING",
                ),
                evidence(
                    post_tx7_recovery_result_test,
                    "Tests del verificador post-TX7 cubren PASS coherente, ping fallido forjado, kernel falso, fatal marker, mutación, path escape y stdout con secreto sin eco del valor.",
                    "READY" if recovery_result_test_ready else "PENDING",
                ),
                evidence(
                    resume_post_tx7_tool,
                    "El wrapper de resume post-TX7 encadena recovery, reentry Lyoko opcional y planes TX11 de boot evidence + gate 2.4 con resultado top-level autoconsistente; el PASS publica el recovery_result_json que debe preceder el RAM boot exacto TX11.",
                    "READY" if resume_post_tx7_ready else "PENDING",
                ),
                evidence(
                    resume_post_tx7_result_verifier,
                    "El verificador de resultado resume comprueba recovery child result, reentry child result opcional, marcadores de planes TX11, rutas bajo output_dir, mutaciones falsas y secretos concretos en stdout/stderr top-level sin imprimir valores.",
                    "READY" if resume_post_tx7_result_ready else "PENDING",
                ),
                evidence(
                    resume_post_tx7_result_test,
                    "Tests del resultado resume cubren PASS con/sin reentry Lyoko, recovery child fallido, marcadores TX11 ausentes, mutación, path escape y stdout top-level con secreto sin eco del valor.",
                    "READY" if resume_post_tx7_result_test_ready else "PENDING",
                ),
                evidence(
                    post_tx7_offline_preflight,
                    "El preflight offline valida estado post-TX7, planes plan-only/ACK-gated, paquete Router-Lyoko exacto, runtime_recovery guards, guard anti-secretos del recovery/resume, guard Aelita memory y planes TX11 antes de pedir acción física.",
                    "READY" if post_tx7_offline_preflight_ready else "PENDING",
                ),
                evidence(
                    post_tx7_offline_preflight_test,
                    "Tests del preflight cubren PASS offline, rechazo por hash Lyoko incorrecto, fallback SHA-256 sin Get-FileHash y ausencia de flags de ejecución hardware.",
                    "READY" if post_tx7_offline_preflight_ready else "PENDING",
                ),
            ],
            next_discriminant=(
                "Continuar con TX11-green-boot-controls: boot evidence exacta, LED verde liberado, LED 2.4 activo, cliente AUTHORIZED, DHCP, BE RP progress y tráfico."
                if current_tx7_recovered
                else "Power-cycle físico controlado; después ejecutar verify_post_tx7_recovery.ps1 con ACK y exigir OMPOSTTX7_RECOVERY_PASS=1."
            ),
        )
    )

    emac_offline = has(w1, r"dual-PHY", r"RAM-only artifact", r"Hardware status: \*\*PENDING RAM BOOT\*\*")
    emac_boot_proven = has(ledger, r"management failure", r"PHY/MAC mode") and not emac_offline
    tx3_bridge_live = has(
        tx3_bridge,
        r'"classification":\s*"RAM-ONLY-TX3-LIVE-BRIDGE-SSH-NO-FLASH"',
        r'"ssh_authenticated":\s*true',
        r'"eth0_carrier":\s*true',
        r'"bridge_up":\s*true',
        r'"eth0"',
        r'"wlan0"',
        r'"no_kernel_oops":\s*true',
    )
    gates.append(
        Gate(
            id="phase1.bridge-ethernet-ssh",
            phase="Fase 1 - Mantener vivo el superordenador",
            sector="Sector Puente",
            requirement="Ethernet y SSH permanecen estables en la imagen exacta que vamos a usar.",
            status="BLOCKED" if current_tx7_hang else "PARTIAL" if tx3_bridge_live else "PENDING" if emac_offline and not emac_boot_proven else "PROVEN" if emac_boot_proven else "UNKNOWN",
            evidence=[
                evidence(
                    hardware_state_path,
                    "En el checkpoint actual la gestión está recuperada por UART/SSH/ICMP/HTTP/eth0 1G; falta soak largo con cliente."
                    if current_tx7_recovered
                    else "En el checkpoint actual la gestión está inalcanzable tras el fault 5 GHz; la estabilidad Ethernet/SSH debe reprobarse tras power-cycle.",
                    "PARTIAL" if current_tx7_recovered else "BLOCKED" if current_tx7_hang else "UNKNOWN",
                ),
                evidence(
                    w1_path,
                    "W1 EMAC dual-PHY está construido y testeado offline, pero declara RAM boot pendiente.",
                    "PENDING" if emac_offline else "UNKNOWN",
                ),
                evidence(
                    tx3_bridge_path,
                    "TX3 RAM actual tiene SSH autenticado, eth0 carrier, br0 con eth0+wlan0, IRQ20/IRQ28 vivos y sin Oops; falta soak largo con cliente.",
                    "PARTIAL" if tx3_bridge_live else "PENDING",
                ),
                evidence(
                    ledger_path,
                    "El ledger identifica el bloqueo anterior como modo PHY/MAC heredado, no excepción kernel.",
                    "PROVEN",
                ),
            ],
            next_discriminant=(
                "Recuperar primero el equipo con el verificador post-TX7; luego repetir SSH/bridge soak en la imagen exacta viva."
                if current_tx7_hang
                else
                "Mantener SSH vivo durante asociación física, DHCP, tráfico y soak de 600 s."
                if tx3_bridge_live
                else "Arrancar la imagen EMAC dual por RAM y exigir RX packets, IRQ seleccionado y SSH vivo."
            ),
        )
    )

    no_flash_guard = has(w1, r"candidate_eligible false", r"flash_supported false") and has(
        w2_tx2, r"RAM-ONLY-NO-FLASH"
    )
    gates.append(
        Gate(
            id="phase1.no-destructive-writes",
            phase="Fase 1 - Mantener vivo el superordenador",
            sector="Sector Memoria",
            requirement="Sin escrituras destructivas mientras Ethernet/2.4 no estén cerrados.",
            status="PROVEN" if no_flash_guard else "PENDING",
            evidence=[
                evidence(w1_path, "El artefacto EMAC dual declara candidate_eligible=false y flash_supported=false.", "PROVEN" if no_flash_guard else "PENDING"),
                evidence(w2_tx2_path, "TX2 está clasificado RAM-ONLY-NO-FLASH.", "PROVEN" if "RAM-ONLY-NO-FLASH" in w2_tx2 else "PENDING"),
            ],
            next_discriminant="Mantener cualquier carga como RAM-only hasta que haya gate completo de rollback.",
        )
    )

    realtek_client_proven = has(ledger, r"Real 2\.4 GHz clients associate", r"PROVEN CLIENT/BRIDGE/INTERNET")
    realtek_tx2_beacon_failed = has(tx2_beacon_fail, r"TX2 is not a pass", r"SSID is invisible")
    tx3_ready_offline = has(
        tx3_manifest,
        r'"classification":\s*"RAM-ONLY-W2-2G-PARITY-TX3-NO-FLASH"',
        r'"candidate_eligible":\s*false',
        r'"profile":\s*"W2_2G_TX3_DATA_COMPACT_OPEN_DIAG"',
        r'"txbd_compact32_data_queues_only":\s*true',
        r'"txbd_preserved_64_queues":\s*\[[^\]]*"BEACON"[^\]]*"MGNT"[^\]]*\]',
        r'"bootbase_contract":\s*"PASS"',
        r'"fits":\s*true',
    )
    realtek_perf_pending = has(w2_tx2, r"Hardware throughput: PENDING") or has(
        w2_matrix, r"Performance", r"PENDING"
    ) or realtek_tx2_beacon_failed
    tx3_live_preassoc = has(
        tx3_preassoc,
        r'"classification":\s*"RAM-ONLY-TX3-PREASSOCIATION-NO-FLASH"',
        r'"associated":\s*false',
        r'"bridge_eth0_wlan0":\s*true',
        r'"irq28_progress":\s*true',
        r'"hostapd_stable":\s*true',
    )
    tx3_client_gate_fail_preassoc = has(
        tx3_preassoc_result,
        r'"status":\s*"FAIL"',
        r'"associated"',
        r'"download_mbps"',
    )
    tx7_ready_offline = has(
        tx7_manifest,
        r'"classification":\s*"RAM-ONLY-W2-2G-PARITY-TX7-HYBRID32-NO-FLASH"',
        r'"profile":\s*"W2_2G_TX7_HYBRID32_BIT15_0_OPEN_DIAG"',
        r'"txbd_compact32_data_queues_only":\s*true',
        r'"bootbase_contract":\s*"PASS"',
        r'"fits":\s*true',
    )
    tx10_controls_ready_offline = has(
        tx10_controls_manifest,
        r'"classification":\s*"RAM-ONLY-W2-2G-PARITY-TX10-CONTROLS-NO-FLASH"',
        r'"profile":\s*"W2_2G_TX10_RX_SIGNAL_SAFE_CONTROLS_OPEN_DIAG"',
        r'"button_daemon":\s*"/usr/sbin/om-buttond"',
        r'"txbd_compact32_global":\s*true',
        r'"bootbase_contract":\s*"PASS"',
        r'"fits":\s*true',
    ) and has(
        tx10_controls_checkpoint,
        r"50 passed",
        r"audit_w2_tx10_candidate\.py`: `PASS`",
        r"GPIO7 \+ GPIO9: lower orange",
    )
    tx11_controls_ready_offline = has(
        tx11_controls_manifest,
        r'"classification":\s*"RAM-ONLY-W2-2G-PARITY-TX11-GREEN-BOOT-CONTROLS-NO-FLASH"',
        r'"profile":\s*"W2_2G_TX11_GREEN_BOOT_CONTROLS_OPEN_DIAG"',
        r'"bootbase_contract":\s*"PASS"',
        r'"fits":\s*true',
    ) and has(
        tx11_controls_checkpoint,
        r"TX11-green-boot-controls",
        r"GPIO9",
        r"green",
        r"12 passed",
    )
    tx7_platform_soak = has(
        tx7_soak,
        r'"complete":\s*true',
        r'"ap_enabled_all_samples":\s*true',
        r'"ssh_alive_all_samples":\s*true',
        r'"fatal_markers_during_run":\s*0',
        r'"association_observed":\s*false',
    )
    tx7_no_client_gate = has(
        tx7_gate_result,
        r'"status":\s*"NO_CLIENT"',
        r'"pass":\s*false',
        r'"association_missing"',
    )
    realtek_next = (
        "Tras recuperar gestión, RAM-boot/validar TX11-green-boot-controls exacto, recolectar boot evidence read-only, ejecutar run_w2_2g_tx11_gate.ps1 con esa evidencia y asociar un cliente físico a OpenMitraStar-2G-DIAG; exigir LED verde liberado, LED 2.4 activo, AUTHORIZED, BE RP progress y tráfico bidireccional antes de Speedtest."
        if current_tx7_hang
        else "TX11-green-boot-controls es el siguiente experimento exacto: RAM boot, boot evidence, LED verde de arranque liberado por userspace, LED 2.4 activo al emitir SSID, cliente iPhone AUTHORIZED, DHCP/HTTPS, BE RP progress y sólo entonces Speedtest."
        if tx11_controls_ready_offline
        else "TX10-controls es el siguiente experimento exacto: RAM boot, boot evidence, cliente iPhone AUTHORIZED, DHCP/HTTPS, BE RP progress y sólo entonces Speedtest."
        if tx10_controls_ready_offline
        else "TX7 está listo como siguiente experimento: asociar iPhone, exigir AUTHORIZED/DHCP/BE RP progress y sólo entonces un Speedtest."
        if tx7_ready_offline
        else "Arrancar TX7 por RAM limpio: confirmar visibilidad SSID, asociación, BE queue/IRQ/retries y sólo entonces un Speedtest."
    )
    gates.append(
        Gate(
            id="phase2.realtek-2g-complete",
            phase="Fase 2 - Materializar los sectores",
            sector="Sector Realtek",
            requirement="2.4 GHz completo: AP visible, cliente autorizado, tráfico real, throughput útil, LED y botón.",
            status="BLOCKED" if current_tx7_hang else "PARTIAL" if (realtek_client_proven and realtek_perf_pending) or tx7_platform_soak or tx3_live_preassoc else "PENDING",
            evidence=[
                evidence(
                    tx7_manifest_path,
                    "TX7 combina datos 32, beacon/gestión 64 y bit15=0 como candidato RAM-only exacto.",
                    "READY" if tx7_ready_offline else "PENDING",
                ),
                evidence(
                    tx10_controls_manifest_path,
                    "TX10-controls combina RX signal-safe, TXBD global 32, LED 2.4 post-hostapd y daemon GPIO2 long-press en un candidato RAM-only exacto.",
                    "READY" if tx10_controls_ready_offline else "PENDING",
                ),
                evidence(
                    tx10_controls_checkpoint_path,
                    "TX10-controls está validado offline con 50 tests, auditoría PASS, checksums OK, Bootbase PASS y mapa físico rojo/verde/naranja documentado.",
                    "READY" if tx10_controls_ready_offline else "PENDING",
                ),
                evidence(
                    tx11_controls_manifest_path,
                    "TX11-green-boot-controls mueve el LED de arranque a GPIO9 verde, conserva GPIO7 como signalR rojo diagnóstico y mantiene 2.4 GHz/controles como RAM-only exacto.",
                    "READY" if tx11_controls_ready_offline else "PENDING",
                ),
                evidence(
                    tx11_controls_checkpoint_path,
                    "TX11 sellado está validado offline con gates 2.4/parity, Bootbase PASS, DTB GPIO9/GPIO7 y sin hardware/flash.",
                    "READY" if tx11_controls_ready_offline else "PENDING",
                ),
                evidence(
                    tx7_soak_path,
                    "TX7 pasó 600 s de plataforma con hostapd/SSH/IRQs vivos y cero fatal markers, pero sin cliente.",
                    "PARTIAL" if tx7_platform_soak else "PENDING",
                ),
                evidence(
                    tx7_gate_result_path,
                    "El evaluador clasifica correctamente el gate TX7 como NO_CLIENT, no como PASS.",
                    "PARTIAL" if tx7_no_client_gate else "PENDING",
                ),
                evidence(ledger_path, "Clientes 2.4 reales asociaron y pasaron Internet por br0, pero con rendimiento fallido.", "PARTIAL" if realtek_client_proven else "PENDING"),
                evidence(w2_tx2_path, "TX2 compacta TXBD y deja hardware throughput pendiente.", "PENDING" if realtek_perf_pending else "UNKNOWN"),
                evidence(tx2_beacon_fail_path, "TX2 global rompió visibilidad de beacon/RF; no pedir Speedtest mientras SSID sea invisible.", "PARTIAL" if realtek_tx2_beacon_failed else "PENDING"),
                evidence(realtek_tx_taxonomy_path, "La taxonomía separa TX0/TX1/TX2/TX3 de colas hardware BE y beacon/management.", "READY" if has(realtek_tx_taxonomy, r"TX0", r"TX1", r"TX2", r"TX3", r"BE") else "PENDING"),
                evidence(tx3_manifest_path, "La imagen completa TX3 está construida offline como RAM-only: cabe en Bootbase, usa SSID abierto y limita TXBD compacto a colas de datos.", "READY" if tx3_ready_offline else "PENDING"),
                evidence(tx3_preassoc_path, "TX3 arrancado en vivo: hostapd ENABLED, br0 contiene eth0+wlan0, IRQ28 progresa y no hay Oops; aún no hay estación asociada.", "PARTIAL" if tx3_live_preassoc else "PENDING"),
                evidence(tx3_preassoc_result_path, "El gate oficial falla correctamente por falta de asociación/DHCP/tráfico/soak; no autoriza Speedtest.", "PARTIAL" if tx3_client_gate_fail_preassoc else "PENDING"),
                evidence(w2_matrix_path, "La matriz exige down/up >= 5 Mbps, BE queue < 384 y soak.", "PENDING"),
            ],
            next_discriminant=realtek_next,
        )
    )

    quantenna_assoc = has(ledger, r"Real 5 GHz client reaches complete open association")
    quantenna_crash = has(ledger, r"Post-association crash is NULL DMA mapping")
    quantenna_tx7_misaligned = has(
        w3_tx7_fault,
        r"Misaligned Access",
        r"EFA=0x86f900a9|EFA:\s+0x86f900a9",
        r"PHYSICAL_POWER_CYCLE_REQUIRED|physical power-cycle required",
    )
    gates.append(
        Gate(
            id="phase2.quantenna-5g",
            phase="Fase 2 - Materializar los sectores",
            sector="Sector Quantenna",
            requirement="5 GHz reparado con cliente real, tráfico, WPA2/DFS y sin crash MuC/TQE.",
            status="BLOCKED" if current_tx7_hang and quantenna_tx7_misaligned else "PARTIAL" if quantenna_assoc or quantenna_crash or quantenna_tx7_misaligned else "PENDING",
            evidence=[
                evidence(
                    w3_tx7_fault_path,
                    "TX7/5G alcanzó control/RF/IRQ8/probe RX y después cayó en Misaligned Access; falta module-map same-boot para simbolizar exacto.",
                    "BLOCKED" if quantenna_tx7_misaligned and current_tx7_hang else "PARTIAL" if quantenna_tx7_misaligned else "PENDING",
                ),
                evidence(ledger_path, "5 GHz alcanzó asociación abierta real en intentos anteriores, pero el tráfico no está certificado de forma estable.", "PARTIAL" if quantenna_assoc else "PENDING"),
                evidence(ledger_path, "La corrección switch_tqe está offline y requiere recheck hardware.", "PENDING" if quantenna_crash else "UNKNOWN"),
            ],
            next_discriminant="No repetir 5 GHz hasta recuperar gestión; el próximo intento debe capturar /proc/modules y /sys/module/*/sections/.text antes de tráfico cliente.",
        )
    )

    lab_flash_done = has(ledger, r"Q2 cold-boots automatically from `mtd4/linux_live`")
    entropy_pending = has(ledger, r"manual UART entropy", r"AUTONOMOUS PENDING")
    gates.append(
        Gate(
            id="phase2.lab-persistence",
            phase="Fase 2 - Materializar los sectores",
            sector="Sector Memoria",
            requirement="Firmware LAB persistente en slot inactivo con OEM conservado y sin gate manual frágil.",
            status="PARTIAL" if lab_flash_done and entropy_pending else "PENDING",
            evidence=[
                evidence(ledger_path, "Q2 cold-boot desde mtd4 está probado, pero requirió entropy manual por UART.", "PARTIAL" if lab_flash_done else "PENDING"),
            ],
            next_discriminant="No promover Q3/W2 a flash hasta cerrar autonomía, bridge, rollback y readback exacto.",
        )
    )

    lyoko_overlay_pass = has(lyoko_validation, r"Current validation status: `PASS`", r"Integrator added")
    lyoko_live_verifier_ready = (
        lyoko_live_verifier.is_file()
        and has(
            lyoko_live_verifier_text,
            r"router-lyoko\.runtime-status/v1",
            r"router-lyoko\.runtime-bridge/v1",
            r"router-lyoko\.runtime-events/v1",
            r"router-lyoko\.runtime-towers/v1",
            r"router-lyoko\.runtime-clients/v1",
            r"router-lyoko\.runtime-recovery/v1",
            r"REQUIRED_RUNTIME_STATUS_SECTIONS",
            r"REQUIRED_RUNTIME_BRIDGE_SECTIONS",
            r"REQUIRED_RUNTIME_EVENT_IDS",
            r"REQUIRED_RUNTIME_TOWER_FIELDS",
            r"REQUIRED_RUNTIME_CLIENT_FIELDS",
            r"REQUIRED_RUNTIME_RECOVERY_SECTIONS",
            r'"clients"',
            r"raw_logs_exposed",
            r"raw_station_dump_exposed",
            r"runtime_status\.recovery\.flash_write_disabled",
            r"runtime_recovery\.recovery_gate\.hardware_recovery_proven_current_boot\.false",
            r"runtime_bridge\.management\.management_path_gate",
            r"runtime_events\.raw_logs_exposed\.false",
            r"runtime_bridge\.control_surface_exposed\.false",
            r"runtime_towers\.control_surface_exposed\.false",
            r"runtime_clients\.control_surface_exposed\.false",
            r"management_path\.proven",
            r"recovery_guards\.runtime_guards_proven",
            r"realtek\.client_data_path\.proven",
            r"READONLY-LIVE-VERIFY-NO-CONTROL",
        )
        and lyoko_live_verifier_test.is_file()
        and has(
            lyoko_live_verifier_test_text,
            r"test_rejects_missing_runtime_status_contract",
            r"test_rejects_runtime_status_without_clients_coverage",
            r"test_rejects_runtime_status_without_recovery_guard",
            r"test_rejects_invalid_runtime_status_port_and_client_values",
            r"test_rejects_missing_runtime_bridge_contract",
            r"test_rejects_runtime_bridge_raw_or_control_exposure",
            r"test_rejects_invalid_runtime_bridge_values",
            r"test_strict_management_path_gate_rejects_carrier_only",
            r"test_rejects_missing_runtime_events_contract",
            r"test_rejects_runtime_events_raw_log_exposure",
            r"test_rejects_runtime_events_missing_required_event",
            r"test_rejects_missing_runtime_towers_contract",
            r"test_rejects_runtime_towers_control_or_write_enabled",
            r"test_rejects_runtime_towers_wrong_service_mapping",
            r"test_rejects_missing_runtime_clients_contract",
            r"test_rejects_runtime_clients_raw_or_control_exposure",
            r"test_rejects_invalid_runtime_client_values",
            r"test_strict_realtek_client_data_gate_rejects_association_only",
            r"test_rejects_missing_runtime_recovery_contract",
            r"test_rejects_runtime_recovery_raw_or_control_exposure",
            r"test_rejects_runtime_recovery_write_or_self_recover_claims",
            r"test_strict_recovery_guards_rejects_write_target_or_self_recover",
        )
    )
    lyoko_static_index_verifier_ready = (
        lyoko_static_index_verifier.is_file()
        and has(
            lyoko_static_index_verifier_text,
            r"router-lyoko\.static-data/v1",
            r"STATIC-READONLY-RAM-OVERLAY-NO-FLASH",
            r"--manifest",
            r"sha256",
        )
    )
    lyoko_served_files_verifier_ready = (
        lyoko_served_files_verifier.is_file()
        and has(
            lyoko_served_files_verifier_text,
            r"READONLY-SERVED-WEB-FILES-VERIFY-NO-CONTROL",
            r"rootfs/var/www/",
            r"rootfs/var/www/api/",
            r"--manifest",
            r"sha256",
        )
    )
    lyoko_served_no_secrets_ready = (
        lyoko_served_no_secrets_verifier.is_file()
        and has(
            lyoko_served_no_secrets_verifier_text,
            r"READONLY-SERVED-NO-SECRETS-VERIFY-NO-CONTROL",
            r"/api/lyoko",
            r"/api/lyoko-control",
            r"load_expected_files",
            r"scan_text",
            r"Findings never include the secret value",
        )
        and lyoko_served_no_secrets_test.is_file()
        and has(
            lyoko_served_no_secrets_test_text,
            r"test_accepts_current_local_web_root",
            r"test_rejects_secret_in_static_served_file_without_printing_value",
            r"test_rejects_secret_in_api_response_without_printing_value",
        )
        and has(
            lyoko_reentry_gate_text,
            r"verify_router_lyoko_served_no_secrets\.py",
            r"served_no_secrets_verifier_ok",
        )
        and has(
            lyoko_reentry_result_verifier_text,
            r"READONLY-SERVED-NO-SECRETS-VERIFY-NO-CONTROL",
            r"served_no_secrets_verifier_ok",
        )
        and has(
            lyoko_reentry_fixture_test_text,
            r"test_reentry_execute_fails_closed_when_control_endpoint_serves_secret",
            r"COOKIE_SESSION_KEY",
            r"served_no_secrets_verifier_ok",
        )
    )
    lyoko_static_sync_ready = (
        lyoko_static_sync.is_file()
        and has(
            lyoko_static_sync_text,
            r"--check",
            r"find_static_drift",
            r"served_file_drift",
            r"manifest_drift",
            r"sha256sums_drift",
        )
        and lyoko_static_data_test.is_file()
        and has(
            lyoko_static_data_test_text,
            r"test_sync_check_fails_closed_on_stale_source_copy",
            r"test_sync_check_mode_does_not_modify_overlay_copy",
            r"served_file_drift",
            r"manifest_drift",
            r"sha256sums_drift",
        )
    )
    lyoko_packager_sync_ready = (
        lyoko_packager.is_file()
        and has(
            lyoko_packager_text,
            r"verify_static_truth_sync",
            r"static Lyoko truth is stale",
            r"find_static_drift",
        )
        and lyoko_packager_test.is_file()
        and has(
            lyoko_packager_test_text,
            r"test_package_refuses_self_consistent_but_stale_static_truth",
            r"static Lyoko truth is stale",
        )
    )
    lyoko_integrator_sync_ready = (
        lyoko_integrator.is_file()
        and has(
            lyoko_integrator_text,
            r"verify_static_truth_sync",
            r"static Lyoko truth is stale",
            r"find_static_drift",
        )
        and lyoko_integrator_test.is_file()
        and has(
            lyoko_integrator_test_text,
            r"test_refuses_self_consistent_but_stale_static_truth",
            r"static Lyoko truth is stale",
        )
    )
    lyoko_no_secrets_ready = (
        lyoko_no_secrets_verifier.is_file()
        and has(
            lyoko_no_secrets_verifier_text,
            r"router-lyoko\.no-secrets-scan/v1",
            r"READONLY-WEB-SECRET-SCAN-NO-CONTROL",
            r"SECRET_ASSIGNMENT_RE",
            r"PEM_SECRET_RE",
            r"assert_no_secrets",
            r"Findings never include the secret value",
        )
        and lyoko_no_secrets_test.is_file()
        and has(
            lyoko_no_secrets_test_text,
            r"test_current_overlay_passes",
            r"test_policy_text_false_and_blocked_is_not_a_secret",
            r"test_rejects_private_key_marker_without_printing_key_body",
            r"test_rejects_concrete_router_secret_assignment_without_printing_value",
            r"test_allows_redacted_or_placeholder_secret_fields",
        )
        and has(
            lyoko_packager_text,
            r"verify_no_secrets",
            r"assert_no_secrets",
        )
        and has(
            lyoko_packager_test_text,
            r"test_package_refuses_secret_material_in_web_overlay",
            r"Lyoko web overlay contains secret material",
        )
        and has(
            lyoko_integrator_text,
            r"verify_no_secrets",
            r"assert_no_secrets",
        )
        and has(
            lyoko_integrator_test_text,
            r"test_refuses_secret_material_before_copy",
            r"Lyoko web overlay contains secret material",
        )
    )
    lyoko_objective_coverage_ready = (
        lyoko_objective_coverage_guard.is_file()
        and has(
            lyoko_objective_coverage_guard_text,
            r"router-lyoko\.objective-coverage/v1",
            r"READONLY-OBJECTIVE-COVERAGE-NO-HARDWARE",
            r"router\.kernel_linux510",
            r"router\.ethernet_ssh_recovery",
            r"router\.realtek_2g",
            r"router\.quantenna_5g",
            r"router\.persistence_flash",
            r"lyoko\.visual_dashboard",
            r"lyoko\.telemetry_api",
            r"lyoko\.towers_services",
            r"lyoko\.missions_history",
            r"lyoko\.aelita_persona_memory",
            r"lyoko\.safe_mode_control_policy",
            r"lyoko\.xana_alerts",
            r"goal_overclaim",
            r"hardware_overclaim",
        )
        and lyoko_objective_coverage_guard_test.is_file()
        and has(
            lyoko_objective_coverage_guard_test_text,
            r"test_current_overlay_covers_objective_without_overclaim",
            r"test_rejects_missing_objective_panel",
            r"test_rejects_goal_completion_overclaim",
            r"test_rejects_hardware_gate_promoted_from_static_overlay",
            r"test_rejects_missing_evidence_binding_for_surface",
        )
        and has(
            lyoko_packager_text,
            r"verify_objective_coverage",
            r"objective coverage guard failed",
        )
    )
    lyoko_reentry_gate_ready = (
        lyoko_reentry_gate.is_file()
        and has(
            lyoko_reentry_gate_text,
            r"OPENMITRASTAR_LYOKO_REENTRY_READONLY",
            r"verify_router_lyoko_live\.py",
            r"verify_router_lyoko_control_api\.py",
            r"verify_router_lyoko_static_index\.py",
            r"verify_router_lyoko_served_files\.py",
            r"verify_router_lyoko_served_no_secrets\.py",
            r"verify_router_lyoko_reentry_result\.py",
            r"--require-kernel-510",
            r"--require-bridge-up",
            r"--require-ssh-running",
            r"--require-management-path",
            r"--require-recovery-guards",
            r"/api/lyoko-control",
            r"/lyoko-data/index\.json",
            r"/lyoko\.html",
            r"/lyoko\.css",
            r"/lyoko\.js",
            r"served_no_secrets_verifier_ok",
            r"result_verifier_ok",
        )
        and not any_has(
            lyoko_reentry_gate_text,
            r"flash_erase",
            r"mtd_debug",
            r"fw_setenv",
            r"saveenv",
            r"reboot -f",
            r"mode COM",
            r"bootm",
            r"ATGO",
        )
    )
    lyoko_reentry_fixture_ready = (
        lyoko_reentry_fixture_test.is_file()
        and has(
            lyoko_reentry_fixture_test_text,
            r"ThreadingHTTPServer",
            r"OMLYOKO_REENTRY_PASS=1",
            r"state_verifier_ok",
            r"control_verifier_ok",
            r"static_index_verifier_ok",
            r"served_files_verifier_ok",
            r"OMLYOKO_REENTRY_PASS=0",
            r"LYOKO_STATE_NOT_PROVEN",
            r"LYOKO_CONTROL_NOT_PROVEN",
            r"LYOKO_STATIC_INDEX_NOT_PROVEN",
            r"served\./lyoko\.js\.sha256",
            r"bridge\.up",
            r"request\.no_write",
            r"safety\.flash_write\.false",
        )
    )
    lyoko_reentry_result_verifier_ready = (
        lyoko_reentry_result_verifier.is_file()
        and has(
            lyoko_reentry_result_verifier_text,
            r"router-lyoko\.reentry-live-api-result/v1",
            r"READONLY-REENTRY-RESULT-VERIFY-NO-CONTROL",
            r"READONLY-LIVE-VERIFY-NO-CONTROL",
            r"READONLY-CONTROL-CONTRACT-VERIFY-NO-CONTROL",
            r"READONLY-STATIC-INDEX-VERIFY-NO-CONTROL",
            r"READONLY-SERVED-WEB-FILES-VERIFY-NO-CONTROL",
            r"pass\.matches_lanes",
            r"mutations\.",
            r"under_output_dir",
        )
    )
    lyoko_reentry_result_test_ready = (
        lyoko_reentry_result_test.is_file()
        and has(
            lyoko_reentry_result_test_text,
            r"test_accepts_coherent_pass_result_with_all_evidence",
            r"test_rejects_forged_pass_true_when_lane_failed",
            r"test_rejects_missing_evidence_file",
            r"test_rejects_mutation_flag_enabled",
            r"test_rejects_stdout_ok_mismatch",
            r"test_rejects_evidence_path_outside_output_dir",
        )
    )
    gates.append(
        Gate(
            id="phase3.lyoko-readonly-dashboard",
            phase="Fase 3 - Construir Lyoko",
            sector="Sector Interfaz",
            requirement="Dashboard/API Lyoko read-only conectado a estado real y preparado para rootfs RAM-test.",
            status="READY" if lyoko_overlay_pass and lyoko_integrator.is_file() and lyoko_integrator_sync_ready and lyoko_no_secrets_ready and lyoko_objective_coverage_ready and lyoko_live_verifier_ready and lyoko_static_sync_ready and lyoko_packager_sync_ready and lyoko_static_index_verifier_ready and lyoko_served_files_verifier_ready and lyoko_served_no_secrets_ready and lyoko_reentry_gate_ready and lyoko_reentry_fixture_ready and lyoko_reentry_result_verifier_ready and lyoko_reentry_result_test_ready else "PENDING",
            evidence=[
                evidence(lyoko_validation_path, "Overlay e integrador Router-Lyoko pasan validaciones locales.", "READY" if lyoko_overlay_pass else "PENDING"),
                evidence(lyoko_integrator, "Integrador copia sólo web/API read-only, verifica hashes y rechaza static Lyoko truth stale antes de copiar.", "READY" if lyoko_integrator_sync_ready else "PENDING"),
                evidence(lyoko_integrator_test, "Tests del integrador rechazan un overlay stale aunque su manifest coincida, sin copiarlo a la rootfs RAM-test.", "READY" if lyoko_integrator_sync_ready else "PENDING"),
                evidence(lyoko_no_secrets_verifier, "Verificador no-secrets escanea web/API Lyoko y rechaza claves concretas, PSK, passwords, COOKIE_SESSION_KEY, secretos cloud y bloques PEM sin imprimir el valor.", "READY" if lyoko_no_secrets_ready else "PENDING"),
                evidence(lyoko_no_secrets_test, "Tests no-secrets cubren overlay actual limpio, falsos positivos de política, PEM, asignaciones concretas y placeholders/redacted permitidos.", "READY" if lyoko_no_secrets_ready else "PENDING"),
                evidence(lyoko_objective_coverage_guard, "Guard de cobertura del objetivo exige superficies para Linux 5.10, puente/recovery, Realtek 2.4, Quantenna 5, persistencia, dashboard, API, torres, misiones, memoria Aelita, modo seguro y alertas XANA sin reclamar hardware no probado.", "READY" if lyoko_objective_coverage_ready else "PENDING"),
                evidence(lyoko_objective_coverage_guard_test, "Tests de cobertura rechazan paneles ausentes, completion overclaim, promoción falsa de gates hardware y bindings de evidencia ausentes.", "READY" if lyoko_objective_coverage_ready else "PENDING"),
                evidence(lyoko_live_verifier, "Verificador live valida /api/lyoko sin control ni escrituras, exige runtime_status con system/ports/radios/clients/bridge/recovery, runtime_bridge con link/IP/IRQ/SSH, runtime_recovery con guardias no destructivas y ruta externa, runtime_towers con servicios pidof, runtime_events clasificados sin logs crudos y runtime_clients con autorización/tráfico/BE RP fail-closed.", "READY" if lyoko_live_verifier_ready else "PENDING"),
                evidence(lyoko_live_verifier_test, "Tests del live verifier rechazan payloads sin runtime_status/runtime_bridge/runtime_recovery/runtime_towers/runtime_events/runtime_clients, sin clients, con recovery write-capable, puente raw/control, gestión carrier-only en gate estricta, recovery self-heal/write-target en gate estricta, torres write/control, valores inválidos de puerto/cliente, exposición de raw logs/station dumps o asociación-only en gate estricta Realtek.", "READY" if lyoko_live_verifier_ready else "PENDING"),
                evidence(lyoko_validation_path, "Dashboard monta Cobertura runtime, Puente runtime, Recovery runtime, Clientes runtime, Torres runtime y Eventos XANA runtime para renderizar runtime_status/runtime_bridge/runtime_recovery/runtime_clients/runtime_towers/runtime_events sin ejecutar control ni exponer logs crudos.", "READY" if lyoko_overlay_pass and lyoko_live_verifier_ready else "PENDING"),
                evidence(lyoko_static_sync, "Sincronizador estático tiene modo --check no mutante que detecta drift fuente→lyoko-data→manifest/SHA256SUMS.", "READY" if lyoko_static_sync_ready else "PENDING"),
                evidence(lyoko_static_data_test, "Tests de datos estáticos usan --check y cubren served_file_drift, manifest_drift y sha256sums_drift.", "READY" if lyoko_static_sync_ready else "PENDING"),
                evidence(lyoko_packager, "Empaquetador ejecuta el guard source-to-served antes de crear el tar y rechaza static Lyoko truth stale.", "READY" if lyoko_packager_sync_ready else "PENDING"),
                evidence(lyoko_packager_test, "Tests del empaquetador rechazan un overlay stale aunque su manifest coincida con el fichero obsoleto.", "READY" if lyoko_packager_sync_ready else "PENDING"),
                evidence(lyoko_static_index_verifier, "Verificador de índice estático compara /lyoko-data/index.json contra bytes/SHA256 del manifest local.", "READY" if lyoko_static_index_verifier_ready else "PENDING"),
                evidence(lyoko_served_files_verifier, "Verificador de ficheros servidos compara /lyoko.html, /lyoko.css, /lyoko.js y /lyoko-data/* contra bytes/SHA256 del manifest local.", "READY" if lyoko_served_files_verifier_ready else "PENDING"),
                evidence(lyoko_served_no_secrets_verifier, "Verificador de no-secrets servidos escanea /api/lyoko, /api/lyoko-control y web/static payloads desde URL/directorio y rechaza secretos concretos sin imprimirlos.", "READY" if lyoko_served_no_secrets_ready else "PENDING"),
                evidence(lyoko_served_no_secrets_test, "Tests de no-secrets servido cubren payload local limpio, secreto en estático, secreto en API y ausencia de comandos de mutación.", "READY" if lyoko_served_no_secrets_ready else "PENDING"),
                evidence(lyoko_reentry_gate, "Puerta de reentrada hace GET /api/lyoko, /api/lyoko-control, /lyoko-data/index.json y los ficheros web estáticos; exige kernel 5.10, bridge up, torre SSH running, runtime_bridge management path, runtime_recovery guards, control fail-closed, static index sin drift, served files sin drift, served no-secrets y verificación del propio lyoko-reentry-result.json.", "READY" if lyoko_reentry_gate_ready and lyoko_served_no_secrets_ready else "PENDING"),
                evidence(lyoko_reentry_fixture_test, "Test E2E local ejecuta la puerta de reentrada contra un HTTP fixture; exige PASS de estado/control/índice/ficheros servidos y fail-closed ante estado caído, control write-capable, índice inseguro o /lyoko.js corrupto.", "READY" if lyoko_reentry_fixture_ready else "PENDING"),
                evidence(lyoko_reentry_result_verifier, "Verificador de resultado valida lyoko-reentry-result.json contra stdout JSON, exits, clasificaciones, rutas bajo output_dir y mutaciones falsas; rechaza PASS forjado.", "READY" if lyoko_reentry_result_verifier_ready else "PENDING"),
                evidence(lyoko_reentry_result_test, "Tests del verificador de resultado cubren PASS coherente, PASS forjado, evidencia ausente, mutación activada, mismatch stdout/result y path escape.", "READY" if lyoko_reentry_result_test_ready else "PENDING"),
            ],
            next_discriminant="Tras recuperación post-TX7, ejecutar la puerta read-only de reentrada y obtener PASS real de /api/lyoko, /api/lyoko-control, /lyoko-data/index.json, /lyoko.html, /lyoko.css, /lyoko.js y /lyoko-data/* desde hardware.",
        )
    )

    control_policy_ready = (
        lyoko_control_policy_path.is_file()
        and lyoko_control_validator.is_file()
        and has(control_policy_text, r'"schema":\s*"router-lyoko\.control-policy/v1"', r'"mode":\s*"observe_only"')
        and has(control_policy_text, r'"control\.flash_promote"', r'"control\.module_reload"', r'"control\.network_reconfigure"')
    )
    gates.append(
        Gate(
            id="phase3.safe-control-policy",
            phase="Fase 3 - Construir Lyoko",
            sector="Sector Aelita",
            requirement="Base de control segura con allowlist observable y acciones peligrosas bloqueadas.",
            status="READY" if control_policy_ready else "PENDING",
            evidence=[
                evidence(
                    lyoko_control_policy_path,
                    "La política arranca en observe_only y bloquea flash, módulos y red.",
                    "READY" if control_policy_ready else "PENDING",
                ),
                evidence(
                    lyoko_control_validator,
                    "El validador rechaza tokens peligrosos en acciones permitidas.",
                    "READY" if lyoko_control_validator.is_file() else "PENDING",
                ),
            ],
            next_discriminant="Promover a safe_control sólo después de /api/lyoko strict PASS, bridge soak, Realtek gate y recovery actual.",
        )
    )

    lyoko_control_api_ready = (
        lyoko_control_api.is_file()
        and has(lyoko_control_api_text, r"observe_only|OBSERVE", r"goal-audit\.json", r"aelita-memory\.json")
        and not any_has(lyoko_control_api_text, r"flash_erase", r"fw_setenv", r"mtd_debug", r"insmod", r"reboot")
    )
    aelita_memory_staged = (
        lyoko_aelita_memory_path.is_file()
        and has(
            aelita_memory_text,
            r'"schema":\s*"router-lyoko\.aelita-memory/v1"',
            r'"writes_device_now":\s*false',
            r"future_backend",
        )
    )
    evidence_bindings_staged = (
        lyoko_evidence_bindings_path.is_file()
        and has(
            evidence_bindings_text,
            r'"schema":\s*"router-lyoko\.evidence-bindings/v1"',
            r'"id":\s*"live\.runtime_status"',
            r'"id":\s*"live\.runtime_bridge"',
            r'"id":\s*"live\.runtime_clients"',
            r'"id":\s*"live\.runtime_recovery"',
            r'"id":\s*"live\.runtime_towers"',
            r'"id":\s*"live\.runtime_events"',
            r"runtime_status\.clients\.wlan0\.associated_count",
            r"runtime_bridge\.management\.management_path_proven",
            r"runtime_clients\.interfaces\.wlan0\.data_path_proven",
            r"runtime_recovery\.recovery_gate\.hardware_recovery_proven_current_boot",
            r"runtime_towers\.towers\.ssh\.service",
            r"runtime_events\.raw_logs_exposed",
            r"hardware_proof",
            r"failure_mode",
        )
    )
    telemetry_contract_staged = (
        lyoko_telemetry_contract_path.is_file()
        and has(
            telemetry_contract_text,
            r'"schema":\s*"router-lyoko\.telemetry-contract/v1"',
            r"fresh_after_seconds",
            r'"dashboard_executes_commands":\s*false',
        )
    )
    telemetry_contract_guard_ready = (
        lyoko_telemetry_contract_guard.is_file()
        and lyoko_telemetry_contract_guard_test.is_file()
        and has(
            telemetry_contract_guard_text,
            r"router-lyoko\.telemetry-contract-guard/v1",
            r"READONLY-TELEMETRY-CONTRACT-GUARD-NO-HARDWARE",
            r"REQUIRED_RUNTIME_FIELDS",
            r"REQUIRED_SAFETY_FALSE",
            r"fresh_after_seconds must be lower than stale_after_seconds",
            r"runtime_endpoint must be /api/lyoko",
            r"mission_data\.\*",
        )
        and has(
            telemetry_contract_guard_test_text,
            r"test_current_contract_passes",
            r"test_rejects_invalid_freshness_window",
            r"test_rejects_write_enabled_safety_flag",
            r"test_rejects_static_mission_data_promoted_to_hardware_proof",
            r"test_rejects_wrong_runtime_endpoint",
        )
    )
    aelita_dialogue_staged = (
        lyoko_aelita_dialogue_path.is_file()
        and has(
            aelita_dialogue_text,
            r'"schema":\s*"router-lyoko\.aelita-dialogue/v1"',
            r"truth_rule",
            r'"writes_device_now":\s*false',
        )
    )
    aelita_memory_guard_ready = (
        lyoko_aelita_memory_guard.is_file()
        and lyoko_aelita_memory_guard_test.is_file()
        and has(
            lyoko_aelita_memory_guard_text,
            r"mission_log_chain_break",
            r"static_dialogue_hardware_claim",
            r"device_write_enabled",
            r"router-lyoko\.aelita-memory-guard/v1",
        )
        and has(
            lyoko_aelita_memory_guard_test_text,
            r"test_rejects_device_write_enabled_memory",
            r"test_rejects_static_dialogue_hardware_claim",
            r"test_rejects_mission_log_chain_break",
            r"test_rejects_unindexed_memory_slot_source",
        )
    )
    event_taxonomy_staged = (
        lyoko_event_taxonomy_path.is_file()
        and has(
            event_taxonomy_text,
            r'"schema":\s*"router-lyoko\.event-taxonomy/v1"',
            r"xana\.",
            r'"dashboard_executes_commands":\s*false',
        )
    )
    lab_console_text_only = has(lyoko_validation, r"LAB console panel", r"renders text\s+only|text-only", r"does not execute")
    gates.append(
        Gate(
            id="phase3.lyoko-memory-agents-control",
            phase="Fase 3 - Construir Lyoko",
            sector="Sector Aelita",
            requirement="Memoria persistente, consola LAB, control local seguro, voz/agentes y eventos narrados.",
            status="PENDING",
            evidence=[
                evidence(
                    lyoko_control_api,
                    "/api/lyoko-control está staged como contrato fail-closed observe-only; no ejecuta comandos ni escribe estado.",
                    "READY" if lyoko_control_api_ready else "PENDING",
                ),
                evidence(
                    lyoko_aelita_memory_path,
                    "La memoria Aelita está staged como contrato versionado RAM/static snapshot con writes_device_now=false.",
                    "READY" if aelita_memory_staged else "PENDING",
                ),
                evidence(
                    lyoko_evidence_bindings_path,
                    "Los bindings de evidencia separan fuentes runtime con hardware_proof de snapshots estáticos sin prueba hardware, incluyendo live.runtime_status, live.runtime_bridge, live.runtime_clients, live.runtime_recovery, live.runtime_towers y live.runtime_events.",
                    "READY" if evidence_bindings_staged else "PENDING",
                ),
                evidence(
                    lyoko_telemetry_contract_path,
                    "El contrato de telemetría define frescura runtime y auto-refresh observe-only.",
                    "READY" if telemetry_contract_staged else "PENDING",
                ),
                evidence(
                    lyoko_telemetry_contract_guard,
                    "El guard del contrato de telemetría verifica /api/lyoko como único endpoint runtime, frescura fail-closed, safety flags false y separación hardware_proof entre runtime y snapshots estáticos.",
                    "READY" if telemetry_contract_guard_ready else "PENDING",
                ),
                evidence(
                    lyoko_telemetry_contract_guard_test,
                    "Tests del contrato de telemetría rechazan ventanas de frescura inválidas, safety flags write-enabled, promoción falsa de mission_data.* a hardware_proof y endpoints runtime incorrectos.",
                    "READY" if telemetry_contract_guard_ready else "PENDING",
                ),
                evidence(
                    lyoko_aelita_dialogue_path,
                    "El catálogo de diálogo Aelita liga cada frase a una condición y fuente de evidencia.",
                    "READY" if aelita_dialogue_staged else "PENDING",
                ),
                evidence(
                    lyoko_aelita_memory_guard,
                    "El guard Aelita memory verifica que memoria, diálogo e historial sean read-only, tengan fuentes indexadas, mantengan cadena hash JSONL y no puedan reclamar hardware desde snapshots estáticos.",
                    "READY" if aelita_memory_guard_ready else "PENDING",
                ),
                evidence(
                    lyoko_aelita_memory_guard_test,
                    "Tests del guard Aelita memory rechazan writes_device_now=true, diálogo estático con hardware_claim, rotura de cadena mission-log y fuentes no indexadas.",
                    "READY" if aelita_memory_guard_ready else "PENDING",
                ),
                evidence(
                    lyoko_event_taxonomy_path,
                    "La taxonomía XANA tipa eventos reales sin ejecutar recuperación ni control.",
                    "READY" if event_taxonomy_staged else "PENDING",
                ),
                evidence(
                    lyoko_validation_path,
                    "La consola LAB está staged como panel text-only; persistencia on-device, control ejecutable y voz/agentes siguen sin probarse.",
                    "READY" if lab_console_text_only else "PENDING",
                ),
            ],
            next_discriminant=(
                "Tras recuperación post-TX7, integrar en raíz RAM-test exacta y verificar /api/lyoko + /api/lyoko-control en hardware; "
                "no promover persistencia, control ejecutable ni voz/agentes hasta cerrar router funcional, rollback y no-flash gates."
            ),
        )
    )

    return gates


def summarize(gates: list[Gate]) -> dict:
    counts: dict[str, int] = {}
    for gate in gates:
        counts[gate.status] = counts.get(gate.status, 0) + 1
    blockers = [g for g in gates if g.status in {"PARTIAL", "PENDING", "BLOCKED", "UNKNOWN"}]
    next_gate = sorted(blockers, key=lambda g: STATUS_ORDER.get(g.status, 99))[0] if blockers else None
    return {
        "schema": "router-lyoko.truth/v1",
        "project": "Router-Lyoko",
        "classification": "EVIDENCE-LEDGER-READONLY-NO-FLASH",
        "persona": "Aelita",
        "summary": {
            "counts": counts,
            "next_gate": next_gate.id if next_gate else None,
            "truth_rule": "Lyoko UI may render only what current evidence supports.",
        },
        "gates": [asdict(g) for g in gates],
    }


def render_markdown(doc: dict) -> str:
    lines = [
        "# Router-Lyoko mission truth",
        "",
        f"Classification: `{doc['classification']}`",
        "",
        "Rule: Lyoko UI may render only what current evidence supports.",
        "",
        "## Summary",
        "",
    ]
    for status, count in sorted(doc["summary"]["counts"].items(), key=lambda kv: STATUS_ORDER.get(kv[0], 99)):
        lines.append(f"- `{status}`: {count}")
    lines.extend(["", "## Gates", ""])
    for gate in doc["gates"]:
        lines.extend(
            [
                f"### {gate['id']}",
                "",
                f"- Phase: {gate['phase']}",
                f"- Sector: {gate['sector']}",
                f"- Status: `{gate['status']}`",
                f"- Requirement: {gate['requirement']}",
                f"- Next discriminant: {gate['next_discriminant']}",
                "- Evidence:",
            ]
        )
        for ev in gate["evidence"]:
            lines.append(f"  - `{ev['status']}` `{ev['path']}` — {ev['claim']}")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compile Router-Lyoko phase/sector gates from current mission evidence."
    )
    parser.add_argument("--json-out", type=Path, default=LYOKO / "mission-truth.json")
    parser.add_argument("--md-out", type=Path, default=LYOKO / "MISSION_TRUTH.md")
    parser.add_argument("--write", action="store_true", help="Write JSON and Markdown outputs.")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    doc = summarize(build_gates())
    if args.write:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
        args.md_out.parent.mkdir(parents=True, exist_ok=True)
        args.md_out.write_text(render_markdown(doc), encoding="utf-8")
    print(json.dumps(doc, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
