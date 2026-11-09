#!/usr/bin/env python3
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PCI = ROOT / "work/kernel-port/linux-5.10/drivers/net/wireless/realtek/rtlwifi/pci.c"
OEM = ROOT / "work/sources/rtl8198c-rtk-ref/rtk_openwrt_sdk/target/linux/realtek/files/drivers/net/wireless/rtl8192cd/WlanHAL/HalCfg.h"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    pci = PCI.read_text(encoding="utf-8", errors="replace")
    oem = OEM.read_text(encoding="utf-8", errors="replace")

    require("#define TXBD_SEG_32_64_SEL      0" in oem,
            "OEM global 8-byte TXBD segment contract missing")
    require("#define TX_BCNQ_TXBD_MODE_SEL   1" in oem,
            "OEM four-segment beacon mode missing")
    require("#define TXBD_BEACON_OFFSET_V1       128" in oem,
            "OEM RTL8192E beacon aperture is not 128 bytes")

    require("#define RTL8192EE_BCN_TXBD_APERTURE_BYTES 128" in pci,
            "Linux beacon aperture constant missing")
    require("RTL8192EE_BCN_TXBD_APERTURE_BYTES / 32" in pci,
            "compact BCNQ does not reserve four 32-byte entries")
    require("rtlpci->txbd_compact32" in pci and
            "rtlpci->irq_line_lifecycle_managed" in pci and
            "rtlhal->hw_type == HARDWARE_TYPE_RTL8192EE" in pci,
            "beacon aperture change is not target gated")
    require("OMRTLTX17 stage=beacon-aperture" in pci,
            "runtime aperture marker missing")
    require("rtlpci->tx_ring[prio].buffer_desc_stride * entries" in pci,
            "allocation no longer derives from stride and entries")
    require("prio <= VO_QUEUE ?" not in pci,
            "hybrid per-queue width logic returned")

    print("STATIC_PASS tx17=all32-plus-rtl8192e-beacon-aperture")
    print("STATIC_PASS scope=allocation-only no-own-no-reclaim-no-rate-no-ampdu-no-irq")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
