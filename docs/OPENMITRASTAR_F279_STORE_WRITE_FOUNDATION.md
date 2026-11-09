# OpenMitraStar F279 lyoko_store write foundation

Date: 2026-09-03

## Live hardware facts

F276 exposes the reserved store as Linux `mtd4`:

- name: `lyoko_store`;
- size: `0x1c0000` (`1,835,008` bytes);
- erase size: `0x10000` (`65,536` bytes);
- type: `rom`;
- flags: `0x0`;
- JFFS2 support: present in the running kernel;
- mounted: no.

The current image intentionally has no `flash_erase`, `mtd_debug`, `nandwrite`
or equivalent write utility. No live write or mount was attempted.

## Offline transaction contract

`tools/lyoko_store_transaction.py` models two independent operations:

1. Initialize only the 28 store eraseblocks at physical offsets
   `0xdc0000..0xf7ffff`.
2. Update only the 94 firmware-prefix eraseblocks at physical offsets
   `0x7e0000..0xdbffff`, preserving the initialized store byte for byte.

The real F277 candidate and the generic F211 JFFS2 image produced:

- F277 blank-slot SHA-256:
  `825cdc0aceabda3fb86b3c12aa31fd835fe6a291bd04f82ef97135971fab8915`;
- initialized-slot SHA-256:
  `6e3413b7ca9cf0d9a091aad0140912a8de68dde0b41efe55d00513e1c8e56615`;
- F278 store-preserving updated-slot SHA-256:
  `008159643863478fbcb5a9074d9f4cf9f1494d34835a73866dd1ed771b3867ca`.

Both generated bundles contain their own `SHA256SUMS`. No hardware command is
emitted by the simulator.

## ARC700 module

F279 provides the first Linux 5.10 module implementing a bounded MTD device for
the store:

- artifact: `qtn-topaz-store-mtd.ko`;
- bytes: `7624`;
- SHA-256: `82c7a4eb61e62999fca458fac008b7063aaa68f04ef0757c76c8690033c62b1d`;
- vermagic: `5.10.260-openmitrastar-radiohw mod_unload ARC700`;
- expected JEDEC: `0xc22018` (`MX25L12836E`);
- exported MTD name: `lyoko_store_rw`;
- write enable default: false;
- module autoload: false;
- bulk erase: absent.

All 17 imported symbols were checked against the exported symbol table of the
exact F223/F276 kernel lineage. The module and transaction tests report 7 PASS,
and all packaged hashes verify.

## Boundary

This is an offline engineering artifact, not a flash or module-load candidate.
Before any write-capable load, Lyoko must inspect the Macronix security register
and dynamic-protection bits read-only, prove that the overlapping ROM mapping
does not create an ownership conflict, and execute a separate recovery-backed
single-eraseblock experiment. Until then `lyoko_store` remains read-only.
