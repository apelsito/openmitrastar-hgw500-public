#!/usr/bin/env python3
"""Build the RAM-only v5 AuC-versus-MuC TX-path discriminator."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
V4 = ROOT / "outputs/kernel-port/quantenna-5g-tqe-rxalign-whcopy-runtime-v4-20260823"
QDRV = V4 / "qdrv-tqe-rxalign-whcopy-txpath.ko"
START = V4 / "om-radio5-start-tqe-rxalign-whcopy-txpath"
STOP = V4 / "om-radio5-stop-tqe-rxalign-whcopy-txpath"
PINNED = {
    QDRV: "f9982924fa655fb24b47f902752cbb9e682419b3e4684f29cb110b42648200f1",
    START: "acf4ecc87cf05afe07f5e4b1e19af1a47adc857e18e797b9497bc5d951063031",
    STOP: "2f4983b7ae02a89ea55472b2ed59da67a59e90d1a57c503d8838e43894348444",
}

START_ANCHOR = """log 'OMRADIO5_ROLLBACK_ARMED seconds=120 scope=wifi0-only eth0_2g=preserved'

printf '1\\n' >\"$rf\" || refuse rf-open
"""
START_REPLACEMENT = """log 'OMRADIO5_ROLLBACK_ARMED seconds=120 scope=wifi0-only eth0_2g=preserved'

# v5 discriminator: force the legacy qdisc/MuC TX route while RF is still
# closed.  This leaves the validated v4 RX-alignment driver unchanged and
# makes the existing dequeue/hardstart/descriptor/mailbox/txdone markers the
# proof of which path actually handled client traffic.
/usr/sbin/iwpriv-qtn wifi0 auc_tx 0 >\"$state/auc-tx-set.log\" 2>&1 || refuse auc-tx-disable
log 'OMRADIO5_AUC_TX_MODE mode=muc value=0 rf=closed reversible=1'

printf '1\\n' >\"$rf\" || refuse rf-open
"""

STOP_ANCHOR = """ifconfig wifi0 0.0.0.0 >/dev/null 2>&1 || true
ifconfig wifi0 down >/dev/null 2>&1 || true
[ ! -e \"$rf\" ] || printf '0\\n' >\"$rf\" 2>/dev/null || true

# Never disturb the live management and 2.4 GHz members.  qdrv and its
"""
STOP_REPLACEMENT = """ifconfig wifi0 0.0.0.0 >/dev/null 2>&1 || true
[ ! -e \"$rf\" ] || printf '0\\n' >\"$rf\" 2>/dev/null || true

# qdrv intentionally remains loaded after this stop.  Restore its default AuC
# route after RF is closed but while wifi0 still exists and can accept the
# private ioctl.  A later run must not inherit the v5 discriminator silently.
auc_tx_restore_rc=0
if [ -d /sys/module/qdrv ]; then
\tif [ -e /sys/class/net/wifi0 ] && [ -x /usr/sbin/iwpriv-qtn ]; then
\t\t/usr/sbin/iwpriv-qtn wifi0 auc_tx 1 >\"$state/auc-tx-restore.log\" 2>&1 || auc_tx_restore_rc=$?
\telse
\t\tauc_tx_restore_rc=1
\tfi
fi
ifconfig wifi0 down >/dev/null 2>&1 || true

# Never disturb the live management and 2.4 GHz members.  qdrv and its
"""

STOP_MARKER_ANCHOR = """printf 'OMRADIO5_ROLLBACK_COMPLETE reason=%s rf=closed wifi0=down eth0_2g=%s secrets=redacted\\n' \\
\t\"$reason\" \"$management\" >/dev/console 2>/dev/null || true
[ \"$management\" = preserved ]
"""
STOP_MARKER_REPLACEMENT = """printf 'OMRADIO5_ROLLBACK_COMPLETE reason=%s rf=closed wifi0=down eth0_2g=%s auc_tx_restore_rc=%s secrets=redacted\\n' \\
\t\"$reason\" \"$management\" \"$auc_tx_restore_rc\" >/dev/console 2>/dev/null || true
[ \"$management\" = preserved ] && [ \"$auc_tx_restore_rc\" = 0 ]
"""


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def replace_once(text: str, anchor: str, replacement: str, label: str) -> str:
    if text.count(anchor) != 1:
        raise SystemExit(f"{label} anchor count is {text.count(anchor)}, expected 1")
    return text.replace(anchor, replacement, 1)


def artifact(path: Path) -> dict[str, object]:
    return {"file": path.name, "bytes": path.stat().st_size, "sha256": sha256(path)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "outputs/kernel-port/quantenna-5g-auc-muc-discriminant-v5-20260823",
    )
    args = parser.parse_args()
    output = args.output_dir if args.output_dir.is_absolute() else ROOT / args.output_dir

    for path, expected in PINNED.items():
        if not path.is_file() or sha256(path) != expected:
            raise SystemExit(f"pinned v4 input mismatch: {path}")

    output.mkdir(parents=True, exist_ok=True)
    qdrv_out = output / "qdrv-tqe-rxalign-whcopy-auctx-muc-v5.ko"
    start_out = output / "om-radio5-start-auctx-muc-v5"
    stop_out = output / "om-radio5-stop-auctx-muc-v5"
    qdrv_out.write_bytes(QDRV.read_bytes())

    start = START.read_text(encoding="utf-8")
    start = replace_once(start, START_ANCHOR, START_REPLACEMENT, "start")
    start_out.write_text(start, encoding="utf-8", newline="\n")

    stop = STOP.read_text(encoding="utf-8")
    stop = replace_once(stop, STOP_ANCHOR, STOP_REPLACEMENT, "stop restore")
    stop = replace_once(stop, STOP_MARKER_ANCHOR, STOP_MARKER_REPLACEMENT, "stop marker")
    stop_out.write_text(stop, encoding="utf-8", newline="\n")

    artifacts = {
        "qdrv": artifact(qdrv_out),
        "start": artifact(start_out),
        "stop": artifact(stop_out),
    }
    manifest = {
        "schema": "openmitrastar.qtn-5g-auc-muc-discriminant/v5",
        "classification": "RAM-ONLY-AUC-OFF-MUC-TX-DISCRIMINANT-NO-FLASH",
        "date": "2026-08-23",
        "base_v4_qdrv_sha256": PINNED[QDRV],
        "behavior_change": "iwpriv-qtn wifi0 auc_tx 0 before RF open",
        "rollback": "RF closed, auc_tx restored while wifi0 exists, then wifi0 down",
        "proof_chain": [
            "OMRADIO5_AUC_TX_MODE mode=muc value=0",
            "OMQDRVTXPATH stage=enqueue-result with root_qlen>0",
            "OMQDRVTXPATH stage=dequeue-ready",
            "OMQDRVTXPATH stage=hardstart",
            "OMQDRVTXPATH stage=desc-ready",
            "OMQDRVTXPATH stage=mailbox-published",
            "OMQDRVTXPATH stage=txdone",
        ],
        "pass": "bidirectional client traffic plus management continuity and rollback restore rc=0",
        "artifacts": artifacts,
        "flash": False,
        "mtd": False,
        "bootenv": False,
        "hardware_tested": False,
    }
    manifest_path = output / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    sums = [
        f"{sha256(path)}  {path.name}"
        for path in (qdrv_out, start_out, stop_out, manifest_path)
    ]
    (output / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    print(
        "OMQTN5G_AUC_MUC_V5_BUILD_PASS=1 "
        f"qdrv={artifacts['qdrv']['sha256']} start={artifacts['start']['sha256']} "
        f"stop={artifacts['stop']['sha256']} flash=0"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
