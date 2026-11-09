# OpenMitraStar F288 Full current state

Date: 2026-09-03

## Installed image

- Runtime: `lyoko-foundation-6.4.1-f288-emac-rx-fault-napi-device`
- Physical target: `mtd4/linux_live`
- Candidate SHA-256: `567a4f02fd405094766c42240b1ba4587af34852d605c3fbbf05f1c885a9d3da`
- Full-slot CRC32: `ec06695b`
- Full-slot SHA-256: `8de9d162364aa20f87bcbb4166b41f7201cd538ac8fb0b9021aa9bea2c466c62`
- TFTP write/readback and protected partitions: PASS
- Platform gate after initial installation and after F289 rollback: PASS

## Realtek result

Three 32 MiB bidirectional runs passed. Median throughput was 25.442 Mbps
downstream and 14.910 Mbps upstream. Compared with F287, the downstream median
was 6.0 percent lower while upstream improved 3.6 percent.

The targeted fault behavior improved:

- sampled NO_RX_DESC state: zero in all three runs;
- NO_RX_DESC-attributed restart: zero in all three runs;
- NO_RX_DESC IRQ: 1, 0 and 0;
- allocation failures and WLAN errors/drops: zero.

One run still recorded a fault-free `stagnant` RX restart. F288 therefore
remains a stable diagnostic baseline, not the final datapath result.

## Quantenna result

The current-image 5 GHz sanity gate passed at 20.991 Mbps down and 25.107 Mbps
up, with 112/112 connected samples over 120 seconds, zero disconnects and zero
fatal markers.

## F289 rejection

F289 attempted to require an RX fault bit before allowing a full RX DMA
restart. It booted and passed the platform gate, but later lost Ethernet/SSH.
UART showed the kernel alive, RX packet count frozen, increasing idle time and
zero recovery attempts. F289 was rolled back to F288 and is rejected.

Evidence:

- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f288-device-bound/flash-one-shot-20260903T230137Z/result.json`
- `outputs/postflash/f289-device-20260903T230128Z/status.json`
- `outputs/f3-certification/f288-emac-rx-fault-20260903/f288-evaluation.json`
- `outputs/f3-certification/f288-emac-rx-fault-20260903/quantenna-sanity/result-20260903T223740Z.json`
- `outputs/f3-certification/f289-rejected-20260903/result.json`
