#!/usr/bin/env python3
"""Package the Quantenna v6.2 scheduler diagnostic with enqueue-result UAF fix.

Offline only: copies an already rebuilt qdrv.ko plus the existing safe
start/stop/evaluator wrappers into a versioned RAM-only diagnostic artifact.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD_ROOT = ROOT / "outputs/kernel-port/quantenna-5g-v6.2-scheduler-diag-uafsafe-20260824"
QDRV = BUILD_ROOT / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
SOURCE_TX = ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_tx.c"
SOURCE_RX = ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_rx.c"
START = ROOT / "outputs/kernel-port/quantenna-5g-v6-scheduler-diag/om-radio5-start-v6-scheduler-diag"
STOP = ROOT / "outputs/kernel-port/quantenna-5g-v6-scheduler-diag/om-radio5-stop-v6-scheduler-diag"
EVALUATOR = ROOT / "outputs/kernel-port/quantenna-5g-v6-scheduler-diag/evaluate-v6-scheduler-diag.py"

QDRV_SHA256 = "5b9ae80e5121c4b00965ce4716ad80285f1b599e29845e8efbf938a79600df35"
START_SHA256 = "6ae7242e7d9bf17587711dff71ff1f97355547a13e0e01a80fda319602feed4f"
STOP_SHA256 = "26d34dc42c55348003dc90baed35c6c50d5ad628ed6dd4217b8b9fd3097c5207"
EVALUATOR_SHA256 = "a3ccd5cccc7983fccdc24f4cfe4da7750c55626ac74d80b5074cc152a42532d1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require_hash(path: Path, expected: str) -> None:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual = sha256(path)
    if actual != expected:
        raise RuntimeError(f"hash mismatch for {path}: {actual} != {expected}")


def verify_source_contract() -> None:
    text = SOURCE_TX.read_text(encoding="utf-8")
    if "omqdrvtx_trace_mgmt(trace_skb)" in text or "omqdrvtx_frame_control(trace_skb)" in text:
        raise RuntimeError("enqueue-result still dereferences trace_skb after enqueue")
    required = (
        "bool trace_mgmt = trace && omqdrvtx_trace_mgmt(skb);",
        "u16 trace_fc = trace_mgmt ? omqdrvtx_frame_control(skb) : 0;",
        "trace_mgmt, trace_fc,",
        "stage=enqueue-result",
    )
    for marker in required:
        if marker not in text:
            raise RuntimeError(f"missing UAF-safe source marker: {marker}")


def artifact(path: Path) -> dict[str, object]:
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/kernel-port/quantenna-5g-v6.2-scheduler-diag-uafsafe-package-20260824",
    )
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    verify_source_contract()
    for path, expected in (
        (QDRV, QDRV_SHA256),
        (START, START_SHA256),
        (STOP, STOP_SHA256),
        (EVALUATOR, EVALUATOR_SHA256),
    ):
        require_hash(path, expected)

    output.mkdir(parents=True, exist_ok=True)
    copies = {
        "qdrv-v6.2-scheduler-diag-uafsafe.ko": QDRV,
        "om-radio5-start-v6.2-scheduler-diag-uafsafe": START,
        "om-radio5-stop-v6.2-scheduler-diag-uafsafe": STOP,
        "evaluate-v6.2-scheduler-diag-uafsafe.py": EVALUATOR,
    }
    artifacts: dict[str, dict[str, object]] = {}
    for name, source in copies.items():
        destination = output / name
        shutil.copy2(source, destination)
        artifacts[name] = artifact(destination)

    manifest = {
        "schema": "openmitrastar.qtn-5g-v6.2-scheduler-diag-uafsafe/v1",
        "date": "2026-08-24",
        "classification": "RAM-ONLY-INSTRUMENTATION-NO-FLASH",
        "single_change": "avoid enqueue-result use-after-free by snapshotting mgmt/fc before enqueue/drop",
        "qdrv_artifact_sha256": QDRV_SHA256,
        "source": {
            "qdrv_tx": {
                "file": str(SOURCE_TX.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(SOURCE_TX),
            },
            "qdrv_rx": {
                "file": str(SOURCE_RX.relative_to(ROOT)).replace("\\", "/"),
                "sha256": sha256(SOURCE_RX),
            },
        },
        "expected_chain": [
            "enqueue",
            "enqueue-result",
            "dequeue-ready",
            "hardstart",
            "desc-ready",
            "mailbox-enter",
            "mailbox-published",
            "txdone",
        ],
        "correlation": {"primary": "skb", "descriptor": "hd_pa"},
        "safety": {
            "router_accessed_now": False,
            "uart_used_now": False,
            "network_used_now": False,
            "flash": False,
            "mtd": False,
            "bootenv": False,
            "reboot": False,
        },
        "artifacts": artifacts,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums = [f"{item['sha256']}  {item['file']}" for item in artifacts.values()]
    sums.append(f"{sha256(manifest_path)}  manifest.json")
    (output / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"OMQTN5G_V62_UAFSAFE_BUILD_PASS=1 qdrv={QDRV_SHA256} output={output} flash=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
