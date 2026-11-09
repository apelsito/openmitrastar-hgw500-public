#!/usr/bin/env python3
"""Build F154 from F153 with software GSO segmentation before AuC TX."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
from pathlib import Path

import build_f143_5g_deferred_dma_free_from_f142 as engine
import build_f153_5g_rx_inactivity_refresh_from_f152 as f153


ROOT = Path(__file__).resolve().parents[1]
BUILD_TAG = "f154-5g-gso-segment-from-f153"
OUT = ROOT / f"work/mission-state/q3-persistent-composite-{BUILD_TAG}/build"
BASE_OUT = f"openmitrastar-linux510-q3-persistent-{BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
CLASSIFICATION = "F154_FROM_F153_5G_GSO_SEGMENT"

SRC_BUILD = f153.OUT
SRC_BASE = f153.BASE_OUT
OLD_QDRV_SHA = f153.NEW_QDRV_SHA
NEW_QDRV_SHA = "dcc4abaaeb92f0f5435860e206369ade67e7ba6e60d52f651eb1951b423a1443"
WLAN_SHA = f153.WLAN_SHA

MODULE_BUILD = ROOT / "outputs/kernel-port/quantenna-linux510-radiohw-gso-segment-f154-20260831"
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
    f153_names = (
        "OLD_QDRV_SHA", "NEW_QDRV_SHA", "WLAN_SHA", "NEW_QDRV",
        "BUILT_WLAN",
    )
    f153_old = {name: getattr(f153, name) for name in f153_names}
    f153_values = {
        "OLD_QDRV_SHA": OLD_QDRV_SHA,
        "NEW_QDRV_SHA": NEW_QDRV_SHA,
        "WLAN_SHA": WLAN_SHA,
        "NEW_QDRV": NEW_QDRV,
        "BUILT_WLAN": BUILT_WLAN,
    }
    try:
        for name, value in engine_values.items():
            setattr(engine, name, value)
        for name, value in f153_values.items():
            setattr(f153, name, value)
        yield
    finally:
        for name, value in f153_old.items():
            setattr(f153, name, value)
        for name, value in engine_old.items():
            setattr(engine, name, value)


def main() -> int:
    for path, expected in ((NEW_QDRV, NEW_QDRV_SHA), (BUILT_WLAN, WLAN_SHA)):
        if not path.is_file() or sha256(path.read_bytes()) != expected:
            raise SystemExit(f"F154 module missing or changed: {path}")
    qdrv = NEW_QDRV.read_bytes()
    for marker in (b"OMQTNINACT stage=rx-refresh", b"OMQDRVTXGSO stage=segmented"):
        if marker not in qdrv:
            raise SystemExit(f"F154 qdrv marker missing: {marker!r}")

    original = engine.patch_cpio
    with variant_context():
        engine.patch_cpio = f153.patch_cpio
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
        "radio2g": "unchanged from F153",
        "radio5_start_stop_security_topology": "unchanged from F153",
        "radio5_modules": "only qdrv.ko replaced; wlan.ko remains byte-identical",
        "qdrv_tx": "software-segment GSO packets before direct AuC/TQE submission",
        "inactivity_fix": "retained byte-for-byte from F153 source behavior",
        "queues_dma_rates_rings_forwarding_auc_tx": "unchanged from F153",
    }
    manifest["runtime_policy"] = {
        "gso_scope": "HGW HOSTAP auc_tx data frames with skb_is_gso",
        "expected_effect": "prevent oversized bridged TCP SKBs from reaching legacy AuC/TQE",
        "normal_skb_path": "unchanged",
        "gso_trace": "first 64 segment or failure events; no MAC addresses",
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
