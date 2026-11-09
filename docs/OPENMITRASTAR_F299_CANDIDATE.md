# OpenMitraStar F299 Full candidate

Date: 2026-09-04

## Purpose

F299 turns the F293 hardware-ingress observation into one bounded recovery
experiment. It can restart EMAC RX earlier only while Linux RX is stalled and
the physical MAC continues to receive frames.

## Exact Candidate

- Runtime: `lyoko-foundation-6.5.2-f299-emac-hw-demand-early-restart-device`
- Target: physical `mtd4/linux_live`
- Bytes: `5259264`
- SHA-256: `92ddc564fc264e3e7e0e1fd1300e798af959bf6c4280f8972a0b8dba20c6221a`
- Full-slot CRC32: `0b419d91`
- Full-slot SHA-256: `9f8a96e00fb838851560809289abaf05986ec56018e9b5ba02c9c35a6bbc2b82`
- Bootbase contract: PASS
- Slot fit: PASS
- Offline focused tests: PASS
- Hardware boot: NOT RUN

## Single Functional Variable

An early restart requires all of the following:

- Linux RX idle for at least 2000 ms;
- no pending DMA interrupt;
- unchanged `cur_rx`;
- head descriptor still DMA-owned;
- hardware `FramesRxTotal` progress in four consecutive 250 ms samples;
- fewer than the original 16 fallback pokes.

The early branch fails closed when a counter read fails or the progress streak
breaks.

## Preserved Recovery

- F290 fallback at 16 pokes remains unconditional and independent of the new
  hardware counter.
- Restart cooldown remains 10000 ms.
- There is still exactly one `qtn_emac_restart_rx_dma()` action and the restart
  sequence is unchanged.
- RX ring 256, NAPI 256, TX ring 64 and RX buffer 2048 are unchanged.
- DTB and kernel configuration are byte-identical to F293.
- The rootfs changes only `etc/openmitrastar/release`.
- Quantenna modules, firmware, scripts and configuration are unchanged.

## Physical Gate

The one-command coordinator installs F299, runs three 32 MiB bidirectional
2.4 GHz tests, requires a proven sub-16-poke hardware-demand restart, checks
median throughput against 95 percent of F290, then executes a real 5 GHz WPA2
32 MiB bidirectional transfer and 120-second soak.

Any `PARTIAL` or `FAIL` result restores the exact F292 image automatically.

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_f299_flash_test_rollback.ps1 `
  -Execute -Ack OPENMITRASTAR_F299_FLASH_TEST_ROLLBACK_92DDC564
```

Only physical `mtd4/linux_live` is a write target. `mtd0`, `mtd1`, `mtd2`,
`mtd3` and `mtd5` remain protected.
