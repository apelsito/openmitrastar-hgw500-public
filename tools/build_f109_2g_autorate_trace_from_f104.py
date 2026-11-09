#!/usr/bin/env python3
"""Build F109 from F104 by disabling forced 2.4 GHz data rate.

This reuses the fixed-size F108 recomposer but changes the single rate policy:
rtl8192ee keeps bounded tx descriptor tracing enabled, while both forced data
rate selectors are disabled so the normal mac80211/firmware rate decision can
run on top of the proven F104 BE guard baseline.
"""
from __future__ import annotations

from pathlib import Path

import build_f108_2g_mcs15_trace_from_f104 as base


base.BUILD_TAG = "f109-2g-autorate-trace-from-f104"
base.OUT = base.ROOT / f"work/mission-state/q3-persistent-composite-{base.BUILD_TAG}/build"
base.BASE_OUT = f"openmitrastar-linux510-q3-persistent-{base.BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
base.SCHEMA = "openmitrastar.q3-persistent-composite-f109-2g-autorate-trace-from-f104/v1"
base.CLASSIFICATION = "F109_FROM_F104_2G_AUTORATE_TRACE_FIXEDSIZE"
base.RESULT_SCHEMA = "openmitrastar.f109-2g-autorate-trace-from-f104-build/v1"
base.PATCH_APPLIED = ["radio2g-disable-forced-data-rate-from-f104", "radio2g-rate-trace-default-on"]
base.VERIFY_MARKERS = (
    b"hgw500_force_data_mcs7=0",
    b"hgw500_force_data_mcs15=0",
    b"hgw500_tx_rate_trace=1",
    b"hgw500_force_data_mcs7=N",
    b"hgw500_force_data_mcs15=N",
    b"hgw500_tx_rate_trace=Y",
)
base.NEW_LOAD = (
    "hgw500_force_data_mcs7=0 hgw500_force_data_mcs15=0 "
    "hgw500_force_data_11m=0 hgw500_txbd_be_data_split=0 hgw500_tx_rate_trace=1"
)
base.NEW_VERIFY = (
    "hgw500_force_data_mcs7=N hgw500_force_data_mcs15=N \\\n"
    "\t\t\thgw500_force_data_11m=N hgw500_txbd_be_data_split=N \\\n"
    "\t\t\thgw500_tx_rate_trace=Y; do"
)
base.PROFILE_REPLACEMENTS = (
    ("profile=all64-mcs7-eapol-mgntq-guard16-nosplit", "profile=all64-auto-eapol-mgntq-guard16-nosplit"),
    ("profile=mcs7-noguard-nosplit", "profile=auto-noguard-nosplit"),
    ("profile=mcs7-noguard-nosplit", "profile=auto-noguard-nosplit"),
)
base.CHANGE_SCOPE = {
    "radio2g_loader": "changed only rtl8192ee forced data selectors to autorate and enabled bounded tx_rate_trace",
    "radio2g_modules": "unchanged binaries from F104",
    "radio2g_queue_reclaim": "unchanged from F104: BE guard 16/8 and hgw500_tx_reclaim_poll=1",
    "radio2g_dma_rings_crypto": "unchanged from F104: TXBD64, dma_wmb, page_units=2, swenc=0",
    "kernel_emac": "unchanged from F104",
    "bridge": "unchanged from F104",
    "radio5_modules": "unchanged from F104; still manual/off in current product gate",
    "qdrv": "unchanged from F104",
    "flash_layout": "unchanged",
    "rootfs_initramfs": "fixed-size CPIO patch; raw payload size, CPIO end and post-CPIO remainder preserved",
}


if __name__ == "__main__":
    raise SystemExit(base.main())
