# OpenMitraStar F272 Full current state

Date: 2026-09-03

## Installed image

- Runtime: `lyoko-foundation-6.2.1-f272-qtn-json-fix-device`
- Target: physical `mtd4/linux_live`
- Candidate bytes: `5259264`
- Candidate SHA-256: `875f81484a08f1d4acf6b36f1adcb4dc5f912ee608107dcd6b438f640ce12832`
- Full-slot CRC32: `9c2b4a35`
- Full-slot SHA-256: `dfd3b8ae779bfcd7188b7ce23f6f13f14e756a3125f9067e1aa09a0050fa7a93`
- Bootbase TFTP write/readback: PASS
- Protected partitions: PASS / unchanged
- Platform gate: PASS

## Radio state

- Realtek 2.4 GHz: `ap-ready`, channel 1, 20 MHz.
- Quantenna 5 GHz: `ap-ready`, channel 36, 80 MHz, 21 dBm, region ES.
- Quantenna dynamic mutation: disabled.
- Fatal kernel, MuC, QMAC and alignment markers: zero after boot.

## Quantenna live readback

The Developer console now reads the following values from the live WEXT ABI:

- SSID broadcast: enabled (`get_hide_ssid=0`).
- client isolation: disabled (`get_ap_bridge=1`).
- WMM: enabled.
- Short GI: enabled.
- DTIM: 3.
- retry count: 0.
- LDPC: enabled.
- strict 40 MHz mode: disabled.
- BA control: 65535.
- BA maximum: 64.
- AMPDU density: 5.
- TPC interval: 30.
- multicast rate: 1000.

The F271 hardware gate detected invalid boolean serialization
(`truefalse`/`falsetrue`). F272 fixes it with explicit inverse-boolean
serialization. The complete `lyoko.radio.contract/v1` response parses as JSON
on the host and reports `true`/`false` correctly.

## Next physical discriminator

The F270/F272 ACK-gated step runner has proved these operations safe:

1. `rf-write-same`
2. `interface-up-same`

The next operation is `mode-write-same`. It remains pending until a physical
power-cycle can be performed if the legacy qdrv/MuC hostlink stalls.

Evidence:

- `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f272-device-bound\flash-one-shot-20260903T110138Z\result.json`
- `outputs/postflash/f272-device-20260903T110128Z/`
- `outputs/handoff-live/f270-qtn-settings-readback-20260903-124417/readback.log`

