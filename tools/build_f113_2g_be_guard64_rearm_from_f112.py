#!/usr/bin/env python3
"""Build F113 from F112 by widening the 2.4 GHz BE queue guard.

F112 proves the BE reclaim-rearm path works and restores full 32 MiB transfers,
but the AP still throttles around the guard16 stop/reclaim loop.  F113 keeps
the F112 image intact and changes only ``usr/sbin/om-radio-modules`` so the BE
queue guard is 64/32 while reclaim polling and the F112 rtl_pci.ko remain
unchanged.
"""
from __future__ import annotations

import json
from pathlib import Path

import build_f107_2g_be_guard64_rearm_from_f106 as base
import build_f71_qcsapi_interp_from_f70 as f71


base.BUILD_TAG = "f113-2g-be-guard64-rearm-from-f112"
base.OUT = base.ROOT / f"work/mission-state/q3-persistent-composite-{base.BUILD_TAG}/build"
base.BASE_OUT = f"openmitrastar-linux510-q3-persistent-{base.BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
base.SRC_BUILD = base.ROOT / "work/mission-state/q3-persistent-composite-f112-2g-be-reclaim-rearm-from-f111/build"
base.SRC_BASE = "openmitrastar-linux510-q3-persistent-f112-2g-be-reclaim-rearm-from-f111-LZMA-OFFLINE-NO-FLASH"


def main() -> int:
    rc = base.main()
    if rc != 0:
        return rc

    manifest_path = base.OUT / "manifest.json"
    result_path = base.OUT / "build-result.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema"] = "openmitrastar.q3-persistent-composite-f113-2g-be-guard64-rearm-from-f112/v1"
    manifest["classification"] = "F113_FROM_F112_2G_BE_GUARD64_REARM_FIXEDSIZE"
    manifest["change_scope"] = {
        "radio2g_loader": "changed only rtl_pci BE queue guard from 16/8 to 64/32; hgw500_tx_reclaim_poll remains enabled",
        "radio2g_module": "unchanged from F112: rtl_pci.ko BE reclaim-rearm build",
        "radio2g_rates_crypto": "unchanged from F112: MCS7 forced, MCS15 off, swenc=0",
        "kernel_emac": "unchanged from F112",
        "emac_poll_fallback": "unchanged from F112",
        "rootfs_initramfs": "fixed-size CPIO patch; raw payload size, CPIO end and post-CPIO remainder preserved",
        "radio5_modules": "unchanged from F112/F111",
        "qdrv": "unchanged from F112/F111",
        "bridge": "unchanged from F112/F111",
        "flash_layout": "unchanged",
    }
    manifest["source"]["build_dir"] = str(base.SRC_BUILD.relative_to(base.ROOT))
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="ascii")

    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["schema"] = "openmitrastar.f113-2g-be-guard64-rearm-from-f112-build/v1"
    result["build_dir"] = str(base.OUT)
    result_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="ascii")

    sha_path = base.OUT / "SHA256SUMS"
    lines = []
    for path in sorted(p for p in base.OUT.iterdir() if p.is_file() and p.name != "SHA256SUMS"):
        lines.append(f"{f71.sha256(path.read_bytes())}  {path.name}")
    sha_path.write_text("\n".join(lines) + "\n", encoding="ascii")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
