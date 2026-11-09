#!/usr/bin/env python3
"""Offline v6.1 contract for the Quantenna scheduler diagnostic lane.

This module does not contact the router and does not create any flashable
image.  It only pins the exact v6 qdrv artifact and provides a small adapter
for wrappers that stage RAM-only 5 GHz tests.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V6_DIR = ROOT / "outputs/kernel-port/quantenna-5g-v6-scheduler-diag"
QDRV = V6_DIR / "qdrv-v6-scheduler-diag.ko"
START = V6_DIR / "om-radio5-start-v6-scheduler-diag"
STOP = V6_DIR / "om-radio5-stop-v6-scheduler-diag"
EVALUATOR = V6_DIR / "evaluate-v6-scheduler-diag.py"
MANIFEST = V6_DIR / "manifest.json"

QDRV_SHA256 = "ba49438c9af9be2058a91704a25571e1d314ef345640f9fe5ccdba66cfa2646e"
START_SHA256 = "6ae7242e7d9bf17587711dff71ff1f97355547a13e0e01a80fda319602feed4f"
STOP_SHA256 = "26d34dc42c55348003dc90baed35c6c50d5ad628ed6dd4217b8b9fd3097c5207"
EVALUATOR_SHA256 = "a3ccd5cccc7983fccdc24f4cfe4da7750c55626ac74d80b5074cc152a42532d1"
MANIFEST_SHA256 = "f234020bfdb69594fd53159cc5a8e52ba5678e2e05cdf08b410edc81236e7fc2"

# The v6 start script reuses the known-good assoc trace control profile.  The
# loaded qdrv module is still pinned separately to QDRV_SHA256 through
# artifacts.sha256 and SAFE_MODULES.
QDRV_PROFILE_SHA256 = "a4a4e277bf815e8b408594d67a1d1afcec03251af5bc4d05b51567abbb41ef33"

OUTPUT_DIR = ROOT / "outputs/kernel-port/quantenna-5g-v6.1-scheduler-contract-20260824"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"hash mismatch for {path}: {actual} != {expected}")


def verify_inputs() -> dict[str, object]:
    for path, expected in (
        (QDRV, QDRV_SHA256),
        (START, START_SHA256),
        (STOP, STOP_SHA256),
        (EVALUATOR, EVALUATOR_SHA256),
        (MANIFEST, MANIFEST_SHA256),
    ):
        _require_hash(path, expected)

    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if manifest.get("schema") != "openmitrastar.qtn-5g-v6-scheduler-diag/v1":
        raise RuntimeError("v6 manifest schema mismatch")
    if manifest.get("classification") != "RAM-ONLY-INSTRUMENTATION-NO-FLASH":
        raise RuntimeError("v6 manifest classification mismatch")
    if any(manifest.get(flag) for flag in ("flash", "mtd", "bootenv", "hardware_tested")):
        raise RuntimeError("v6 manifest must remain offline/no-flash/no-hardware")
    if manifest["artifacts"]["qdrv"]["sha256"] != QDRV_SHA256:
        raise RuntimeError("v6 manifest qdrv hash mismatch")

    start_text = START.read_text(encoding="utf-8")
    for marker in (
        "openmitrastar_tx_path_trace_enable=1",
        "/usr/sbin/iwpriv-qtn wifi0 auc_tx 0",
        "Q3_RADIO5_BEACON_LIFETIME=1",
        "OMQTN5G_ISOLATED_L3",
        "[ ! -e /sys/class/net/br0/brif/wifi0 ]",
    ):
        if marker not in start_text:
            raise RuntimeError(f"v6 start contract missing: {marker}")
    for forbidden in ("flash_erase", "mtd_debug", "fw_setenv", "brctl addif br0 wifi0"):
        if forbidden in start_text:
            raise RuntimeError(f"v6 start contains forbidden primitive: {forbidden}")

    return manifest


def apply_to_runner(qtn_runner) -> dict[str, object]:
    """Patch a loaded run_qtn_w3_tx7_client_traffic module for v6.1 staging."""
    manifest = verify_inputs()
    qtn_runner.QDRV_SHA256 = QDRV_SHA256
    qtn_runner.QDRV_PROFILE_SHA256 = QDRV_PROFILE_SHA256
    qtn_runner.SAFE_MODULES["qdrv.ko"] = (QDRV, QDRV_SHA256)
    qtn_runner.SAFE_START = (START, START_SHA256)
    qtn_runner.SAFE_STOP = (STOP, STOP_SHA256)
    return contract_manifest(manifest)


def capture_minimum() -> list[dict[str, str]]:
    return [
        {"stage": "capture-ready", "source": "uart-events.jsonl", "gate": "ready or reconnected before qdrv-load-begin"},
        {"stage": "qdrv-load-begin", "source": "uart.log", "gate": "OMQTN5G_RUN marker present before qdrv load"},
        {"stage": "enqueue", "source": "uart.log", "gate": "same skb; mgmt=1 for AUTH/ASSOC response path"},
        {"stage": "enqueue-result", "source": "uart.log", "gate": "same skb; rc and queue state captured"},
        {"stage": "dequeue-ready", "source": "uart.log", "gate": "same skb; descriptor counts captured"},
        {"stage": "hardstart", "source": "uart.log", "gate": "same skb; first missing transition if absent"},
        {"stage": "desc-ready", "source": "uart.log", "gate": "same skb; establish hd_pa identity"},
        {"stage": "mailbox-enter", "source": "uart.log", "gate": "same skb and same hd_pa"},
        {"stage": "mailbox-published", "source": "uart.log", "gate": "same skb and same hd_pa"},
        {"stage": "txdone", "source": "uart.log", "gate": "same skb and same hd_pa"},
        {"stage": "rollback-or-recovery", "source": "uart.log + post-recovery.json", "gate": "terminal state not inferred without evidence"},
    ]


def contract_manifest(source_manifest: dict[str, object] | None = None) -> dict[str, object]:
    source_manifest = source_manifest or verify_inputs()
    return {
        "schema": "openmitrastar.qtn-5g-v6.1-scheduler-contract/v1",
        "date": "2026-08-24",
        "classification": "OFFLINE-CONTRACT-ONLY-NO-HARDWARE-NO-FLASH",
        "source_schema": source_manifest["schema"],
        "qdrv_artifact_sha256": QDRV_SHA256,
        "qdrv_profile_sha256": QDRV_PROFILE_SHA256,
        "wrapper_acceptance": {
            "runner_qdrv_sha256": QDRV_SHA256,
            "runner_qdrv_profile_sha256": QDRV_PROFILE_SHA256,
            "runner_safe_start_sha256": START_SHA256,
            "runner_safe_stop_sha256": STOP_SHA256,
            "profile_separation_required": True,
            "reason": "v6 is an instrumented qdrv artifact; the start script keeps the assoc-trace functional profile while artifacts.sha256 pins the loaded module exactly",
        },
        "expected_chain": source_manifest["expected_chain"],
        "correlation": source_manifest["correlation"],
        "capture_minimum": capture_minimum(),
        "required_terminal_states": [
            "PASS_COMMITTED",
            "FAIL_ROLLED_BACK",
            "FAIL_RECOVERED_AFTER_REBOOT",
            "FAIL_RECOVERY_UNPROVEN",
            "CAPTURE_INVALID",
        ],
        "product_integration": {
            "enabled_service": False,
            "init_product_change": False,
            "diagnostic_only": True,
        },
        "safety": {
            "router_accessed_now": False,
            "uart_used_now": False,
            "network_used_now": False,
            "flash": False,
            "mtd": False,
            "bootenv": False,
            "reboot": False,
        },
    }


def write_capture_plan(path: Path) -> None:
    lines = [
        "# Quantenna v6.1 scheduler diagnostic - minimum UART/OOB capture",
        "",
        "This is not an execution authorization. It is the offline contract for the next hardware run.",
        "",
        "## Candidate",
        "",
        f"- qdrv artifact SHA256: `{QDRV_SHA256}`",
        f"- qdrv runtime profile SHA256: `{QDRV_PROFILE_SHA256}`",
        "- classification: `OFFLINE-CONTRACT-ONLY-NO-HARDWARE-NO-FLASH`",
        "",
        "## Minimum Evidence",
        "",
    ]
    for item in capture_minimum():
        lines.append(f"- `{item['stage']}` from `{item['source']}`: {item['gate']}.")
    lines.extend([
        "",
        "## Interpretation",
        "",
        "- `dequeue-ready` missing: scheduler/node active-band path.",
        "- `dequeue-ready` present and `hardstart` missing: Linux qdisc-to-netdev handoff.",
        "- `hardstart` present and `desc-ready` missing: node/descriptor preparation.",
        "- descriptor stages present and mailbox missing: hostlink/semaphore publication.",
        "- mailbox present and `txdone` missing: MuC completion path.",
        "- complete chain but no client response: MuC/AuC/RF delivery.",
        "",
        "## Safety",
        "",
        "- No flash, MTD, bootenv or reboot path in this contract.",
        "- `wifi0` remains isolated L3 and must not be added to `br0`.",
        "- Missing UART readiness, a UART gap during qdrv load, or missing rollback/recovery proof is `CAPTURE_INVALID` or `FAIL_RECOVERY_UNPROVEN`, never PASS.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def build(output_dir: Path = OUTPUT_DIR) -> dict[str, object]:
    manifest = contract_manifest()
    output_dir.mkdir(parents=True, exist_ok=True)
    copies = {
        "qdrv-v6-scheduler-diag.ko": QDRV,
        "om-radio5-start-v6-scheduler-diag": START,
        "om-radio5-stop-v6-scheduler-diag": STOP,
        "evaluate-v6-scheduler-diag.py": EVALUATOR,
        "v6-source-manifest.json": MANIFEST,
    }
    artifacts: dict[str, dict[str, object]] = {}
    for name, source in copies.items():
        destination = output_dir / name
        shutil.copy2(source, destination)
        artifacts[name] = {
            "file": name,
            "bytes": destination.stat().st_size,
            "sha256": sha256(destination),
        }
    capture_plan = output_dir / "CAPTURE_MINIMUM_UART_OOB.md"
    write_capture_plan(capture_plan)
    artifacts[capture_plan.name] = {
        "file": capture_plan.name,
        "bytes": capture_plan.stat().st_size,
        "sha256": sha256(capture_plan),
    }
    manifest["artifacts"] = artifacts
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums = [f"{item['sha256']}  {item['file']}" for item in artifacts.values()]
    sums.append(f"{sha256(manifest_path)}  manifest.json")
    (output_dir / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        verify_inputs()
        print(f"OMQTN5G_V61_CONTRACT_CHECK_PASS=1 qdrv={QDRV_SHA256} flash=0")
        return 0
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    manifest = build(output)
    print(
        "OMQTN5G_V61_CONTRACT_BUILD_PASS=1 "
        f"qdrv={manifest['qdrv_artifact_sha256']} "
        f"profile={manifest['qdrv_profile_sha256']} "
        f"output={output} flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
