#!/usr/bin/env python3
"""Package the corrected TQE RX-alignment + local header-copy runtime."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "outputs/kernel-port/quantenna-5g-txpath-discriminant-20260823"
START = BASE / "om-radio5-start-txpath-trace"
STOP = BASE / "om-radio5-stop-txpath-trace"
START_SHA = "acf4ecc87cf05afe07f5e4b1e19af1a47adc857e18e797b9497bc5d951063031"
STOP_SHA = "2f4983b7ae02a89ea55472b2ed59da67a59e90d1a57c503d8838e43894348444"
QDRV = ROOT / (
    "outputs/kernel-port/quantenna-5g-tqe-rxalign-whcopy-v4-20260823/rootfs/"
    "lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
)
QDRV_SHA = "f9982924fa655fb24b47f902752cbb9e682419b3e4684f29cb110b42648200f1"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir", type=Path,
        default=ROOT / "outputs/kernel-port/quantenna-5g-tqe-rxalign-whcopy-runtime-v4-20260823",
    )
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir
    for path, expected in ((START, START_SHA), (STOP, STOP_SHA), (QDRV, QDRV_SHA)):
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"pinned input mismatch: {path}")

    output.mkdir(parents=True, exist_ok=True)
    artifacts = {
        "qdrv": (QDRV, "qdrv-tqe-rxalign-whcopy-txpath.ko"),
        "start": (START, "om-radio5-start-tqe-rxalign-whcopy-txpath"),
        "stop": (STOP, "om-radio5-stop-tqe-rxalign-whcopy-txpath"),
    }
    manifest_artifacts = {}
    for name, (source, filename) in artifacts.items():
        destination = output / filename
        destination.write_bytes(source.read_bytes())
        manifest_artifacts[name] = {
            "file": filename,
            "bytes": destination.stat().st_size,
            "sha256": sha256(destination),
        }

    manifest = {
        "schema": "openmitrastar.qtn-5g-tqe-rxalign-whcopy-txpath/v1",
        "classification": "RAM-ONLY-TQE-RXALIGN-WHCOPY-TXPATH-NO-FLASH",
        "single_behavior_change": (
            "align the direct TQE RX skb and preserve an in-skb whole_frm_hdr "
            "with a validated local copy before skb replacement"
        ),
        "fault_anchor": {
            "eret": "0x852efc96",
            "symbol": "ip_rcv_core",
            "efa": "0x86e90442",
            "alignment": "2-mod-4",
            "uart": "outputs/uart-live/qtn-5g-txpath-oob/txpath-oob-20260823-192811/uart.log",
        },
        "header_preservation": {
            "method": "validated local ieee80211_qosframe_addr4 copy",
            "old_skb_pointer_retained": False,
            "head_offset_rebase": False,
        },
        "artifacts": manifest_artifacts,
        "txpath_markers": [
            "enqueue", "hardstart", "desc-ready", "mailbox-enter",
            "mailbox-published", "txdone",
        ],
        "expected_rx_marker": "OMQDRVRX stage=stack-realign source=tqe",
        "flash": False,
        "bootenv": False,
        "hardware_tested": False,
    }
    (output / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        "OMQTN5G_TQE_RXALIGN_WHCOPY_RUNTIME_BUILD_PASS=1 "
        f"qdrv={manifest_artifacts['qdrv']['sha256']} "
        f"start={manifest_artifacts['start']['sha256']} flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
