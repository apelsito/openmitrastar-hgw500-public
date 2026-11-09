#!/usr/bin/env python3
"""Offline preflight for the F66 persistent 2.4 GHz queue-guard candidate.

This verifier does not open UART, start TFTP, SSH to the router, reboot, or
flash anything. It folds the F66 artifact checks into one machine-readable
gate that can be run before handing control to Bootbase automation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "work/mission-state/q3-persistent-composite-f66-2g-queue-guard/build"
BASE = "openmitrastar-linux510-q3-persistent-f66-2g-autorate-reclaim-LZMA-OFFLINE-NO-FLASH"
WEB = BUILD / f"{BASE}.webformat.bin"
TFTP_COPY = ROOT / "work/tftp/omvl" / f"{BASE}.webformat.bin"
MANIFEST = BUILD / "manifest.json"
CONTRACT = BUILD / "bootbase-contract.json"
PATCH_REPORT = BUILD / "f66-fixed-size-patch-report.json"
SHA256SUMS = BUILD / "SHA256SUMS"
LOADER = BUILD / "om-radio-modules.fixedsize"
FLASH_WRAPPER = ROOT / "tools/flash_f66_2g_qguard.ps1"
WATCH_WRAPPER = ROOT / "tools/watch_flash_f66_2g_qguard_until_bootbase.ps1"

EXPECTED_WEB_SHA256 = "021cd4896ee54db95addd3b3c4111eb811b2dcf77a69c87b28b94dd4bec4b341"
EXPECTED_WEB_BYTES = 5_613_197
EXPECTED_SLOT_BYTES = 7_995_392
EXPECTED_CURRENT_LIVE_CRC32 = "26523198"
KNOWN_CURRENT_LIVE_CRC32 = {"26523198", "9f2a3ac5", "faee4019", "b05e9b7b", "aba558f3"}
EXPECTED_FLASH_ACK = "OPENMITRASTAR_Q3_F66_2G_AUTORATE_RECLAIM_MTD4_FLASH_021CD489"
EXPECTED_SUPERVISOR_ACK = "OPENMITRASTAR_AELITA_RECOVER_UART_FLASH_F66_RECLAIM_021CD489"
REQUIRED_LOADER_MARKERS = (
    "hgw500_tx_reclaim_poll=1",
    "hgw500_tx_queue_guard=N",
    "hgw500_tx_reclaim_poll=Y",
    "profile=all64-autorate-eapol-mgntq-reclaim",
    "hgw500_force_data_mcs7=0",
    "hgw500_force_data_mcs7=N",
    "hgw500_txbd_be_data_split=1",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def add_check(checks: list[dict[str, Any]], name: str, ok: bool, detail: Any = "") -> None:
    checks.append({"name": name, "ok": bool(ok), "detail": detail})


def parse_sha256sums(path: Path) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for line in path.read_text(encoding="ascii").splitlines():
        if not line.strip():
            continue
        match = re.fullmatch(r"([0-9a-f]{64})\s{2}(.+)", line.strip())
        if not match:
            raise ValueError(f"bad SHA256SUMS line: {line!r}")
        parsed[match.group(2)] = match.group(1)
    return parsed


def extract_default_crc32(text: str) -> str | None:
    match = re.search(r'\[string\]\$CurrentLiveCrc32\s*=\s*"([0-9a-fA-F]{8})"', text)
    return match.group(1).lower() if match else None


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current-live-crc32", default="26523198")
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    current_live_crc32 = args.current_live_crc32.lower()

    checks: list[dict[str, Any]] = []
    required = (WEB, TFTP_COPY, MANIFEST, CONTRACT, PATCH_REPORT, SHA256SUMS, LOADER, FLASH_WRAPPER, WATCH_WRAPPER)
    for path in required:
        add_check(checks, f"exists:{path.relative_to(ROOT).as_posix()}", path.is_file())

    manifest = load_json(MANIFEST) if MANIFEST.is_file() else {}
    contract = load_json(CONTRACT) if CONTRACT.is_file() else {}
    report = load_json(PATCH_REPORT) if PATCH_REPORT.is_file() else {}
    web_sha = sha256(WEB) if WEB.is_file() else None
    tftp_sha = sha256(TFTP_COPY) if TFTP_COPY.is_file() else None
    loader_sha = sha256(LOADER) if LOADER.is_file() else None
    loader_text = LOADER.read_text(encoding="utf-8") if LOADER.is_file() else ""
    flash_text = FLASH_WRAPPER.read_text(encoding="utf-8") if FLASH_WRAPPER.is_file() else ""
    watch_text = WATCH_WRAPPER.read_text(encoding="utf-8") if WATCH_WRAPPER.is_file() else ""

    add_check(checks, "web.sha256", web_sha == EXPECTED_WEB_SHA256, web_sha)
    add_check(checks, "web.bytes", WEB.is_file() and WEB.stat().st_size == EXPECTED_WEB_BYTES, WEB.stat().st_size if WEB.is_file() else None)
    add_check(checks, "tftp.copy.matches", tftp_sha == web_sha == EXPECTED_WEB_SHA256, {"web": web_sha, "tftp": tftp_sha})
    add_check(checks, "slot.fits", manifest.get("slot", {}).get("fits") is True and manifest.get("slot", {}).get("bytes") == EXPECTED_SLOT_BYTES, manifest.get("slot"))
    add_check(checks, "manifest.schema", manifest.get("schema") == "openmitrastar.q3-persistent-composite-f66/v1", manifest.get("schema"))
    add_check(checks, "manifest.classification", manifest.get("classification") == "F66_FIXED_SIZE_FROM_F65_2G_AUTORATE_RECLAIM", manifest.get("classification"))
    add_check(checks, "manifest.security.no_hardware", manifest.get("security") == {"flash": False, "opens_uart": False, "touches_router": False}, manifest.get("security"))
    add_check(checks, "manifest.webformat.identity", manifest.get("artifacts", {}).get("webformat", {}).get("sha256") == web_sha and manifest.get("artifacts", {}).get("webformat", {}).get("bytes") == EXPECTED_WEB_BYTES, manifest.get("artifacts", {}).get("webformat"))
    add_check(checks, "bootbase.result", contract.get("result") == "PASS", contract.get("result"))
    add_check(checks, "bootbase.candidate.accepted", contract.get("candidate", {}).get("accepted_by_contract") is True, contract.get("candidate", {}).get("accepted_by_contract"))
    add_check(checks, "bootbase.candidate.identity", contract.get("candidate", {}).get("sha256") == web_sha and contract.get("candidate", {}).get("size") == EXPECTED_WEB_BYTES, contract.get("candidate", {}))
    add_check(checks, "patch.report.no_hardware", report.get("hardware_actions") is False and report.get("flash_supported") is False, {"hardware_actions": report.get("hardware_actions"), "flash_supported": report.get("flash_supported")})
    add_check(checks, "patch.report.webformat.identity", report.get("webformat_sha256") == web_sha and report.get("webformat_crc32") == manifest.get("artifacts", {}).get("webformat", {}).get("crc32"), {"sha256": report.get("webformat_sha256"), "crc32": report.get("webformat_crc32")})
    add_check(checks, "loader.sha256", report.get("loader_sha256") == loader_sha, {"report": report.get("loader_sha256"), "actual": loader_sha})
    add_check(checks, "loader.size.fixed", report.get("compact_loader_size", 0) <= report.get("old_loader_size", -1) and report.get("padding_bytes") == report.get("old_loader_size", 0) - report.get("compact_loader_size", 0), {"compact": report.get("compact_loader_size"), "old": report.get("old_loader_size"), "padding": report.get("padding_bytes")})
    missing_markers = [marker for marker in REQUIRED_LOADER_MARKERS if marker not in loader_text]
    add_check(checks, "loader.markers", not missing_markers, missing_markers)
    marker_report = report.get("markers", {})
    add_check(checks, "patch.report.markers", marker_report.get("autorate") is True and marker_report.get("mcs7") is False and marker_report.get("queue_guard") is False and marker_report.get("queue_guard_disabled") is True and all(marker_report.get(key) is True for key in ("be_data_split", "reclaim_poll")), marker_report)

    try:
        sums = parse_sha256sums(SHA256SUMS)
        sums_ok = True
        sums_detail: dict[str, Any] = {}
        for rel, expected in sums.items():
            target = BUILD / rel
            actual = sha256(target) if target.is_file() else None
            if actual != expected:
                sums_ok = False
                sums_detail[rel] = {"expected": expected, "actual": actual}
        add_check(checks, "sha256sums.all_match", sums_ok, sums_detail or {"entries": len(sums)})
    except Exception as exc:
        add_check(checks, "sha256sums.parse", False, repr(exc))

    wrapper_default_crc32 = extract_default_crc32(flash_text)
    add_check(checks, "current_live_crc32.known", current_live_crc32 in KNOWN_CURRENT_LIVE_CRC32, current_live_crc32)
    add_check(checks, "flash.wrapper.default_crc32.current", wrapper_default_crc32 == EXPECTED_CURRENT_LIVE_CRC32, wrapper_default_crc32)
    add_check(checks, "flash.wrapper.pinned_candidate", EXPECTED_WEB_SHA256 in flash_text and str(EXPECTED_WEB_BYTES) in flash_text and EXPECTED_FLASH_ACK in flash_text, "hash/bytes/ack")
    add_check(checks, "watch.wrapper.pinned_candidate", EXPECTED_WEB_SHA256 in watch_text and "f66-2g-autorate-reclaim" in watch_text, "hash/name")
    add_check(checks, "watch.wrapper.current_crc_passthrough", '"-CurrentLiveCrc32", $CurrentLiveCrc32' in watch_text, "passthrough")
    add_check(checks, "supervisor.ack.expected", EXPECTED_SUPERVISOR_ACK == "OPENMITRASTAR_AELITA_RECOVER_UART_FLASH_F66_RECLAIM_021CD489", EXPECTED_SUPERVISOR_ACK)

    ok = all(item["ok"] for item in checks)
    payload = {
        "schema": "openmitrastar.f66-offline-preflight/v1",
        "status": "PASS" if ok else "FAIL",
        "candidate": {
            "path": str(WEB.relative_to(ROOT)),
            "bytes": WEB.stat().st_size if WEB.is_file() else None,
            "sha256": web_sha,
            "expected_sha256": EXPECTED_WEB_SHA256,
        },
        "tftp_copy": {
            "path": str(TFTP_COPY.relative_to(ROOT)),
            "sha256": tftp_sha,
        },
        "current_live_crc32": current_live_crc32,
        "wrapper_default_current_live_crc32": wrapper_default_crc32,
        "flash": False,
        "router_mutations": False,
        "opens_uart": False,
        "checks": checks,
    }
    output = args.output or (BUILD / "f66-offline-preflight.json")
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    print(f"OMF66_OFFLINE_PREFLIGHT_RESULT={output}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
