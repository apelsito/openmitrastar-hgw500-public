# OpenMitraStar F290 Full current state

Date: 2026-09-04

## Installed image

- Runtime: `lyoko-foundation-6.4.3-f290-emac-restart-context-device`
- Physical target: `mtd4/linux_live`
- Candidate SHA-256: `b3512d5098f1e47e68995836e8e7ed1cef7d8c0a733cbe5e651ae75591770bfc`
- Full-slot CRC32: `a91859e2`
- Full-slot SHA-256: `bf2a923fffad5825357c261568fd1d5bea0eba6e5503880cdcb3c0fc9969cf03`
- TFTP write/readback and protected partitions: PASS
- Platform gate after installation and after F291 rollback: PASS

## Realtek result

Three physical 32 MiB bidirectional runs passed:

- downstream: 14.769, 29.258 and 29.499 Mbps; median 29.258 Mbps;
- upstream: 14.410, 16.561 and 13.693 Mbps; median 14.410 Mbps;
- sampled NO_RX_DESC: zero in all runs;
- NO_RX_DESC-attributed restart: zero in all runs;
- allocation failures and WLAN errors/drops: zero.

One run used the generic stagnant recovery. F290 proved that this recovery was
not arbitrary: a real `NO_RX_DESC` event (`0x20`) occurred 6.15 seconds before
the restart, while the descriptor at the software head had already returned to
DMA ownership. The hardware fault bit had cleared before the recovery decision.

## Quantenna result

The 5 GHz gate passed at 33.133 Mbps down and 27.880 Mbps up, with 111/111
connected samples over 120 seconds, zero disconnects and zero fatal markers.

## F291 rejection

F291 retained RX fault history for ten seconds and allowed restart only while
that history was recent. It completed two Realtek runs, then lost Ethernet/SSH
before run three while Linux remained alive over UART and no restart occurred.
F291 was rolled back to F290 with complete readback and protected partitions
unchanged.

Decision: retain F290. The next driver experiment must preserve the F288/F290
fallback and add a stronger traffic-demand discriminator before tightening it.

Evidence:

- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f290-device-bound/flash-one-shot-20260904T000933Z/result.json`
- `outputs/postflash/f290-device-20260904T000924Z/status.json`
- `outputs/f3-certification/f290-emac-restart-context-20260903/f290-evaluation.json`
- `outputs/f3-certification/f290-emac-restart-context-20260903/quantenna-sanity/result-20260903T234303Z.json`
- `outputs/f3-certification/f291-rejected-20260904/result.json`
