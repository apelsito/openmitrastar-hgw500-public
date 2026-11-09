#!/usr/bin/env python3
"""Build F114 from F112 by disabling the 2.4 GHz BE queue guard.

F112 proves BE reclaim can complete real transfers, but throughput is still
limited by repeated guard stop/reclaim cycles.  F114 keeps the F112 kernel,
rtl_pci.ko, rates, bridge and 5 GHz payload unchanged, and changes only the
2.4 GHz loader parameter ``hgw500_tx_queue_guard`` to 0.  Reclaim-poll remains
present in the module but should not throttle BE when the guard is disabled.
"""
from __future__ import annotations

import json

import build_f107_2g_be_guard64_rearm_from_f106 as base
import build_f71_qcsapi_interp_from_f70 as f71


base.BUILD_TAG = "f114-2g-no-be-guard-from-f112"
base.OUT = base.ROOT / f"work/mission-state/q3-persistent-composite-{base.BUILD_TAG}/build"
base.BASE_OUT = f"openmitrastar-linux510-q3-persistent-{base.BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
base.SRC_BUILD = base.ROOT / "work/mission-state/q3-persistent-composite-f112-2g-be-reclaim-rearm-from-f111/build"
base.SRC_BASE = "openmitrastar-linux510-q3-persistent-f112-2g-be-reclaim-rearm-from-f111-LZMA-OFFLINE-NO-FLASH"
base.NEW_LOAD = (
    "hgw500_eapol_trace=$radio2g_eapol_trace "
    "hgw500_eapol_mgnt_queue=$radio2g_eapol_mgnt_queue "
    "hgw500_tx_queue_guard=0 hgw500_tx_queue_guard_high=16 "
    "hgw500_tx_queue_guard_low=8  hgw500_tx_reclaim_poll=1"
)
base.NEW_VERIFY = (
    "hgw500_txbd_be_legacy64=N hgw500_tx_queue_guard=N \\\n"
    "\t\t\thgw500_tx_queue_guard_high=16 hgw500_tx_queue_guard_low=8  \\\n"
    "\t\t\thgw500_txbd_final_readback=N hgw500_tx_reclaim_poll=Y"
)
base.NEW_PROFILE = "profile=all64-mcs7-eapol-mgntq-noguard-nosplit"


def main() -> int:
    rc = base.main()
    if rc != 0:
        return rc

    manifest_path = base.OUT / "manifest.json"
    result_path = base.OUT / "build-result.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["schema"] = "openmitrastar.q3-persistent-composite-f114-2g-no-be-guard-from-f112/v1"
    manifest["classification"] = "F114_FROM_F112_2G_NO_BE_GUARD_FIXEDSIZE"
    manifest["change_scope"] = {
        "radio2g_loader": "changed only rtl_pci BE queue guard from enabled to disabled; hgw500_tx_reclaim_poll remains available",
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
    result["schema"] = "openmitrastar.f114-2g-no-be-guard-from-f112-build/v1"
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
