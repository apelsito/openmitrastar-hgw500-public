#!/usr/bin/env python3
"""Build F100 from F99 with RTL8192EE management tracing off by default."""
from __future__ import annotations

import build_f99_2g_mcs7_fixedrate_from_f98 as base


base.BUILD_TAG = "f100-2g-mcs7-fixedrate-quiet-from-f99"
base.OUT = base.ROOT / f"work/mission-state/q3-persistent-composite-{base.BUILD_TAG}/build"
base.BASE_OUT = f"openmitrastar-linux510-q3-persistent-{base.BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
base.F98_BUILD = base.ROOT / "work/mission-state/q3-persistent-composite-f99-2g-mcs7-fixedrate-from-f98/build"
base.F98_BASE = "openmitrastar-linux510-q3-persistent-f99-2g-mcs7-fixedrate-from-f98-LZMA-OFFLINE-NO-FLASH"
base.REALTEK_BUNDLE = base.ROOT / "outputs/kernel-port/realtek-loop/all64-mcs7-fixedrate-quiet-f100-RAM-ONLY-NO-FLASH"
base.MODULE_REPLACEMENTS = {
    base.RTL8192EE_ENTRY: base.REALTEK_BUNDLE / "modules/rtl8192ee.ko",
}
base.CLASSIFICATION = "F100_FROM_F99_2G_RTL8192EE_MCS7_FIXEDRATE_QUIET_FIXEDSIZE"
base.MODULE_SCOPE = "replaced only rtl8192ee.ko with the F100 fixed-rate quiet-performance build"
base.RATE_SCOPE = (
    "keeps F99 fixed-rate descriptor behavior and adds hgw500_mgmt_trace=0 default "
    "to suppress OMRTLMGMT RX/TX log flood during throughput runs"
)


if __name__ == "__main__":
    raise SystemExit(base.main())
