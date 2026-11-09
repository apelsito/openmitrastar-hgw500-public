# OpenMitraStar F274 Full current state

Date: 2026-09-03

## Installed image

- Runtime: `lyoko-foundation-6.2.3-f274-qtn-safe-noop-device`
- Target: physical `mtd4/linux_live`
- Candidate bytes: `5259264`
- Candidate SHA-256: `ffbc2cb44acb2514c33adebeaec212122f7cc13e6cef3ef7b81a9d306f623bfe`
- Full-slot CRC32: `b0df3f11`
- Full-slot SHA-256: `fda72a7c0e3685c044d40ef237a920b4a2d1b750614a791fc2c910bcc8709750`
- Bootbase TFTP write/readback and protected-partition checks: PASS
- Platform gate: PASS

## Quantenna control result

`om-qtnctl plan /dev/null` reports the current configuration as an exact
no-op:

```text
mutation_required=false
ssid=false
channel=false
bandwidth=false
hostapd_restart_required=false
wext_mode_write_required=false
wext_channel_write_required=false
```

`om-qtnctl apply /dev/null` now returns verified success using backend `no-op`
even though dynamic Quantenna mutation remains disabled. Physical verification
confirmed that it performs no WEXT/MuC write, does not restart hostapd-qtn,
preserves SSH and both APs, and produces zero fatal markers.

## Current boundary

The safe sequence is now proven through:

1. RF reassertion with the current value.
2. Interface-up reassertion.
3. Complete configuration no-op detection.

The next unproven step is `mode-write-same`. Source analysis shows that an
exact ifmedia match should return before the driver callback; a mismatch can
reset WME/rates, alter channel state, send multiple hostlink/MuC parameters and
update the beacon. It therefore remains reserved for a session with physical
power-cycle recovery.

Evidence:

- `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f274-device-bound\flash-one-shot-20260903T112541Z\result.json`
- `outputs/postflash/f274-device-20260903T112531Z/`
- `docs/QTN_DYNAMIC_CONTROL_ISOLATION_F273.md`

