#!/usr/bin/env python3
"""Build F144 from F143 with Linux 5.10 qdisc-sleeping node binding."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
from pathlib import Path

import build_f143_5g_deferred_dma_free_from_f142 as f143


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f144-5g-qdisc-binding-from-f143"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F144_FROM_F143_5G_QDISC_SLEEPING_BINDING"
NEW_QDRV_SHA = "89139dbf883e254b8b74ad57a61d8b35ed5bb85b4654cf73787910134016c684"
NEW_QDRV = (
    ROOT
    / "outputs/kernel-port/quantenna-linux510-radiohw-qdisc-binding-f144-20260830"
    / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna/qdrv/qdrv.ko"
)
BUILD_PROFILE = NEW_QDRV.parents[7] / "build-profile.env"
MODULE_MANIFEST = NEW_QDRV.parents[7] / "module-manifest.tsv"
ORIGINAL_PATCH_CPIO = f143.patch_cpio
F143_OUT = f143.OUT
F143_BASE_OUT = f143.BASE_OUT
F143_QDRV_SHA = f143.NEW_QDRV_SHA


@contextlib.contextmanager
def f144_context():
    names = (
        "BUILD_TAG", "OUT", "BASE_OUT", "CLASSIFICATION", "SRC_BUILD",
        "SRC_BASE", "OLD_QDRV_SHA", "NEW_QDRV_SHA", "NEW_QDRV",
        "BUILD_PROFILE", "MODULE_MANIFEST",
    )
    old = {name: getattr(f143, name) for name in names}
    replacements = {
        "BUILD_TAG": BUILD_TAG,
        "OUT": OUT,
        "BASE_OUT": BASE_OUT,
        "CLASSIFICATION": CLASSIFICATION,
        "SRC_BUILD": F143_OUT,
        "SRC_BASE": F143_BASE_OUT,
        "OLD_QDRV_SHA": F143_QDRV_SHA,
        "NEW_QDRV_SHA": NEW_QDRV_SHA,
        "NEW_QDRV": NEW_QDRV,
        "BUILD_PROFILE": BUILD_PROFILE,
        "MODULE_MANIFEST": MODULE_MANIFEST,
    }
    try:
        for name, value in replacements.items():
            setattr(f143, name, value)
        yield
    finally:
        for name, value in old.items():
            setattr(f143, name, value)


def patch_cpio(raw: bytes):
    with f144_context():
        patched, report = ORIGINAL_PATCH_CPIO(raw)
    report["qdrv"]["fixes"] = [
        "bind Quantenna node scheduler state to qdisc_sleeping on Linux 5.10",
        "preserve F143 deferred hostlink DMA frees",
        "preserve GFP_DMA | GFP_ATOMIC disassociation allocation",
        "preserve the HGW-specific disabled hang-recovery timer",
    ]
    report["start_script"]["fixes"] = [
        "keeps F143 RF/VAP/userspace ordering and TX-power behavior",
        "updates the qdrv integrity expectation for the qdisc-binding rebuild",
        "does not change 2.4 GHz, rates, rings, forwarding, bridge topology or auc_tx",
    ]
    return patched, report


def main() -> int:
    data = NEW_QDRV.read_bytes()
    if hashlib.sha256(data).hexdigest() != NEW_QDRV_SHA:
        raise SystemExit("F144 rebuilt qdrv hash mismatch")
    if b"OMQDRVSCH stage=bind source=qdisc-sleeping" not in data:
        raise SystemExit("F144 rebuilt qdrv lacks qdisc binding marker")

    original_patch_cpio = f143.patch_cpio
    with f144_context():
        f143.patch_cpio = patch_cpio
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                rc = f143.main()
        finally:
            f143.patch_cpio = original_patch_cpio
    if rc:
        return rc

    manifest_path = OUT / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="ascii"))
    manifest["change_scope"] = {
        "radio2g": "unchanged from F143",
        "radio5_start": "unchanged from F143 except qdrv integrity hash",
        "radio5_stop": "unchanged from F143",
        "radio5_modules": "only qdrv.ko replaced from the verified 25-module build",
        "qdrv": "Linux 5.10 node scheduler binding uses qdisc_sleeping instead of the transient active qdisc",
        "wlan": "unchanged from F143",
        "rates_rings_forwarding_auc_tx": "unchanged from F143",
        "bridge_topology": "unchanged from F143",
    }
    manifest["runtime_policy"] = {
        "qdisc_node_binding": "qdisc_sleeping on Linux >= 4.20",
        "hr_timer": "disabled for HGW-500BNA-QCv2 before timer setup",
        "disassoc_dma_allocation": "GFP_DMA | GFP_ATOMIC",
        "hostlink_dma_free": "deferred to system workqueue from interrupt/IRQ-disabled context",
        "expected_effect": "make locally generated AP-to-client frames visible to the active Quantenna scheduler",
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
