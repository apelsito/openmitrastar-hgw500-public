#!/usr/bin/env python3
"""Build the offline v6 scheduler-observability RAM candidate."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "outputs/kernel-port/quantenna-5g-v6-scheduler-diag/build"
QDRV = BUILD / (
    "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
)
QDRV_SHA = "ba49438c9af9be2058a91704a25571e1d314ef345640f9fe5ccdba66cfa2646e"
V5 = ROOT / "outputs/kernel-port/quantenna-5g-auc-muc-oob-v5-20260823"
START = V5 / "om-radio5-start-auctx-muc-v5"
STOP = V5 / "om-radio5-stop-auctx-muc-v5"
START_SHA = "6ae7242e7d9bf17587711dff71ff1f97355547a13e0e01a80fda319602feed4f"
STOP_SHA = "26d34dc42c55348003dc90baed35c6c50d5ad628ed6dd4217b8b9fd3097c5207"
EVALUATOR = ROOT / "tools/evaluate_qtn_5g_v6_scheduler_diag.py"
SOURCE_TX = ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_tx.c"
SOURCE_RX = ROOT / "work/linux510-radio-port/quantenna-v6-scheduler-diag/qdrv/qdrv_rx.c"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def artifact(path: Path) -> dict[str, object]:
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs/kernel-port/quantenna-5g-v6-scheduler-diag",
    )
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    for path, expected in ((QDRV, QDRV_SHA), (START, START_SHA), (STOP, STOP_SHA)):
        if not path.is_file() or sha(path) != expected:
            raise SystemExit(f"pinned v6 input mismatch: {path}")

    output.mkdir(parents=True, exist_ok=True)
    files = {
        "qdrv": (QDRV, "qdrv-v6-scheduler-diag.ko"),
        "start": (START, "om-radio5-start-v6-scheduler-diag"),
        "stop": (STOP, "om-radio5-stop-v6-scheduler-diag"),
        "evaluator": (EVALUATOR, "evaluate-v6-scheduler-diag.py"),
    }
    artifacts = {}
    for name, (source, filename) in files.items():
        destination = output / filename
        destination.write_bytes(source.read_bytes())
        artifacts[name] = artifact(destination)

    manifest = {
        "schema": "openmitrastar.qtn-5g-v6-scheduler-diag/v1",
        "classification": "RAM-ONLY-INSTRUMENTATION-NO-FLASH",
        "date": "2026-08-23",
        "v5_conclusion": (
            "auc_tx=0 is upstream of qdisc/hardstart and changed the path, but "
            "the run never associated and therefore did not exercise client IP TX"
        ),
        "source_findings": {
            "queue_enabled_is_dequeue_gate": False,
            "actual_dequeue_gates": ["netif_queue_stopped", "descriptor_availability"],
            "management_descriptor_consumption_observed": True,
            "previous_hardstart_trace_excluded_management": True,
            "first_missing_transition": "management dequeue-ready to management hardstart is unobserved",
        },
        "single_change": (
            "extend bounded TXPATH instrumentation to authentication/association "
            "management replies and correlate all stages by skb then hd_pa"
        ),
        "source": {
            "qdrv_tx": {"file": str(SOURCE_TX.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(SOURCE_TX)},
            "qdrv_rx": {"file": str(SOURCE_RX.relative_to(ROOT)).replace("\\", "/"), "sha256": sha(SOURCE_RX)},
            "module_manifest_sha256": sha(BUILD / "module-manifest.tsv"),
        },
        "artifacts": artifacts,
        "expected_chain": [
            "enqueue", "enqueue-result", "dequeue-ready", "hardstart",
            "desc-ready", "mailbox-enter", "mailbox-published", "txdone",
        ],
        "correlation": {"primary": "skb", "descriptor": "hd_pa"},
        "flash": False,
        "mtd": False,
        "bootenv": False,
        "hardware_tested": False,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums = [f"{sha(output / item['file'])}  {item['file']}" for item in artifacts.values()]
    sums.append(f"{sha(manifest_path)}  manifest.json")
    (output / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(f"OMQTN5G_V6_SCHEDULER_DIAG_BUILD_PASS=1 qdrv={QDRV_SHA} manifest={sha(manifest_path)} flash=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
