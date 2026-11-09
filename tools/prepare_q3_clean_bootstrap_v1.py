#!/usr/bin/env python3
"""Prepare the read-only input gate for the Q3 clean bootstrap image.

This tool never contacts the router and never writes flash.  It binds the
known-good 2.4 GHz bundle and waits for an Aelita 5 GHz isolated-L3 PASS before
allowing the actual firmware compositor to run.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
LANE = ROOT / "work/mission-state/q3-clean-bootstrap-v1"
LOCK = LANE / "input-lock.json"
READINESS = LANE / "readiness.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def valid_5g_evaluation(payload: dict) -> bool:
    network = payload.get("network") or {}
    return (
        payload.get("schema") == "openmitrastar.qtn-5g-isolated-l3-evaluation/v1"
        and payload.get("status") == "PASS"
        and network.get("direct_bidirectional_icmp") is True
        and network.get("main_management_preserved") is True
        and network.get("wifi0_in_br0") is False
    )


def discover_5g_evaluation(explicit: Path | None) -> Path | None:
    if explicit:
        return explicit.resolve()
    roots = (
        ROOT / "outputs/f3-certification/qtn-5g-aelita",
        ROOT / "outputs/f3-certification/qtn-5g-isolated-l3",
        ROOT / "outputs/kernel-port/quantenna-5g-isolated-l3-runtime-20260823",
    )
    candidates: list[Path] = []
    for directory in roots:
        if directory.is_dir():
            candidates.extend(directory.glob("*evaluation*.json"))
    return max(candidates, key=lambda item: item.stat().st_mtime) if candidates else None


def prepare(evaluation_path: Path | None = None) -> dict:
    lock = load_json(LOCK)
    failures: list[str] = []

    base = ROOT / lock["base"]["path"]
    if not base.is_file() or sha256(base) != lock["base"]["sha256"]:
        failures.append("q2_base_hash")

    radio2_dir = ROOT / lock["radio2g"]["bundle"]
    radio2_manifest_path = radio2_dir / "manifest.json"
    if (
        not radio2_manifest_path.is_file()
        or sha256(radio2_manifest_path) != lock["radio2g"]["manifest_sha256"]
    ):
        failures.append("radio2_manifest_hash")
        radio2_manifest = {}
    else:
        radio2_manifest = load_json(radio2_manifest_path)

    modules = {Path(item["path"]).name: item for item in radio2_manifest.get("modules", [])}
    if len(modules) != 10:
        failures.append("radio2_complete_stack")
    for name, key in (("rtl_pci.ko", "rtl_pci_sha256"), ("rtl8192ee.ko", "rtl8192ee_sha256")):
        item = modules.get(name)
        expected = lock["radio2g"][key]
        path = radio2_dir / "modules" / name
        if not item or item.get("sha256") != expected or not path.is_file() or sha256(path) != expected:
            failures.append(f"radio2_{name}_hash")

    staging = ROOT / lock["radio5g"]["staging_runtime"]
    staging_manifest = staging / "manifest.json"
    if (
        not staging_manifest.is_file()
        or sha256(staging_manifest) != lock["radio5g"]["staging_manifest_sha256"]
    ):
        failures.append("radio5_staging_manifest_hash")

    evaluation = discover_5g_evaluation(evaluation_path)
    evaluation_payload: dict | None = None
    if evaluation and evaluation.is_file():
        evaluation_payload = load_json(evaluation)
    if not evaluation_payload or not valid_5g_evaluation(evaluation_payload):
        failures.append("radio5_isolated_l3_pass")

    ready = not failures
    result = {
        "schema": "openmitrastar.q3-clean-bootstrap-readiness/v1",
        "ready_to_compose": ready,
        "candidate_eligible": False,
        "failures": sorted(set(failures)),
        "target": "mtd4_linux_live",
        "slot_bytes": 0x7A0000,
        "preserved_partitions": ["mtd0", "mtd1", "mtd2", "mtd3", "mtd5"],
        "radio2_manifest": str(radio2_manifest_path.relative_to(ROOT)).replace("\\", "/"),
        "radio2_manifest_sha256": sha256(radio2_manifest_path) if radio2_manifest_path.is_file() else None,
        "radio5_evaluation": (
            str(evaluation.relative_to(ROOT)).replace("\\", "/")
            if evaluation and evaluation.is_relative_to(ROOT)
            else str(evaluation) if evaluation else None
        ),
        "radio5_evaluation_sha256": sha256(evaluation) if evaluation and evaluation.is_file() else None,
        "next": (
            "compose_offline_candidate"
            if ready
            else "prepare_out_of_band_qdrv_txpath_capture"
        ),
        "next_discriminant": lock.get("next_discriminant"),
        "hardware_actions": False,
        "flash_actions": False,
    }
    LANE.mkdir(parents=True, exist_ok=True)
    READINESS.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--five-g-evaluation", type=Path)
    parser.add_argument("--require-ready", action="store_true")
    args = parser.parse_args()
    result = prepare(args.five_g_evaluation)
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.require_ready and not result["ready_to_compose"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
