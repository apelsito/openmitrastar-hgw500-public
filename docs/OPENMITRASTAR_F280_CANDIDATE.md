# OpenMitraStar F280 Full offline successor

Date: 2026-09-03

## Artifact

- Runtime: `lyoko-foundation-6.3.4-f280-store-driver-disabled-device`
- Classification: `PRIVATE_DEVICE_BOUND_OFFLINE_SUCCESSOR_HOLD`
- Candidate bytes: `5263360`
- Candidate SHA-256: `a9b418569b4643b121e0bfb1c6c96d3eafefeea150decd8e9ff6f1a9312ad82f`
- Rootfs SHA-256: `610f5be3c3962291940a46d145f2b871d5226d6f22de619782fb6cc6c1616595`
- Full-slot CRC32: `87dfc115`
- Full-slot SHA-256: `25e8de1498ff7e34e3becab6fc84fcc6238f12110e810a7acc40e5caf2379d0f`
- Candidate eligible: false
- Flash supported: false
- Hardware validation: NOT RUN

## Change

F280 inherits F278 and adds only:

- `/lib/modules/5.10.260-openmitrastar-radiohw/openmitrastar/storage/qtn-topaz-store-mtd.ko`;
- `/etc/openmitrastar/features/store-mtd-driver-v1` with
  `OPENMITRASTAR_STORE_MTD_DRIVER=0`;
- release identity.

The module is not referenced by any init script and therefore cannot load at
boot. Even if loaded manually without parameters, it registers a read-only MTD
because `allow_write` defaults to false.

## Module contract

- ARC700 Linux 5.10 module: `7624` bytes.
- SHA-256: `82c7a4eb61e62999fca458fac008b7063aaa68f04ef0757c76c8690033c62b1d`.
- Vermagic: `5.10.260-openmitrastar-radiohw mod_unload ARC700`.
- All 17 imports exist in the exact kernel export table.
- Expected flash identity: Macronix `0xc22018`.
- Addressable range: physical `0xdc0000..0xf7ffff` only.
- Erase granularity: 64 KiB.
- Program granularity: pages of at most 256 bytes.
- Every programmed page is read back before the driver advances.
- Bulk erase is absent.

## Validation

- F280 builder and inherited contract tests: PASS.
- F279 module and store transaction tests: PASS.
- Combined focused suite: 8 PASS.
- Packaged `SHA256SUMS`: PASS.
- Kernel, DTB and kernel config are byte-identical to F278/F277/F276.
- `lyoko_store` remains erased in the firmware image.

## Boundary

F280 is not eligible for flash. Before promotion, F277 must complete its
physical Quantenna gate, and the store module must first be loaded read-only to
measure the Macronix protection state and verify that the overlapping
`map_rom` view remains stable. A write-capable load requires a separate,
recovery-backed single-eraseblock campaign.

