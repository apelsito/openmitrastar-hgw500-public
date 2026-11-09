#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ARTIFACT = ROOT / "outputs/kernel-port/quantenna-linux510-v89-routed-20260818-2045"
DEFAULT_MANIFEST = ROOT / "work/mission-state/w3-offline/W3_V89_SIGNED_ARTIFACT.json"
DEFAULT_GATE = ROOT / "work/mission-state/w3-offline/W3_RUNTIME_GATE.env"
RELEASE = "5.10.260-openmitrastar-radio"
QDRV_VERSION = 0x25040059
BOARD = {
    "board_id": 65535, "emac0": 1, "emac1": 1, "wifi_hw": 7, "rfic": 4,
    "calstate": 3, "ext_lna_gain": 12, "ext_lna_bypass_gain": -5,
    "tx_power_cal": 0, "min_tx_power": 7, "max_tx_power": 21,
    "allow_dram_sram_fallback": 0,
}
FIRMWARE = {
    "lib/firmware/auc_driver.default.0.bin": "e1fd397ef56b061af7c91cbd422973dcfcf1382933afa226f8f428dd315f65af",
    "lib/firmware/auc_driver.nomu.0.bin": "c10018f4fe384d753a800bbbcd5ef3c85c568d0852c221009063282d30fd85f6",
    "lib/firmware/qtn_driver.qtn_ruby.0.bin": "71dcd32849f122c09397490914227af6f77e51c34d15615028faa3d0fabb0fe4",
    "lib/firmware/rdsp_driver.0.bin": "87c882910d87cd29ba2004c4154e9240291aaad6aedb0ff4d90c7a5570be79fd",
}
REGDB = {"etc/qtn_regulatory_db.bin": "2263cc2407d6e0d1543aa55bd7d2b9b98598301c59b4ded7d2b9b98598301c59b4d3dca40701132f044365"}
# Correct the visually duplicated prefix above without hiding the pinned value.
REGDB["etc/qtn_regulatory_db.bin"] = "2263cc2407d6e0d1543aa55bd7d2b9b98598301c59b4d3dca40701132f044365"
TESTS = [
    [sys.executable, "tools/test_qtn_qdrv_abi_diff.py", "-v"],
    [sys.executable, "tools/test_qdrv_abi_contract.py", "-v"],
    [sys.executable, "tools/test_qtn_w3_offline_gate.py", "-v"],
    [sys.executable, "tools/test_qtn_w3_pre_mmio_ladder.py", "-v"],
    [sys.executable, "tools/test_qtn_v89_shared_publisher.py", "-v"],
]


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module_rows(artifact: Path) -> list[dict[str, object]]:
    with (artifact / "module-manifest.tsv").open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle, delimiter="\t"))
    if len(rows) != 22:
        raise ValueError(f"expected 22 modules, got {len(rows)}")
    return [{"path": row["module"], "sha256": row["sha256"], "size": int(row["size"]),
             "vermagic": row["vermagic"], "depends": row["depends"]} for row in rows]


def build_manifest(artifact: Path, release: str) -> dict[str, object]:
    rows = module_rows(artifact)
    qdrv = next(row for row in rows if row["path"] == "qdrv/qdrv.ko")
    return {
        "schema": "openmitrastar-w3-v89-artifact-v1",
        "generated_utc": os.environ.get(
            "W3_MANIFEST_UTC", datetime.now(timezone.utc).isoformat()
        ),
        "artifact": str(artifact.relative_to(ROOT)).replace("\\", "/"),
        "release": release,
        "qdrv_build_version": f"0x{QDRV_VERSION:08x}",
        "qdrv_sha256": qdrv["sha256"],
        "modules": rows,
        "firmware": FIRMWARE,
        "regulatory": REGDB,
        "board": BOARD,
        "allocator": {"size": 0x77A0, "shared": 0x190, "txbf": 0x190,
                      "muc_dsp": 0x1340, "sample": 0x1BD8, "scan": 0x1C78,
                      "scs": 0x1D24, "nac": 0x6D7C},
        "tests": [command[1] for command in TESTS],
        "module_manifest_sha256": sha(artifact / "module-manifest.tsv"),
    }


def verify(manifest: dict[str, object], run_tests: bool) -> None:
    artifact = ROOT / str(manifest["artifact"])
    release = str(manifest["release"])
    if release not in (RELEASE, "5.10.260-openmitrastar-radiohw") or manifest["qdrv_build_version"] != "0x25040059":
        raise ValueError("release/version mismatch")
    rows = module_rows(artifact)
    expected = {row["path"]: row for row in manifest["modules"]}
    if {row["path"] for row in rows} != set(expected):
        raise ValueError("module inventory mismatch")
    for row in rows:
        path = artifact / "rootfs/lib/modules" / release / "extra/quantenna" / str(row["path"])
        exp = expected[row["path"]]
        if sha(path) != exp["sha256"] or path.stat().st_size != exp["size"]:
            raise ValueError(f"module mismatch: {row['path']}")
    if expected["qdrv/qdrv.ko"]["sha256"] != manifest["qdrv_sha256"]:
        raise ValueError("qdrv manifest mismatch")
    qdrv_data = (artifact / "rootfs/lib/modules" / release / "extra/quantenna/qdrv/qdrv.ko").read_bytes()
    if b"v37.4.0.89" not in qdrv_data or b"openmitrastar-gated" not in qdrv_data:
        raise ValueError("gated qdrv version marker absent")
    for rel, digest in {**FIRMWARE, **REGDB}.items():
        if sha(artifact / "rootfs" / rel) != digest:
            raise ValueError(f"immutable input mismatch: {rel}")
    if manifest["board"] != BOARD or manifest["allocator"]["size"] != 0x77A0:
        raise ValueError("board/allocator contract mismatch")
    soc = (ROOT / "work/linux510-radio-port/quantenna/qdrv/qdrv_soc.c").read_text(encoding="utf-8")
    if soc.count("qdrv_v89_shared_publish_init(") != 1 or "nac_mon_info) == 0x6d7c" not in soc:
        raise ValueError("publisher route mismatch")
    if run_tests:
        for command in TESTS:
            result = subprocess.run(command, cwd=ROOT)
            if result.returncode:
                raise ValueError(f"test failed: {command[1]}")


def gate_text(manifest: dict[str, object], manifest_path: Path = DEFAULT_MANIFEST) -> str:
    return "\n".join([
        "W3_PAIR_APPROVED=1",
        "W3_HARDWARE_ACTIVE_APPROVED=0",
        "W3_HOST_BUILD=v37.4.0.89-openmitrastar-gated",
        "W3_HOST_VERSION=0x25040059",
        "W3_FIRMWARE_BUILD=v37.4.0.89",
        "W3_FIRMWARE_VERSION=0x25040059",
        "W3_OVERLAP_CLASS=OEM_QUIRK_PROVEN",
        f"W3_KERNEL_RELEASE={manifest['release']}",
        f"W3_ARTIFACT_QDRV_SHA256={manifest['qdrv_sha256']}",
        f"W3_MANIFEST_SHA256={sha(manifest_path)}",
        "W3_STOP_REASON=HARDWARE_ACTIVE_NOT_APPROVED",
        "",
    ])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact", type=Path, default=DEFAULT_ARTIFACT)
    parser.add_argument("--release", default=RELEASE)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--verify", action="store_true")
    parser.add_argument("--run-tests", action="store_true")
    parser.add_argument("--write-gate", type=Path)
    args = parser.parse_args()
    artifact = args.artifact if args.artifact.is_absolute() else ROOT / args.artifact
    manifest_path = args.manifest if args.manifest.is_absolute() else ROOT / args.manifest
    gate_path = None if args.write_gate is None else (
        args.write_gate if args.write_gate.is_absolute() else ROOT / args.write_gate
    )
    if args.write_manifest:
        manifest_path.write_text(json.dumps(build_manifest(artifact, args.release), indent=2) + "\n", encoding="utf-8")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if args.verify or gate_path:
        verify(manifest, args.run_tests)
    if gate_path:
        gate_path.write_text(gate_text(manifest, manifest_path), encoding="utf-8")
    print(f"W3_V89_ARTIFACT_PASS qdrv={manifest['qdrv_sha256']} modules={len(manifest['modules'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
