#!/usr/bin/env python3
"""Build F146 from F145 with bounded AuC/TQE submission diagnostics."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import build_f143_5g_deferred_dma_free_from_f142 as engine
import build_f145_5g_node_scheduler_trace_from_f144 as f145


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f146-5g-auc-submit-trace-from-f145"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F146_FROM_F145_5G_AUC_SUBMIT_TRACE"
OLD_QDRV_SHA = f145.NEW_QDRV_SHA
NEW_QDRV_SHA = "f92761b610eb715d5811275d00935391f9e9fbfb50e213949f3d019f276273c4"
NEW_QDRV = (
    ROOT
    / "outputs/kernel-port/quantenna-linux510-radiohw-auc-submit-trace-f146-20260831"
    / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
)
BUILD_PROFILE = NEW_QDRV.parents[7] / "build-profile.env"
MODULE_MANIFEST = NEW_QDRV.parents[7] / "module-manifest.tsv"
ORIGINAL_PATCH_CPIO = engine.patch_cpio


@contextlib.contextmanager
def variant_context():
    names = (
        "BUILD_TAG", "OUT", "BASE_OUT", "CLASSIFICATION", "SRC_BUILD",
        "SRC_BASE", "OLD_QDRV_SHA", "NEW_QDRV_SHA", "NEW_QDRV",
        "BUILD_PROFILE", "MODULE_MANIFEST",
    )
    old = {name: getattr(engine, name) for name in names}
    values = {
        "BUILD_TAG": BUILD_TAG,
        "OUT": OUT,
        "BASE_OUT": BASE_OUT,
        "CLASSIFICATION": CLASSIFICATION,
        "SRC_BUILD": f145.OUT,
        "SRC_BASE": f145.BASE_OUT,
        "OLD_QDRV_SHA": OLD_QDRV_SHA,
        "NEW_QDRV_SHA": NEW_QDRV_SHA,
        "NEW_QDRV": NEW_QDRV,
        "BUILD_PROFILE": BUILD_PROFILE,
        "MODULE_MANIFEST": MODULE_MANIFEST,
    }
    try:
        for name, value in values.items():
            setattr(engine, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(engine, name, value)


def patch_cpio(raw: bytes):
    with variant_context():
        patched, report = ORIGINAL_PATCH_CPIO(raw)
    report["qdrv"]["fixes"] = [
        "add bounded AuC/TQE submission diagnostics for ARP, IPv4 and IPv6",
        "record destination node, TQE port/TID and NETDEV_TX_BUSY result",
        "preserve all F145 behavior and diagnostics",
    ]
    report["start_script"]["fixes"] = [
        "keeps F145 RF/VAP/userspace ordering and TX-power behavior",
        "updates the qdrv integrity expectation for the AuC submission trace build",
        "does not change 2.4 GHz, rates, rings, forwarding, bridge topology or auc_tx",
    ]
    return patched, report


def main() -> int:
    data = NEW_QDRV.read_bytes()
    if hashlib.sha256(data).hexdigest() != NEW_QDRV_SHA:
        raise SystemExit("F146 rebuilt qdrv hash mismatch")
    if b"OMQDRVTXPATH stage=auc-submit" not in data:
        raise SystemExit("F146 rebuilt qdrv lacks AuC submission marker")

    original = engine.patch_cpio
    with variant_context():
        engine.patch_cpio = patch_cpio
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = engine.main()
        finally:
            engine.patch_cpio = original
    if rc:
        return rc

    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    manifest["change_scope"] = {
        "radio2g": "unchanged from F145",
        "radio5_start": "unchanged from F145 except qdrv integrity hash",
        "radio5_stop": "unchanged from F145",
        "radio5_modules": "only qdrv.ko replaced from the verified 25-module build",
        "qdrv": "bounded AuC/TQE submission diagnostics only",
        "wlan": "unchanged from F145",
        "queues_dma_rates_rings_forwarding_auc_tx": "behavior unchanged from F145",
        "bridge_topology": "unchanged from F145",
    }
    manifest["runtime_policy"] = {
        "auc_submit_trace": "first 64 ARP/IPv4/IPv6 packets while tx-path tracing is enabled",
        "node_scheduler_trace": "preserved from F145 for the non-AuC path",
        "qdisc_node_binding": "qdisc_sleeping on Linux >= 4.20",
        "hr_timer": "disabled for HGW-500BNA-QCv2 before timer setup",
        "disassoc_dma_allocation": "GFP_DMA | GFP_ATOMIC",
        "hostlink_dma_free": "deferred to system workqueue from interrupt/IRQ-disabled context",
        "expected_effect": "separate TQE buffer exhaustion from loss after successful AuC publication",
        "persistent_flash_writes": 0,
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

    sums_path = OUT / "SHA256SUMS"
    lines = []
    for line in sums_path.read_text(encoding="ascii").splitlines():
        _digest, name = line.split("  ", 1)
        path = OUT / name
        lines.append(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {name}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
