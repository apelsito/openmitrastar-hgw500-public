# OpenMitraStar F318 bounded store transaction core

Date: 2026-09-05

## Result

F318 replaces the unsafe transaction policy of the historical F279 prototype
with a portable, offline transaction core for the two Lyoko journal slots.
It does not access SPI registers, register an MTD, emit flash opcodes or produce
a firmware image.

- Artifact: `libf318store.a`
- Bytes: `3,774`
- SHA-256:
  `93950f425444f9bf236488fb072be6061028412c631071b406a9cc2a7ce50130`
- Reproducible ARC700 builds: PASS.

The two permitted eraseblocks are fixed at physical offsets `0x00dc0000` and
`0x00dd0000`. The other 26 eraseblocks reserved for `lyoko_store`, the firmware
prefix and every protected partition are outside the write API.

## Transaction contract

Each slot stores at most 256 payload bytes in one dedicated 64 KiB eraseblock.
A write requires an exclusive controller claim and performs:

1. snapshot the target protection value and cross-partition protection
   witnesses;
2. unprotect only the target block through an injected provider operation;
3. verify the target is unprotected;
4. erase only the target eraseblock;
5. write and verify a versioned header plus payload and CRC32;
6. write a final commit marker using a NOR-safe `1 -> 0` transition;
7. restore the exact original target protection value;
8. verify the target and all protection witnesses match their original values;
9. release the controller owner.

Failure after unprotect always attempts exact target-block protection restore.
An unexpected change to another sampled block is reported as a witness failure.
The API intentionally has no global lock or global unlock operation.

## Why this remains offline

The F310 read-only observer caused an ARC Machine Check when a loadable module
accessed the SPI controller directly. Therefore F318 has no MMIO backend. A
future hardware provider must first establish exclusive ownership/arbitration
inside a versioned kernel image and prove an exact per-block protection-write
primitive. If it cannot restore one DPB without a chip-wide operation, the
provider must fail closed and persistent writes remain disabled.

F318 does not assume that a raw DPB byte means locked or unlocked. The hardware
provider supplies the observed unprotected value and must restore the original
opaque byte exactly.

## Validation

- Host C11 strict build and functional tests: PASS.
- GCC `-fanalyzer`: PASS.
- ARC700/uClibc object build: PASS.
- Reproducible two-build archive: PASS.
- Global block-protection primitives: absent and forbidden by the builder.
- Hardware, UART, TFTP, flash and MTD actions: none.

The next step is a read-only ownership/arbitration provider integrated into a
new kernel image. It must not load the rejected F295 module and must not expose
write operations until controller access and exact per-block protection
restoration are independently proven.
