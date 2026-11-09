#!/usr/bin/env python3
"""Build F106 from F104 by replacing only rtl_pci.ko.

F105 proved that synchronous TX-side reclaim was too aggressive.  F106 keeps
F104's loader/rate/bridge/EMAC/5 GHz policy and replaces only ``rtl_pci.ko``:
when BE guard stop finds ``schedule_delayed_work(...)=0``, it uses
``mod_delayed_work(system_wq, ...)`` to rearm the normal RX-work reclaim path.
"""
from pathlib import Path

import build_f105_2g_be_reclaim_kick_from_f104 as base


base.BUILD_TAG = "f106-2g-be-reclaim-rearm-from-f104"
base.OUT = base.ROOT / f"work/mission-state/q3-persistent-composite-{base.BUILD_TAG}/build"
base.BASE_OUT = f"openmitrastar-linux510-q3-persistent-{base.BUILD_TAG}-LZMA-OFFLINE-NO-FLASH"
base.REALTEK_BUNDLE = base.ROOT / "outputs/kernel-port/realtek-loop/all64-mcs7-be-reclaim-rearm-f106-RAM-ONLY-NO-FLASH"
base.MODULE_REPLACEMENTS = {
    base.RTL_PCI_ENTRY: base.REALTEK_BUNDLE / "modules/rtl_pci.ko",
}
base.CLASSIFICATION = "F106_FROM_F104_2G_RTL_PCI_BE_RECLAIM_REARM_FIXEDSIZE"
base.MODULE_SCOPE = "replaced only rtl_pci.ko with the F106 BE reclaim-rearm build"
base.RECLAIM_SCOPE = (
    "when BE guard stop sees schedule_delayed_work return 0, rearm the normal "
    "RX-work reclaim path with mod_delayed_work instead of completing TX in "
    "the transmit path"
)


if __name__ == "__main__":
    raise SystemExit(base.main())
