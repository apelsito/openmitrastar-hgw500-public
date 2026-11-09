# OpenMitraStar F293 Full candidate

Date: 2026-09-04

## Purpose

F293 is a telemetry-only kernel successor to the physically installed F292.
It answers the remaining Realtek/EMAC question before another recovery-policy
experiment: did the Arasan MAC observe incoming frames while Linux RX appeared
idle?

It preserves the F290 recovery behavior inherited by F292. It does not use the
rejected F291 ten-second fault window and it does not gate, suppress or trigger
RX recovery from the new counters.

## Exact candidate

- Runtime: `lyoko-foundation-6.5.1-f293-emac-hw-rx-demand-device`
- Target if explicitly promoted: physical `mtd4/linux_live`
- Bytes: `5259264`
- SHA-256: `76f07b7d868fe878fe032bf302b2c75340498cd0186537bf75fc3ef9066ddc37`
- Full-slot CRC32: `3cc67f08`
- Full-slot SHA-256: `e93b0320d5a1032182661cdd4a26a31248edec6867328e9f8ac09d0ba662d3bb`
- Bootbase contract: PASS
- Slot fit: PASS
- Hardware boot: NOT RUN

Private artifact:

`%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f293-device-bound/openmitrastar-linux510-f293-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`

## Single functional variable

During the already-existing 250 ms stall-poke path, F293 samples:

- the Arasan MAC `FramesRxTotal` counter;
- whether that counter advanced;
- the age of the last observed hardware RX progress;
- the DMA missed-frame counter;
- the same values at the instant the unchanged F290 fallback restarts RX.

This distinguishes three cases that F290 could not separate:

1. no traffic reached the Ethernet MAC;
2. traffic reached the MAC but not the Linux descriptor ring;
3. the descriptor ring progressed and the apparent idle period was harmless.

## Preserved behavior

- RX ring: 256 descriptors.
- NAPI weight: 256.
- TX ring: 64 descriptors.
- RX buffer: 2048 bytes.
- F290 restart conditions, cooldown and restart sequence unchanged.
- F292 SquashFS, web, API, radio modules, firmware and package runtime unchanged
  except for the release identity.
- `mtd0`, `mtd1`, `mtd2`, `mtd3` and `mtd5` are not touched.

## Offline evidence

- ARC700 kernel and image build: PASS.
- Binary telemetry contract: PASS.
- Bootbase and slot layout: PASS.
- Configuration and DTB byte-identical to F292: PASS.
- Rootfs delta limited to `etc/openmitrastar/release`: PASS.
- `SHA256SUMS`: PASS.
- Focused tests: 9 PASS.
- Promotion dry-run: router SSH, UART and local TFTP prerequisites PASS.
- Hardware actions during construction: none.

## Physical gate

Promotion is intentionally not automatic. After exact authorization, use:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\promote_f293_mtd4_direct.ps1 `
  -Execute -Ack OPENMITRASTAR_F293_HW_RX_DEMAND_76F07B7D
```

Then run:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_f293_physical_campaign.ps1 `
  -Execute -Ack OPENMITRASTAR_F293_HW_RX_DEMAND_PHYSICAL
```

Acceptance requires three real 2.4 GHz 32 MiB bidirectional runs, clean counter
reads, no material throughput regression, router health, and a 120-second 5 GHz
sanity gate. A restart is useful evidence but is not manufactured artificially.

## One-command campaign

The complete guarded sequence is prepared in
`tools/run_f293_flash_test_rollback.ps1`:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_f293_flash_test_rollback.ps1 `
  -Execute -Ack OPENMITRASTAR_F293_FLASH_TEST_ROLLBACK_76F07B7D
```

It pins the exact F293 and F292 hashes, writes only `mtd4/linux_live`, runs the
three Realtek transfers and Quantenna sanity gate, and automatically restores
F292 if a post-promotion campaign fails. If F293 cannot be confirmed as written,
the coordinator does not guess and reports that manual recovery may be needed.
