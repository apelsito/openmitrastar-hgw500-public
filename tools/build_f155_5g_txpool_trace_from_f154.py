#!/usr/bin/env python3
"""Build F155 from F154 with read-only AuC/TQE/HBM counters."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import build_f143_5g_deferred_dma_free_from_f142 as engine
import build_f153_5g_rx_inactivity_refresh_from_f152 as pair_builder
import build_f154_5g_gso_segment_from_f153 as f154


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f155-5g-txpool-trace-from-f154"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F155_FROM_F154_5G_TXPOOL_TRACE"

SRC_BUILD = f154.OUT
SRC_BASE = f154.BASE_OUT
OLD_QDRV_SHA = f154.NEW_QDRV_SHA
NEW_QDRV_SHA = "0ef6cac2fe68ba62dcba21c4878b9d4697d8e6560579bf74f3ed9a5ae09c0dff"
WLAN_SHA = f154.WLAN_SHA

MODULE_BUILD = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-txpool-trace-f155-20260831"
MODULE_ROOT = MODULE_BUILD / "rootfs/lib/modules/5.10.260-openmitrastar-radiohw/extra/quantenna"
NEW_QDRV = MODULE_ROOT / "qdrv/qdrv.ko"
BUILT_WLAN = MODULE_ROOT / "wlan/wlan.ko"
BUILD_PROFILE = MODULE_BUILD / "build-profile.env"
MODULE_MANIFEST = MODULE_BUILD / "module-manifest.tsv"


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@contextlib.contextmanager
def variant_context():
    engine_names = (
        "BUILD_TAG", "OUT", "BASE_OUT", "CLASSIFICATION", "SRC_BUILD",
        "SRC_BASE", "OLD_QDRV_SHA", "NEW_QDRV_SHA", "NEW_QDRV",
        "BUILD_PROFILE", "MODULE_MANIFEST", "WLAN_SHA",
    )
    engine_old = {name: getattr(engine, name) for name in engine_names}
    engine_values = {
        "BUILD_TAG": BUILD_TAG,
        "OUT": OUT,
        "BASE_OUT": BASE_OUT,
        "CLASSIFICATION": CLASSIFICATION,
        "SRC_BUILD": SRC_BUILD,
        "SRC_BASE": SRC_BASE,
        "OLD_QDRV_SHA": OLD_QDRV_SHA,
        "NEW_QDRV_SHA": NEW_QDRV_SHA,
        "NEW_QDRV": NEW_QDRV,
        "BUILD_PROFILE": BUILD_PROFILE,
        "MODULE_MANIFEST": MODULE_MANIFEST,
        "WLAN_SHA": WLAN_SHA,
    }
    pair_names = (
        "OLD_QDRV_SHA", "NEW_QDRV_SHA", "WLAN_SHA", "NEW_QDRV",
        "BUILT_WLAN",
    )
    pair_old = {name: getattr(pair_builder, name) for name in pair_names}
    pair_values = {
        "OLD_QDRV_SHA": OLD_QDRV_SHA,
        "NEW_QDRV_SHA": NEW_QDRV_SHA,
        "WLAN_SHA": WLAN_SHA,
        "NEW_QDRV": NEW_QDRV,
        "BUILT_WLAN": BUILT_WLAN,
    }
    try:
        for name, value in engine_values.items():
            setattr(engine, name, value)
        for name, value in pair_values.items():
            setattr(pair_builder, name, value)
        yield
    finally:
        for name, value in pair_old.items():
            setattr(pair_builder, name, value)
        for name, value in engine_old.items():
            setattr(engine, name, value)


def main() -> int:
    for path, expected in ((NEW_QDRV, NEW_QDRV_SHA), (BUILT_WLAN, WLAN_SHA)):
        if not path.is_file() or sha256(path.read_bytes()) != expected:
            raise SystemExit(f"F155 module missing or changed: {path}")
    qdrv = NEW_QDRV.read_bytes()
    for marker in (
        b"OMQTNINACT stage=rx-refresh",
        b"OMQDRVTXGSO stage=segmented",
        b"OMQDRVTXPOOL total=",
        b"openmitrastar_auc_busy_total",
    ):
        if marker not in qdrv:
            raise SystemExit(f"F155 qdrv marker missing: {marker!r}")

    original = engine.patch_cpio
    with variant_context():
        engine.patch_cpio = pair_builder.patch_cpio
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
        "radio2g": "unchanged from F154",
        "radio5_start_stop_security_topology": "unchanged from F154",
        "radio5_modules": "only qdrv.ko replaced; wlan.ko remains byte-identical",
        "qdrv_tx": "F154 GSO segmentation retained; add read-only AuC/TQE/HBM counters",
        "queues_dma_rates_rings_forwarding_auc_tx": "behavior unchanged from F154",
    }
    manifest["runtime_policy"] = {
        "telemetry": [
            "AuC submit and NETDEV_TX_BUSY totals",
            "GSO input, produced-segment and local-drop totals",
            "EMAC RX and TX-done pool availability around submit failures",
        ],
        "expected_effect": "distinguish HBM exhaustion from post-segmentation RF/BA failure",
        "persistent_flash_writes": 0,
    }
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii"
    )
    sums_path = OUT / "SHA256SUMS"
    lines = []
    for line in sums_path.read_text(encoding="ascii").splitlines():
        _digest, name = line.split("  ", 1)
        path = OUT / name
        lines.append(f"{sha256(path.read_bytes())}  {name}")
    sums_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    print(json.dumps(manifest, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
