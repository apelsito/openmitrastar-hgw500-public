#!/usr/bin/env python3
"""File-only F320 physical-gate contract. No port/network/process execution."""
from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import zlib

from build_f320_spi_control_firmware import (BASE, DEVICE, EXPECTED_CHANGES, MODULE_TARGET,
    FEATURE_TARGET, VERSION, verify_contract, sha)
from bootbase_contract_emulator import validate_bootbase_slot

EXPECTED_IMAGE = "66ff3e8f11a054595ab349e9863789f6422e2ea2253f1a8da01840a6eb43a1fa"
EXPECTED_MODULE = "6ec075b4875890d5f366ff568932b591b59cc15231282274d77bb868a768a06a"
EXPECTED_BYTES = 5292032
ROOT = Path(__file__).resolve().parents[1]


def inspect_candidate() -> dict:
    folder = DEVICE / "f320-device-bound"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="ascii"))
    module_dir = Path(manifest["source"]["module_manifest"]).parent
    module = verify_contract(module_dir)
    if sha(module_dir / "manifest.json") != manifest["source"]["module_manifest_sha256"]:
        raise ValueError("module manifest drift")
    if module["artifact"]["sha256"] != EXPECTED_MODULE:
        raise ValueError("different F320 module")
    candidate = folder / (BASE + ".webformat.bin")
    data = candidate.read_bytes()
    if sha(candidate) != EXPECTED_IMAGE or len(data) != EXPECTED_BYTES:
        raise ValueError("F320 image hash/size drift")
    if any(manifest.get(key) is not False for key in ("candidate_eligible", "flash_supported", "release_eligible")):
        raise ValueError("unexpected physical/release eligibility; this gate is deliberately offline")
    if set(manifest["change_scope"]["changed_paths"]) != EXPECTED_CHANGES:
        raise ValueError("unexpected candidate delta")
    for line in (folder / "SHA256SUMS").read_text(encoding="ascii").splitlines():
        expected, name = line.split("  ", 1)
        if Path(name).name != name or sha(folder / name) != expected:
            raise ValueError("candidate evidence hash changed")
    full = data + b"\xff" * (0x7a0000 - len(data))
    if f"{zlib.crc32(full) & 0xffffffff:08x}" != "f7e832d9":
        raise ValueError("F320 full-slot CRC mismatch")
    if any(byte != 255 for byte in full[0x5e0000:]):
        raise ValueError("candidate initializes store")
    # Existing independent Bootbase validator, not an acceptance label alone.
    contract = validate_bootbase_slot(str(candidate), data, 0x7a0000)
    if not contract.accepted_by_contract:
        raise ValueError("Bootbase contract rejected F320")
    return {"path": str(candidate), "sha256": EXPECTED_IMAGE, "bytes": EXPECTED_BYTES,
            "full_slot_crc32": "f7e832d9", "manifest_sha256": sha(folder / "manifest.json"),
            "module_sha256": EXPECTED_MODULE, "bootbase_contract": "PASS"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path)
    args = parser.parse_args()
    candidate = inspect_candidate()
    output = args.output_dir or ROOT / "outputs/preflight" / ("f320-spi-read-gate-" + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    plan = {
        "schema": "openmitrastar.f320-spi-read-gate/v1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "OFFLINE_PASS_PHYSICAL_NO_GO", "hardware_actions_performed": False,
        "candidate": candidate, "target": "HGW-500BNA-QCv2 A2 / 192.168.1.90",
        "runtime_version": VERSION, "module": "/" + MODULE_TARGET,
        "authorization": {"current": "PREPARATION_ONLY", "old_f319_ack_reusable": False,
                          "proposed_exact_ack": "OPENMITRASTAR_F320_MTD4_66FF3E8F"},
        "physical_executor": "tools/promote_f320_mtd4.ps1; separate source-bound qualification required",
        "physical_preconditions": [
            "Reviewed F320-specific executor/rollback and offline tests; no F319-hash bypass",
            "Exact F320 artifact authorization and manual HGW-only power-cycle contingency",
            "Fresh pinned F319 SSH followed by exclusive hardware guard and authenticated UART nonce",
            "Protected-partition and current F319 slot CRC verification before mtd4-only flash",
            "Verified historical F314 Bootbase restoration plus intact exact F314 artifacts",
            "Candidate boot/platform gates and no conflicting SPI module before bounded probe",
            "RX-only correlated UART ready before explicit execute_read=1 module load",
        ],
        "acceptance": [
            "Unique begin/end UART brackets and successful actual capture/process exit",
            "legacy_map_verified=Y, map_read_count=1, controller_read_count=1",
            "controller_write_count=0, transaction_provider_ready=N",
            "No access to SPI command apertures, flash content or protection controls",
            "Unchanged MTD table, no fatal markers, clean unload and management/radio regression",
        ],
        "recovery": {"normal_failure": "restore exact F314 after known completed write under retained guard",
                     "machine_check_or_hard_hang": "manual HGW-only power-cycle; reacquire identity before any UART reuse",
                     "partial_flash_failure": "stop and classify readback; no automatic alternate-image retry",
                     "mtd3_boot_proven": False},
        "address_scope": {"F319": "resource reservation at 0xe4030000 only; no bus read proof",
                          "F320": "read map bits at 0xe0000004, then at most one SPI control read at 0xe2000004",
                          "cause": "legacy/alias mismatch supported by OEM config and F319 DTB; exact F310 faulting access not proven"},
        "next_action": "Use the separately qualified F320 executor only with exact authority, power-cycle contingency and fresh binding; this file-only plan is not permission to execute",
    }
    (output / "plan.json").write_text(json.dumps(plan, indent=2) + "\n", encoding="ascii")
    print(json.dumps({"status": plan["status"], "plan": str(output / "plan.json"), "hardware_actions": False}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
