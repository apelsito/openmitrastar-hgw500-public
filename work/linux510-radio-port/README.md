# OpenMitraStar Linux 5.10 radio port

> Public source snapshot. [Scope, provenance and verification](docs/PUBLIC_SNAPSHOT.md).

This directory contains compile-only porting work for the HGW-500BNA-QCv2.
Nothing here is a flash image and the build scripts must not access MTD.

Hardware contract:

- CPU: little-endian ARC700 at 500 MHz, MMUv2, 8 KiB pages.
- 5 GHz: native Quantenna Topaz/QMAC controlled by `qdrv`, MuC, DSP and AuC.
- 2.4 GHz: Realtek PCIe device handled by the OEM `rtl8192cd` stack.

The immediate gates are source compilation, shared-structure ABI checks and
offline firmware validation. Hardware enablement remains disabled until the
RAM-only boot path, IRQ ownership, DMA coherency and calibration handoff are
independently proven.
