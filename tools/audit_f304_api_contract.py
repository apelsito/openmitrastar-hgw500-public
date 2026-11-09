#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from datetime import datetime, timezone


ROOT = Path(__file__).resolve().parents[1]
DEVICE = "hgw500bna-qcv2-a2-primary"
FIRMWARE = Path.home() / ".openmitrastar/devices" / DEVICE / "firmware"
F301 = FIRMWARE / "f301-device-bound"
F304 = FIRMWARE / "f304-device-bound"
API = ROOT / "versions/lyoko-foundation-6.7.1-f304-api-contract/overlay/usr/libexec/openmitrastar/om-api-v1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    f301 = json.loads((F301 / "manifest.json").read_text(encoding="ascii"))
    f304 = json.loads((F304 / "manifest.json").read_text(encoding="ascii"))
    source = API.read_text(encoding="utf-8")

    checks = {
        "f301_is_installed_baseline": f301["artifacts"]["webformat"]["sha256"] == "4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262",
        "f304_is_offline": f304["physical_validation"]["status"] == "NOT_RUN",
        "f304_flash_disabled": f304["candidate_eligible"] is False and f304["flash_supported"] is False,
        "rootfs_diff_api_only": set(f304["foundation_assets"]["rootfs_diff"]["changed_paths"]) == {"etc/openmitrastar/release", "usr/libexec/openmitrastar/om-api-v1"},
        "kernel_unchanged": f304["artifacts"]["kernel_lzma"]["sha256"] == f301["artifacts"]["kernel_lzma"]["sha256"],
        "radio_payload_unchanged": f304["integration"]["radio_payload_byte_identical_to_f301"] is True,
        "canonical_patch": 'PATCH) stage_radio_config "$band"' in source,
        "legacy_stage_alias": "radios/2g/stage|radios/5g/stage)" in source,
        "dynamic_rootfs_size": "rootfs_bytes=$(mtd_named_bytes rootfs_live)" in source and "rootfs_live_bytes\":6422528" not in source,
        "dfs_fail_closed": "dfs-radar-backend-unavailable" in source,
        "no_firmware_write_api": '"firmware_write_api":false' in source,
        "no_persistent_config_writes": '"persistent_config_writes":false' in source,
        "no_persistent_package_writes": '"persistent_package_writes":false' in source,
        "no_dangerous_write_tools": not any(token in source for token in ("flash_erase", "mtd_debug", "nandwrite", "fw_setenv")),
    }

    classifications = [
        {"area": "GET /api/v1/status", "f301": "implemented", "f304": "implemented"},
        {"area": "GET /api/v1/network", "f301": "implemented", "f304": "implemented"},
        {"area": "GET /api/v1/radios/{id}", "f301": "implemented", "f304": "implemented"},
        {"area": "PATCH /api/v1/radios/{id}", "f301": "functional-different-contract", "f304": "implemented"},
        {"area": "GET /api/v1/clients", "f301": "implemented-redacted", "f304": "implemented-redacted"},
        {"area": "GET /api/v1/hardware", "f301": "implemented-hardware-limited", "f304": "implemented-hardware-limited"},
        {"area": "GET /api/v1/diagnostics", "f301": "implemented", "f304": "implemented"},
        {"area": "GET /api/v1/privacy", "f301": "implemented-policy-implicit", "f304": "implemented-explicit"},
        {"area": "GET /api/v1/firmware", "f301": "functional-stale-rootfs-size", "f304": "implemented-dynamic-mtd"},
        {"area": "POST /api/v1/config/apply", "f301": "implemented-hardware-gated-volatile", "f304": "implemented-hardware-gated-volatile"},
        {"area": "POST /api/v1/config/rollback", "f301": "implemented-hardware-gated-volatile", "f304": "implemented-hardware-gated-volatile"},
        {"area": "package catalog/query", "f301": "implemented", "f304": "implemented"},
        {"area": "package install/remove", "f301": "implemented-feature-gated-ram-only", "f304": "implemented-feature-gated-ram-only-explicit"},
        {"area": "DFS mutation", "f301": "blocked-by-hardware", "f304": "blocked-by-hardware"},
        {"area": "persistent config/package writes", "f301": "absent-by-policy", "f304": "absent-explicit"},
        {"area": "firmware update API", "f301": "absent-by-policy", "f304": "absent-explicit"},
    ]

    result = {
        "schema": "openmitrastar.f304-api-offline-audit/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if all(checks.values()) else "FAIL",
        "base": {
            "version": "F301",
            "sha256": f301["artifacts"]["webformat"]["sha256"],
        },
        "candidate": {
            "version": "F304",
            "path": str(F304 / f304["artifacts"]["webformat"]["file"]),
            "bytes": f304["artifacts"]["webformat"]["bytes"],
            "sha256": f304["artifacts"]["webformat"]["sha256"],
            "rootfs_sha256": f304["artifacts"]["rootfs_squashfs"]["sha256"],
            "api_sha256": sha256(API),
            "hardware_status": "NOT_RUN",
            "candidate_eligible": False,
            "flash_supported": False,
        },
        "classifications": classifications,
        "checks": checks,
        "hardware_actions": {"ssh": False, "uart": False, "tftp": False, "radio": False, "flash": False, "mtd": False},
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    target = args.output_dir / "audit.json"
    target.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")
    print(json.dumps({"status": result["status"], "output": str(target), "checks": len(checks)}, indent=2))
    return 0 if result["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
