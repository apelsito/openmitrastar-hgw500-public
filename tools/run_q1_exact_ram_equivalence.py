#!/usr/bin/env python3
"""Exact-candidate Q1 RAM/SSH equivalence gate.

This specializes the shared management-only observer for the exact flash-sized
Q1 image. Default mode is local-only. Execute mode is read-only and accepts
the manifest-declared fail-closed state when external radio credentials are
absent; it never claims either radio operational from that state.
"""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
BASE_PATH = ROOT / "tools/run_f5_foundation_ram_equivalence.py"
SPEC = importlib.util.spec_from_file_location("openmitrastar_shared_ram_equivalence", BASE_PATH)
assert SPEC and SPEC.loader
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

CANDIDATE_DIR = ROOT / "work/mission-state/f2-q1-full-flash-candidate"
EXPECTED_UART_SHA256 = "426fda61b9b4168e363dcc6b6fffdb8545d29b3f3607ed3962219442b5f2468a"

BASE.CANDIDATE_DIR = CANDIDATE_DIR
BASE.DEFAULT_CANDIDATE = CANDIDATE_DIR / "openmitrastar-linux510-q1-full-webformat.bin"
BASE.DEFAULT_MANIFEST = CANDIDATE_DIR / "manifest.json"
BASE.DEFAULT_RAM_IMAGE = ROOT / "work/tftp/omvl/linux510-q1-full-product-v1-LZMA-RAM-TEST-NO-FLASH.bin"
BASE.DEFAULT_UART_LOG = ROOT / "outputs/uart-live/ramssh-cycle-20260820-203019.log"
BASE.DEFAULT_OUTPUT = CANDIDATE_DIR / "ram-equivalence.json"
BASE.EXPECTED_SHA256 = "bd473ef7f7238a5f9488e4739308615355c7e86526c5c867e16d3a232908c306"
BASE.EXPECTED_BYTES = 3_647_602
BASE.RAM_BOOT_NAME = "linux510-q1-full-product-v1-LZMA-RAM-TEST-NO-FLASH.bin"
BASE.DEFAULT_HOST = "192.168.1.90"
BASE.ACK = "OPENMITRASTAR_Q1_EXACT_RAM_EQUIVALENCE"
BASE.PROFILE = "Q1_FULL_PRODUCT"
BASE.SCOPE = "OEM-PARITY-INTEGRATION"
BASE.RUNNER_SCHEMA = "openmitrastar.q1-exact-ram-equivalence-runner/v1"
BASE.PASS_MARKER_PREFIX = "OM_Q1_EXACT_RAM_EQ"
BASE.EXPECTED_DEGRADED_SERVICES = ("S35-radio-modules", "S50-radio-ap")

shared_static_checks = BASE.static_checks


def q1_static_checks(candidate: Path, manifest_path: Path, ram_image: Path,
                     uart_log: Path):
    checks, uart_markers = shared_static_checks(candidate, manifest_path, ram_image, uart_log)
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    capabilities = manifest.get("capabilities", {})
    claims = manifest.get("completion_claims", {})
    checks.update({
        "uart_log_sha256_pinned": BASE.sha256(uart_log) == EXPECTED_UART_SHA256,
        "q1_management_identity": capabilities.get("management_ipv4") == "192.168.1.90"
        and capabilities.get("cgi_management_port") == 80,
        "q1_payloads_integrated_not_claimed_live":
            capabilities.get("realtek_v4_payload_integrated") is True
            and capabilities.get("quantenna_rxalign_payload_integrated") is True
            and claims == {"full_product": False, "oem_parity_100": False,
                           "radio2g": False, "radio5g": False},
        "q1_radio_credentials_fail_closed":
            capabilities.get("both_radios_fail_closed_without_credentials") is True,
        "q1_watchdog_disabled": capabilities.get("watchdog_enabled") is False,
    })
    return checks, uart_markers


BASE.static_checks = q1_static_checks


if __name__ == "__main__":
    raise SystemExit(BASE.main())
