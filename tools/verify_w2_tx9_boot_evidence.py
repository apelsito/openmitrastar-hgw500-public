#!/usr/bin/env python3
"""Verify exact TX9 RAM-only boot evidence before arming the live client gate."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any


EXPECTED_IMAGE_NAME = "linux510-w2-2g-parity-tx9-global32-rx-unaligned-v1-RAM-TEST-NO-FLASH.bin"
EXPECTED_SHA256 = "cf101c61314a446203b3e581d00f6b32b3111bfd81bc6c2d178f526cd5c1da8a"
EXPECTED_BYTES = 4_329_980
EXPECTED_SSID = "OpenMitraStar-2G-DIAG"
EXPECTED_CHANNEL = 1
EXPECTED_TXBD_QUEUES = [f"q{idx}" for idx in range(9)]

SECRET_PATTERNS = [
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"(?i)\b(password|passwd|wpa_passphrase|psk)\s*[:=]\s*[^,\s}\]]+"),
]


def nested(data: dict[str, Any], path: str, default: Any = None) -> Any:
    current: Any = data
    for part in path.split("."):
        if not isinstance(current, dict) or part not in current:
            return default
        current = current[part]
    return current


def is_false(value: Any) -> bool:
    return value is False or value in (0, "false", "False", "0", None)


def image_name(path_text: str) -> str:
    return Path(path_text.replace("\\", "/")).name


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("evidence", type=Path)
    parser.add_argument("--expected-sha256", default=EXPECTED_SHA256)
    parser.add_argument("--expected-bytes", type=int, default=EXPECTED_BYTES)
    parser.add_argument("--expected-image-name", default=EXPECTED_IMAGE_NAME)
    args = parser.parse_args(argv)

    checks: list[dict[str, object]] = []

    def check(check_id: str, ok: bool, detail: str) -> None:
        checks.append({"id": check_id, "ok": bool(ok), "detail": detail})

    if not args.evidence.is_file():
        check("evidence.exists", False, str(args.evidence))
        result = {
            "schema": "openmitrastar.w2-tx9-boot-evidence-verifier/v1",
            "ok": False,
            "status": "TX9_BOOT_EVIDENCE_REJECTED",
            "checks": checks,
            "failed_checks": ["evidence.exists"],
        }
        print(json.dumps(result, indent=2, sort_keys=True))
        return 2

    raw = args.evidence.read_text(encoding="utf-8", errors="replace")
    try:
        evidence = json.loads(raw)
    except json.JSONDecodeError as exc:
        check("evidence.json", False, str(exc))
        evidence = {}
    else:
        check("evidence.json", True, "JSON parsed")

    serialized = json.dumps(evidence, sort_keys=True)
    secret_hits = [pattern.pattern for pattern in SECRET_PATTERNS if pattern.search(serialized)]

    observed = evidence.get("observed") if isinstance(evidence.get("observed"), dict) else {}
    txbd = observed.get("txbd_layout") if isinstance(observed.get("txbd_layout"), dict) else {}
    bridge_members = observed.get("bridge_members") if isinstance(observed.get("bridge_members"), list) else []
    safety_findings = observed.get("safety_findings") if isinstance(observed.get("safety_findings"), list) else []
    image = evidence.get("image") if isinstance(evidence.get("image"), dict) else {}

    check("schema", evidence.get("schema") == "openmitrastar.w2-2g-client-evidence/v1", str(evidence.get("schema")))
    classification = str(evidence.get("classification", ""))
    check("classification.tx9", "RAM-ONLY-TX9" in classification, classification)
    check("classification.no_flash", "NO-FLASH" in classification, classification)
    check("image.sha256", image.get("sha256") == args.expected_sha256, str(image.get("sha256")))
    check("image.bytes", image.get("bytes") == args.expected_bytes, str(image.get("bytes")))
    check("image.name", image_name(str(image.get("path", ""))) == args.expected_image_name, str(image.get("path")))
    check("mutations.false", is_false(evidence.get("mutations")), repr(evidence.get("mutations")))
    check("flash.false", is_false(evidence.get("flash")), repr(evidence.get("flash")))
    check("hostapd.stable", evidence.get("hostapd_stable") is True, repr(evidence.get("hostapd_stable")))
    check("bridge.eth0_wlan0", evidence.get("bridge_eth0_wlan0") is True, repr(evidence.get("bridge_eth0_wlan0")))
    check("bridge.members", {"eth0", "wlan0"}.issubset({str(item) for item in bridge_members}), repr(bridge_members))
    check("ssid", observed.get("ssid") == EXPECTED_SSID, str(observed.get("ssid")))
    check("channel", observed.get("channel") == EXPECTED_CHANNEL, str(observed.get("channel")))
    check("radio.ready", observed.get("radio_state") == "ready", str(observed.get("radio_state")))
    check("hostapd.enabled", observed.get("hostapd_state") == "ENABLED", str(observed.get("hostapd_state")))
    check("irq20.progress", observed.get("irq20_progress") is True, repr(observed.get("irq20_progress")))
    check("irq28.progress", evidence.get("irq28_progress") is True, repr(evidence.get("irq28_progress")))
    check("irq28.counter_progress", int(observed.get("irq28_after") or 0) > int(observed.get("irq28_before") or 0), f"{observed.get('irq28_before')}->{observed.get('irq28_after')}")
    check("netdev.errors_zero", int(evidence.get("netdev_errors_delta") or 0) == 0, str(evidence.get("netdev_errors_delta")))
    check("kernel.no_oops", evidence.get("no_kernel_oops") is True, repr(evidence.get("no_kernel_oops")))
    check("safety.empty", safety_findings == [], repr(safety_findings))

    for queue in EXPECTED_TXBD_QUEUES:
        value = str(txbd.get(queue, ""))
        check(f"txbd.{queue}.stride32", "stride32" in value, value)
        check(f"txbd.{queue}.compact1", "compact=1" in value, value)

    check("client.not_required", True, "client association is evaluated by the subsequent live traffic gate")
    check("secrets.absent", not secret_hits, "no private key/password/PSK patterns in evidence JSON")

    failed = [item["id"] for item in checks if not item["ok"]]
    result = {
        "schema": "openmitrastar.w2-tx9-boot-evidence-verifier/v1",
        "classification": "READONLY-TX9-BOOT-EVIDENCE-VERIFIER-NO-HARDWARE",
        "ok": not failed,
        "status": "TX9_BOOT_EVIDENCE_ACCEPTED" if not failed else "TX9_BOOT_EVIDENCE_REJECTED",
        "evidence": str(args.evidence),
        "image": {
            "name": image_name(str(image.get("path", ""))),
            "sha256": image.get("sha256"),
            "bytes": image.get("bytes"),
        },
        "failed_checks": failed,
        "checks": checks,
        "mutations": False,
        "flash": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if not failed else 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
