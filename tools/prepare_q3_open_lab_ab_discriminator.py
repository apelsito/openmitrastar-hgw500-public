#!/usr/bin/env python3
"""Prepare, but never execute, the Q3 OPEN-LAB A/B RAM discriminator."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
A_IMAGE = ROOT / "work/mission-state/q3-open-lab-v2-composite/build/openmitrastar-linux510-q3-open-lab-v2-LZMA-RAM-ONLY-NO-FLASH.webformat.bin"
A_MANIFEST = ROOT / "work/mission-state/q3-open-lab-v2-composite/build/manifest.json"
A_SHA = "02cf63bdfd86d45ca887a3ca8b92cdff6c10bd4b327017e45097c5b8054d09d6"
A_BYTES = 4_312_825
OUTPUT = ROOT / "work/mission-state/q3-open-lab-discriminator/experiment-contract.json"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--b-image", type=Path)
    parser.add_argument("--b-manifest", type=Path)
    parser.add_argument("--b-sha256")
    parser.add_argument("--w3-analysis", type=Path)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()

    if not A_IMAGE.is_file() or sha(A_IMAGE) != A_SHA or A_IMAGE.stat().st_size != A_BYTES:
        raise SystemExit("A OPEN-LAB v2 drift")
    a_manifest = json.loads(A_MANIFEST.read_text(encoding="utf-8"))
    if a_manifest.get("classification") != "OPEN-LAB-RAM-ONLY-NO-FLASH" or a_manifest.get("profile") != "Q3_OPEN_LAB":
        raise SystemExit("A profile contract drift")

    b_ready = all((args.b_image, args.b_manifest, args.b_sha256, args.w3_analysis))
    b = None
    status = "WAIT_W3_ANALYSIS"
    if b_ready:
        b_image = args.b_image.resolve()
        b_manifest_path = args.b_manifest.resolve()
        analysis_path = args.w3_analysis.resolve()
        for path in (b_image, b_manifest_path, analysis_path):
            if not path.is_file():
                raise SystemExit(f"missing B input: {path}")
        expected = args.b_sha256.lower()
        if len(expected) != 64 or sha(b_image) != expected:
            raise SystemExit("B image hash mismatch")
        analysis = json.loads(analysis_path.read_text(encoding="utf-8"))
        if analysis.get("status") != "W3_APPROVED_SINGLE_VARIABLE" or analysis.get("changed_dimension") != "switch_tqe_rx_ring_entries":
            raise SystemExit("W3 did not approve a single-variable radio5 comparison")
        if analysis.get("a_sha256") != A_SHA or analysis.get("b_sha256") != expected:
            raise SystemExit("W3 analysis does not bind A/B images")
        b_manifest = json.loads(b_manifest_path.read_text(encoding="utf-8"))
        for invariant in ("kernel_sha256", "dtb_sha256", "rootfs_non_radio_sha256", "profile_sha256"):
            if analysis.get("invariants", {}).get(invariant) is not True:
                raise SystemExit(f"B invariant not proven: {invariant}")
        b = {
            "image": str(b_image), "sha256": expected, "bytes": b_image.stat().st_size,
            "manifest": str(b_manifest_path), "manifest_sha256": sha(b_manifest_path),
            "w3_analysis": str(analysis_path), "w3_analysis_sha256": sha(analysis_path),
            "classification": b_manifest.get("classification"),
        }
        status = "READY_FOR_SEQUENTIAL_RAM_EXECUTION"

    report = {
        "schema": "openmitrastar.q3-open-lab-ab-discriminator/v1",
        "status": status,
        "hardware_actions": False,
        "flash_actions": False,
        "changed_dimension": "switch_tqe_rx_ring_entries",
        "a": {"image": str(A_IMAGE), "sha256": A_SHA, "bytes": A_BYTES,
              "classification": "OPEN-LAB-RAM-ONLY-NO-FLASH",
              "stack": "current-no-fwt-direct-symbols"},
        "b": b,
        "invariants_required": [
            "same kernel and DTB", "same rootfs outside radio5 payload",
            "same SSID MOVISTAR_PLUS_55CB", "same OPEN security",
            "same channel 36 / 80 MHz / ES", "same automatic MAC producer",
            "same Ethernet, 2.4 GHz, bridge, LEDs and management"
        ],
        "measurement": {
            "cold_boot_each_arm": True,
            "hot_stack_restart_forbidden": True,
            "baseline_seconds": 30,
            "client_attempt_window_seconds": 60,
            "metrics": ["SSID visibility", "hostapd PONG/config", "station/authorization",
                        "wifi0 RX/TX", "IRQ8/IRQ9/IRQ10", "eth0 management", "fatal markers"]
        },
        "rollback": {
            "local_watchdog_seconds": 180,
            "management_rule": "never remove eth0 or wlan0 from br0",
            "uart": "power-cycle -> Bootbase/ZHAL ATGU -> boot persistent Q2 mtd4 or RAM A",
            "persistent_q2_sha256": "cbe904ab7a807838fa12077fab924c79ce3c112a5ef40727cbaf9ec98f638cf1",
            "flash_write": False
        },
        "decision_table": {
            "A_no_attempt_B_associates": "current no-fwt/direct-symbols radio5 stack regression",
            "A_and_B_no_attempt": "phone/RF visibility or shared control path; stack delta not causal",
            "A_and_B_associate": "transient/start-order issue; retain current safer stack",
            "B_fatal_or_management_loss": "reject B immediately and cold-rollback to A/Q2"
        }
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    print(f"OMQ3_OPEN_LAB_AB_PREP status={status} hardware=0 flash=0")
    return 0 if b_ready else 2


if __name__ == "__main__":
    raise SystemExit(main())
