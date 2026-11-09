# OpenMitraStar F287 Full current state

Date: 2026-09-03

## Installed image

- Runtime: `lyoko-foundation-6.4.0-f287-emac-napi256-device`
- Physical target: `mtd4/linux_live`
- Candidate bytes: `5259264`
- Candidate SHA-256: `c808359b3ff1a68dd360e1358ae2c258d3a206cb1dd2987c7bbbc401fe149154`
- Full-slot CRC32: `8c931453`
- Full-slot SHA-256: `a3c9fa05b9c23de64466305cd0acc1b5ca3baa005d7667e87b4e67e9e9d6210b`
- Bootbase TFTP write/readback: PASS
- Protected partitions and store tail: PASS
- Platform gate: PASS

## Realtek NAPI-256 result

Three physical 32 MiB bidirectional runs completed successfully:

- downstream: 27.062, 29.739 and 13.789 Mbps; median 27.062 Mbps;
- upstream: 15.019, 14.262 and 14.394 Mbps; median 14.394 Mbps;
- WLAN allocation failures, errors and drops: zero;
- first two runs: zero NO_RX_DESC, zero NAPI exhaustion and zero RX restart;
- third run: 56 NO_RX_DESC IRQs, 307 sampled states, one NAPI exhaustion
  and one NO_RX_DESC-attributed restart.

Compared with F285, median downstream improved from 14.681 to 27.062 Mbps
without median upload regression. F287 is retained as the improved diagnostic
baseline, but it is not the final datapath because the residual failure remains
reproducible.

## Quantenna regression

The F287 5 GHz sanity gate passed:

- 32 MiB downstream: 30.315 Mbps;
- 32 MiB upstream: 26.566 Mbps;
- 120 seconds, 111/111 connected samples and zero disconnects;
- channel 36, WPA2/CCMP and 866.7 Mbps negotiated PHY;
- router and 2.4 GHz AP preserved; zero fatal markers.

## Next candidate

F288 keeps NAPI and the RX ring at 256, but includes `RX_STOPPED`,
`NO_RX_DESC` and `RX_MISSED` in the DMA pending mask. Those events are
acknowledged and schedule NAPI immediately instead of waiting for the periodic
stall/restart fallback.

Evidence:

- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f287-device-bound/flash-one-shot-20260903T213311Z/result.json`
- `outputs/postflash/f287-device-20260903T213301Z/status.json`
- `outputs/f3-certification/f287-emac-napi256-20260903/f287-evaluation.json`
- `outputs/f3-certification/f287-emac-napi256-20260903/quantenna-sanity/result-20260903T215601Z.json`
