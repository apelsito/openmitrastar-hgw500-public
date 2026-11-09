# OpenMitraStar F300 Full candidate

Date: 2026-09-04

## Purpose

F300 follows the physically proven F299 early-recovery path and changes one
threshold: two consecutive hardware MAC progress samples are sufficient instead
of four.

F299 proved that this branch can recover a real `NO_RX_DESC` stall safely, but
it fired at poke 13 and only shortened the observed outage by 760 ms. F300 is
intended to react near poke 11 for the same sequence while retaining every
fallback and safety condition.

## Exact Candidate

- Runtime: `lyoko-foundation-6.5.3-f300-emac-hw-demand-two-sample-device`
- Target: physical `mtd4/linux_live`
- Bytes: `5259264`
- SHA-256: `734bba8ad1b706c0c17ad5e73341cbb7c7a5c4d78cf05e069d955705d789edbb`
- Candidate CRC32: `0e7cd284`
- Full-slot CRC32: `841f11c8`
- Full-slot SHA-256: `fb7867874640a428124a18be38b8521e52e5d27322393f88ab44bbd6d17baf9b`
- Bootbase and slot contracts: PASS
- Reproducible build: PASS
- Hardware boot: NOT RUN

## Single Functional Variable

`QTN_TOPAZ_EMAC_RX_DEMAND_RESTART_SAMPLES` changes from 4 to 2.

The early branch still requires Linux RX idle, no pending DMA IRQ, unchanged
`cur_rx`, a DMA-owned head descriptor and consecutive `FramesRxTotal` progress.
Counter failure or a broken streak disables the early branch.

## Preserved Behavior

- F290 fallback: 16 pokes, unchanged and unconditional.
- Restart cooldown: 10000 ms.
- Restart sequence: unchanged.
- RX ring 256, NAPI 256, TX ring 64 and RX buffer 2048.
- Kernel configuration and DTB byte-identical to F299.
- Rootfs change limited to release identity.
- Quantenna stack byte-identical to F299.

## Physical Acceptance

F300 must complete three 32 MiB bidirectional 2.4 GHz runs, demonstrate a valid
hardware-demand restart before poke 13, retain at least 95 percent of F290's
median throughput, remain fatal-free, then pass a real 5 GHz WPA2 32 MiB
bidirectional transfer and 120-second soak.

Any non-PASS result restores exact F292 automatically.
