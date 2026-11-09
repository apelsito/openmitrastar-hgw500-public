#!/usr/bin/env python3
"""Build F147 from F146 by restoring post-start read-only qdrv GET commands."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import build_f143_5g_deferred_dma_free_from_f142 as engine
import build_f146_5g_auc_submit_trace_from_f145 as f146


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f147-5g-readonly-get-from-f146"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F147_FROM_F146_5G_READONLY_GET"
OLD_QDRV_SHA = f146.NEW_QDRV_SHA
NEW_QDRV_SHA = "ed2a1ce601089bb2cbb6b52d0d4444839da927dd6443124d11856cddc900f387"
NEW_QDRV = (
    ROOT
    / "outputs/kernel-port/quantenna-linux510-radiohw-readonly-get-f147-20260831"
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
        "SRC_BUILD": f146.OUT,
        "SRC_BASE": f146.BASE_OUT,
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
        "allow read-only qdrv get commands after sequential bring-up",
        "keep set/start/stop and non-allowlisted commands guarded",
        "preserve all F146 data-path behavior and diagnostics",
    ]
    report["start_script"]["fixes"] = [
        "keeps F146 RF/VAP/userspace ordering and TX-power behavior",
        "updates the qdrv integrity expectation for the read-only diagnostics build",
        "does not change 2.4 GHz, rates, rings, forwarding, bridge topology or auc_tx",
    ]
    return patched, report


def main() -> int:
    data = NEW_QDRV.read_bytes()
    if hashlib.sha256(data).hexdigest() != NEW_QDRV_SHA:
        raise SystemExit("F147 rebuilt qdrv hash mismatch")
    for marker in (
        b"OMQDRVTXPATH stage=auc-submit",
        b"OMQDRVHLINK stage=free-deferred",
    ):
        if marker not in data:
            raise SystemExit(f"F147 rebuilt qdrv missing marker: {marker!r}")

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
        "radio2g": "unchanged from F146",
        "radio5_start": "unchanged from F146 except qdrv integrity hash",
        "radio5_stop": "unchanged from F146",
        "radio5_modules": "only qdrv.ko replaced from the verified 25-module build",
        "qdrv": "sequential guard permits read-only get commands after start",
        "wlan": "unchanged from F146",
        "queues_dma_rates_rings_forwarding_auc_tx": "behavior unchanged from F146",
        "bridge_topology": "unchanged from F146",
    }
    manifest["runtime_policy"] = {
        "post_start_get": "allowed for read-only qdrv diagnostics",
        "post_start_mutation": "still rejected by sequential bring-up guard",
        "auc_submit_trace": "preserved from F146",
        "hostlink_dma_free": "deferred from interrupt/IRQ-disabled context",
        "expected_effect": "make assoc_q and auc_stats available without changing radio state",
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
