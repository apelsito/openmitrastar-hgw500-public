#!/usr/bin/env python3
"""Run the complete offline F315/F316 liberation contract."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
F315_DEVICE = Path.home() / ".openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f315-device-bound"
F316_NATIVE = ROOT / "outputs/kernel-port/f316-radar-native-20260905/manifest.json"
F316_CLASSIFIER = ROOT / "outputs/kernel-port/f316-radar-classifier-20260905/manifest.json"
RADIOD = ROOT / "outputs/userland/lyoko-radiod-arc700-20260905/manifest.json"
OUT = ROOT / "outputs/preflight/f315-f316-liberation-audit.json"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(script: str) -> None:
    result = subprocess.run(
        [sys.executable, str(ROOT / script)],
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise SystemExit(result.stderr or result.stdout)


def main() -> int:
    for test in (
        "tools/test_f315_oem_radar_oracle.py",
        "tools/test_f315_radar_shadow_offline.py",
        "tools/test_f315_radar_shadow_firmware.py",
        "tools/test_f316_classifier_offline.py",
        "tools/test_f316_radar_native_offline.py",
        "tools/test_f316_qdrv_dfs_contract.py",
        "tools/test_lyoko_radiod_arc700.py",
    ):
        run(test)

    f315 = json.loads((F315_DEVICE / "manifest.json").read_text(encoding="ascii"))
    native = json.loads(F316_NATIVE.read_text(encoding="ascii"))
    classifier = json.loads(F316_CLASSIFIER.read_text(encoding="ascii"))
    radiod = json.loads(RADIOD.read_text(encoding="ascii"))
    checks = {
        "f315_flash_candidate": f315["candidate_eligible"] is True and f315["flash_supported"] is True,
        "f315_kernel_preserved": f315["integration"]["f314_kernel_artifacts_byte_identical"] is True,
        "f315_shadow_no_callback": f315["radar_shadow"]["callback_invocations"] == 0,
        "f316_classifier": classifier["status"] == "PASS",
        "f316_selector": classifier["lanes"]["candidate_selector"] == "PASS_DATA_DRIVEN_ROUTE",
        "f316_postfilter": classifier["lanes"]["postfilter"] == "PASS_CALLBACK_ELIGIBILITY_ONLY",
        "f316_native_provider": native["status"] == "PASS" and len(native["provider"]["exports"]) == 18,
        "f316_qdrv_external_link": native["qdrv"]["external_provider_link"] == "PASS",
        "f316_authority_default_off": native["runtime_defaults"]["authoritative_enable"] is False,
        "f317_policy_engine": radiod["status"] == "PASS" and radiod["binary"]["static"] is True,
        "uart_unused": all(
            item["hardware_actions"]["uart"] is False
            for item in (native, classifier, radiod)
        ),
    }
    result = {
        "schema": "openmitrastar.f315-f316-liberation-audit/v1",
        "date": "2026-09-05",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "artifacts": {
            "f315_candidate_sha256": f315["artifacts"]["webformat"]["sha256"],
            "f316_provider_sha256": native["provider"]["sha256"],
            "f316_classifier_sha256": classifier["artifact"]["sha256"],
            "lyoko_radiod_sha256": radiod["binary"]["sha256"],
        },
        "physical": {
            "f315_installed": False,
            "f315_shadow_capture": False,
            "f316_active_dfs": False,
            "reason": "UART reserved for another device; no router mutation performed",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
