# OpenMitraStar F288 Full candidate

Date: 2026-09-03

## Purpose

F288 targets the residual Realtek-side Ethernet receive stall observed once in
three F287 runs. The DMA reports RX fault state, but the existing pending mask
only acknowledges TX done, RX done and MAC events. A pure or latched RX fault
can therefore wait for the periodic stall detector and trigger a full RX DMA
restart.

F288 includes `RX_STOPPED`, `NO_RX_DESC` and `RX_MISSED` in the pending mask
used by the interrupt and fallback poll paths. These events are acknowledged
and schedule NAPI immediately. Interrupt-enable policy is unchanged to avoid
introducing an unbounded RX fault interrupt storm.

## Candidate

- Runtime: `lyoko-foundation-6.4.1-f288-emac-rx-fault-napi-device`
- Candidate bytes: `5259264`
- Candidate SHA-256: `567a4f02fd405094766c42240b1ba4587af34852d605c3fbbf05f1c885a9d3da`
- Full-slot CRC32: `ec06695b`
- Full-slot SHA-256: `8de9d162364aa20f87bcbb4166b41f7201cd538ac8fb0b9021aa9bea2c466c62`
- Bootbase contract and slot fit: PASS
- Packaged SHA256SUMS: PASS
- Hardware boot: NOT RUN

## Scope

- RX ring: unchanged at 256 descriptors.
- NAPI weight: unchanged at 256.
- RX buffers, TX path and restart thresholds: unchanged.
- DMA interrupt-enable mask: unchanged.
- Rootfs: F287 plus release identity only.
- Radio modules, firmware, web/API, packages and DTB: unchanged.

ARC disassembly contains the combined pending mask `0x1f1` in both the IRQ and
poll paths, plus the existing NAPI-256 and RX-ring-256 contracts.

## Acceptance

Run the same three 32 MiB bidirectional Realtek tests and the F287-equivalent
5 GHz sanity gate. F288 is accepted only with no throughput regression, zero
allocation/frame errors and zero RX fault restarts in every run.
