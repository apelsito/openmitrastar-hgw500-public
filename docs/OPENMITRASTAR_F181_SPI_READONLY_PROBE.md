# OpenMitraStar F181 SPI read-only probe

Date: `2026-09-01`

F181 is a standalone ARC700 kernel module that reads only the Topaz SPI NOR
JEDEC ID and status register.

Expected hardware:

- flash: Macronix `MX25L12836E`;
- JEDEC ID: `0xc22018`;
- controller base: `0xe4030000`.

The module contains no register writes, MTD registration, erase callback or
write callback. Its `write_capable` parameter is permanently false.

This is the required probe before implementing a bounded `lyoko_store` write
driver. The module remains offline and has not been loaded on the router.

## Built artifact

- Module: `outputs/kernel-port/f181-spi-readonly-probe-20260901/qtn-topaz-spi-probe.ko`
- Size: `4,840` bytes
- SHA-256: `34f7fb7aeccb741b97f7d6d8d4c4f43be561024aa490dd0a1d9588365f678485`
- ABI: ELF32 ARCompact ARC700 v4, statically linked kernel module
- Tests: `2 passed`
- Hardware actions: none
