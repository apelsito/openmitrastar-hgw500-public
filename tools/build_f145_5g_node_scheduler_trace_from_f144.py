#!/usr/bin/env python3
"""Build F145 from F144 with bounded node scheduler diagnostics."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import build_f143_5g_deferred_dma_free_from_f142 as engine
import build_f144_5g_qdisc_binding_from_f143 as f144


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f145-5g-node-scheduler-trace-from-f144"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F145_FROM_F144_5G_NODE_SCHEDULER_TRACE"
OLD_QDRV_SHA = f144.NEW_QDRV_SHA
NEW_QDRV_SHA = "5efe71b0431b5867f172a1abebe0b99534e07f7db9f6c5c1dcb89bc6c1c79341"
NEW_QDRV = (
    ROOT
    / "outputs/kernel-port/quantenna-linux510-radiohw-node-scheduler-trace-f145-20260831"
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
        "SRC_BUILD": f144.OUT,
        "SRC_BASE": f144.BASE_OUT,
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
        "add bounded node-enqueue-result diagnostics for AP-to-client data",
        "record node/root/installed qdisc identity and queue depth",
        "record MuC quota thresholds, over-threshold state, tokens and active bands",
        "preserve all F144 behavior",
    ]
    report["start_script"]["fixes"] = [
        "keeps F144 RF/VAP/userspace ordering and TX-power behavior",
        "updates the qdrv integrity expectation for the scheduler trace build",
        "does not change 2.4 GHz, rates, rings, forwarding, bridge topology or auc_tx",
    ]
    return patched, report


def main() -> int:
    data = NEW_QDRV.read_bytes()
    if hashlib.sha256(data).hexdigest() != NEW_QDRV_SHA:
        raise SystemExit("F145 rebuilt qdrv hash mismatch")
    if b"OMQDRVTXPATH stage=node-enqueue-result" not in data:
        raise SystemExit("F145 rebuilt qdrv lacks node scheduler marker")

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
        "radio2g": "unchanged from F144",
        "radio5_start": "unchanged from F144 except qdrv integrity hash",
        "radio5_stop": "unchanged from F144",
        "radio5_modules": "only qdrv.ko replaced from the verified 25-module build",
        "qdrv": "bounded node scheduler diagnostics only",
        "wlan": "unchanged from F144",
        "queues_dma_rates_rings_forwarding_auc_tx": "behavior unchanged from F144",
        "bridge_topology": "unchanged from F144",
    }
    manifest["runtime_policy"] = {
        "node_scheduler_trace": "first 32 ARP/IPv4/IPv6 packets while tx-path tracing is enabled",
        "qdisc_node_binding": "qdisc_sleeping on Linux >= 4.20",
        "hr_timer": "disabled for HGW-500BNA-QCv2 before timer setup",
        "disassoc_dma_allocation": "GFP_DMA | GFP_ATOMIC",
        "hostlink_dma_free": "deferred to system workqueue from interrupt/IRQ-disabled context",
        "expected_effect": "identify the exact reason successful enqueue never reaches dequeue-ready",
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
