# OpenMitraStar F295 store protection observer

Date: 2026-09-04

F295 is a standalone ARC700 module for inspecting the raw protection state of
the SPI NOR region reserved for `lyoko_store`.

## Artifact

- Module: `qtn-topaz-store-protection-observer.ko`
- Bytes: `8368`
- SHA-256: `2f00a2db7103e0eb5691d86ae9122cdb22e34d935d7042339d131d2e55c906f8`
- Vermagic: `5.10.260-openmitrastar-radiohw mod_unload ARC700`
- Build and symbol contract: PASS.
- Hardware load: NOT RUN.

## Read-only contract

The module can observe:

- JEDEC identity;
- status and security registers;
- raw DPB values for all 28 store eraseblocks;
- whether the SPI controller configuration was restored after the reads.

The module contains no page-program, sector-erase, write-enable, write-disable,
DPB-write, global-lock/unlock or MTD-registration path. It maps only the SPI
controller, not the flash data window. The command selector is written solely
to issue the OEM-derived read opcodes for SCUR and DPB.

No DPB value is interpreted as locked or unlocked until hardware output and the
exact flash behavior are correlated. F295 reports zero/nonzero raw counts only.

## Live baseline before F295

Read-only F292 inspection showed:

- `lyoko_store`: 1,835,008 bytes;
- erase size: 65,536 bytes;
- type: `rom`;
- flags: `0x0`;
- not mounted;
- `/persist` remains JFFS2 read-only.

No module was loaded and no MTD data was read or written during this work.

The future physical gate is `tools/run_f296_store_protection_probe.ps1`. It
captures UART, hashes the complete store before and after observation, verifies
that `/proc/mtd` is unchanged and unloads the module before declaring PASS.
