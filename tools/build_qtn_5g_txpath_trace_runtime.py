#!/usr/bin/env python3
"""Build the isolated-L3 runtime that enables only qdrv TX path tracing."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/kernel-port/quantenna-5g-isolated-l3-runtime-20260823"
START = BASE / "om-radio5-start-isolated-l3"
STOP = BASE / "om-radio5-stop-isolated-l3"
START_SHA = "bc5d5144c718c78f03640e1c1b6272f9cd03e1381b4a1e5adee4fb3c45710896"
STOP_SHA = "2f4983b7ae02a89ea55472b2ed59da67a59e90d1a57c503d8838e43894348444"
QDRV = ROOT / "outputs/kernel-port/quantenna-5g-txpath-trace-radiohw-20260823/rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
QDRV_SHA = "62c7f5433da5b9035f5e6a7a2694a2424faf66da1d307d10950ce7c785dbc524"


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs/kernel-port/quantenna-5g-txpath-discriminant-20260823",
    )
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    if sha(START) != START_SHA or sha(STOP) != STOP_SHA or sha(QDRV) != QDRV_SHA:
        raise SystemExit("pinned TX path inputs do not match")
    source = START.read_text(encoding="utf-8")
    needle = "tqe_sem_en=1 openmitrastar_clearsram_only=0"
    if source.count(needle) != 3:
        raise SystemExit("unexpected qdrv load call count")
    start = source.replace(
        needle,
        "tqe_sem_en=1 openmitrastar_tx_path_trace_enable=1 openmitrastar_clearsram_only=0",
    ).encode()
    stop = STOP.read_bytes()
    output.mkdir(parents=True, exist_ok=True)
    (output / "om-radio5-start-txpath-trace").write_bytes(start)
    (output / "om-radio5-stop-txpath-trace").write_bytes(stop)
    qdrv_out = output / "qdrv-txpath-trace.ko"
    qdrv_out.write_bytes(QDRV.read_bytes())
    manifest = {
        "schema": "openmitrastar.qtn-5g-txpath-discriminant/v1",
        "classification": "RAM-ONLY-TRACE-NO-FWT-NO-FLASH",
        "artifacts": {
            "qdrv": {"file": qdrv_out.name, "bytes": qdrv_out.stat().st_size, "sha256": sha(qdrv_out)},
            "start": {"file": "om-radio5-start-txpath-trace", "bytes": len(start), "sha256": hashlib.sha256(start).hexdigest()},
            "stop": {"file": "om-radio5-stop-txpath-trace", "bytes": len(stop), "sha256": hashlib.sha256(stop).hexdigest()},
        },
        "activation": "openmitrastar_tx_path_trace_enable=1",
        "markers": ["enqueue", "hardstart", "desc-ready", "mailbox-enter", "mailbox-published", "txdone"],
        "topology": "isolated-l3 192.168.77.1/24; wifi0 outside br0; TQE512",
        "behavior_changes": ["bounded logging only"],
        "fwt_ctrl": False,
        "ioss": False,
        "flash": False,
        "reproducible": True,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "OMQTN5G_TXPATH_DISCRIMINANT_BUILD_PASS=1 "
        f"qdrv={manifest['artifacts']['qdrv']['sha256']} "
        f"start={manifest['artifacts']['start']['sha256']} flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
