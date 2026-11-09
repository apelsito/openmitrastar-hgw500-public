#!/usr/bin/env python3
"""Verify exact TX10 RAM-only boot evidence before the client traffic gate."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any


EXPECTED_IMAGE_NAME = os.environ.get("OM_W2_2G_EXPECTED_IMAGE_NAME", "linux510-w2-2g-parity-tx10-controls-v1-RAM-TEST-NO-FLASH.bin")
EXPECTED_SHA256 = os.environ.get("OM_W2_2G_EXPECTED_IMAGE_SHA256", "998510e1aeabef6e51f953c33533a9b714251dbb5b52062d5eaa112aa431e7ee")
EXPECTED_BYTES = int(os.environ.get("OM_W2_2G_EXPECTED_IMAGE_BYTES", "4331206"))
EXPECTED_CLASSIFICATION_TOKEN = os.environ.get("OM_W2_2G_EXPECTED_BOOT_CLASSIFICATION_TOKEN", "RAM-ONLY-TX10")
EXPECTED_SSID = "OpenMitraStar-2G-DIAG"
EXPECTED_TXBD_QUEUES = [f"q{idx}" for idx in range(9)]
SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(password|passwd|wpa_passphrase|psk)\s*[:=]\s*[^,\s}\]]+"),
]


def image_name(value: object) -> str:
    return Path(str(value).replace("\\", "/")).name


def false_like(value: Any) -> bool:
    return value is False or value in (0, "false", "False", "0", None)


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    args = parser.parse_args(argv)
    checks: list[dict[str, object]] = []

    def check(check_id: str, ok: bool, detail: object) -> None:
        checks.append({"id": check_id, "ok": bool(ok), "detail": str(detail)})

    if not args.evidence.is_file():
        check("evidence.exists", False, args.evidence)
        print(json.dumps({"schema": "openmitrastar.w2-tx10-boot-evidence-verifier/v1", "ok": False, "status": "TX10_BOOT_EVIDENCE_REJECTED", "failed_checks": ["evidence.exists"], "checks": checks}, indent=2, sort_keys=True))
        return 2

    raw = args.evidence.read_text(encoding="utf-8", errors="replace")
    try:
        evidence = json.loads(raw)
        check("evidence.json", True, "JSON parsed")
    except json.JSONDecodeError as exc:
        evidence = {}
        check("evidence.json", False, exc)

    observed = evidence.get("observed") if isinstance(evidence.get("observed"), dict) else {}
    image = evidence.get("image") if isinstance(evidence.get("image"), dict) else {}
    txbd = observed.get("txbd_layout") if isinstance(observed.get("txbd_layout"), dict) else {}
    members = {str(item) for item in observed.get("bridge_members", [])} if isinstance(observed.get("bridge_members"), list) else set()
    safety = observed.get("safety_findings") if isinstance(observed.get("safety_findings"), list) else []
    classification = str(evidence.get("classification", ""))

    check("schema", evidence.get("schema") == "openmitrastar.w2-2g-client-evidence/v1", evidence.get("schema"))
    check("classification.expected_token", EXPECTED_CLASSIFICATION_TOKEN in classification, classification)
    check("classification.no_flash", "NO-FLASH" in classification, classification)
    check("image.name", image_name(image.get("path", "")) == EXPECTED_IMAGE_NAME, image.get("path"))
    check("image.sha256", image.get("sha256") == EXPECTED_SHA256, image.get("sha256"))
    check("image.bytes", image.get("bytes") == EXPECTED_BYTES, image.get("bytes"))
    check("mutations.false", false_like(evidence.get("mutations")), evidence.get("mutations"))
    check("flash.false", false_like(evidence.get("flash")), evidence.get("flash"))
    check("boot_state.present", bool(str(observed.get("boot_state", "")).strip()), observed.get("boot_state"))
    check("radio.ready", observed.get("radio_state") == "ready", observed.get("radio_state"))
    check("hostapd.enabled", observed.get("hostapd_state") == "ENABLED" and evidence.get("hostapd_stable") is True, observed.get("hostapd_state"))
    check("ssid", observed.get("ssid") == EXPECTED_SSID, observed.get("ssid"))
    check("channel", observed.get("channel") == 1, observed.get("channel"))
    check("bridge", evidence.get("bridge_eth0_wlan0") is True and {"eth0", "wlan0"}.issubset(members), sorted(members))
    check("irq20.progress", observed.get("irq20_progress") is True, observed.get("irq20_progress"))
    check("irq28.progress", evidence.get("irq28_progress") is True and int(observed.get("irq28_after") or 0) > int(observed.get("irq28_before") or 0), f"{observed.get('irq28_before')}->{observed.get('irq28_after')}")
    check("netdev.errors_zero", int(evidence.get("netdev_errors_delta") or 0) == 0, evidence.get("netdev_errors_delta"))
    check("kernel.no_oops", evidence.get("no_kernel_oops") is True and safety == [], safety)
    for queue in EXPECTED_TXBD_QUEUES:
        value = str(txbd.get(queue, ""))
        check(f"txbd.{queue}.global32", "stride32" in value and "compact=1" in value, value)
    serialized = json.dumps(evidence, sort_keys=True)
    check("secrets.absent", not any(pattern.search(serialized) for pattern in SECRET_PATTERNS), "secret patterns absent")

    failed = [item["id"] for item in checks if not item["ok"]]
    result = {
        "schema": "openmitrastar.w2-tx10-boot-evidence-verifier/v1",
        "classification": "READONLY-TX10-BOOT-EVIDENCE-VERIFIER-NO-HARDWARE",
        "ok": not failed,
        "status": "TX10_BOOT_EVIDENCE_ACCEPTED" if not failed else "TX10_BOOT_EVIDENCE_REJECTED",
        "evidence": str(args.evidence),
        "image": {"name": image_name(image.get("path", "")), "sha256": image.get("sha256"), "bytes": image.get("bytes")},
        "failed_checks": failed,
        "checks": checks,
        "mutations": False,
        "flash": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
