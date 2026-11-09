# OpenMitraStar F269 Full current state

Date: 2026-09-03

## Installed image

- Runtime: `lyoko-foundation-6.1.2-f269-qtn-step-lock-fix-device`
- Target: physical `mtd4/linux_live`
- Candidate bytes: `5255168`
- Candidate SHA-256: `11ef1262931e0fb4ea1afabfb36ea5dc185972c7b745d0160067f8baf2bb8b25`
- Full-slot CRC32: `0760c563`
- Full-slot SHA-256: `1e699e9cf2bab264a61bb532f6df33fa92981948fbb1f5b06cce71b77425d4ae`
- Bootbase TFTP write/readback and protected-partition checks: PASS
- Platform, SSH, SquashFS, web/API and both radio boot states: PASS

Evidence:

- `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f269-device-bound\flash-one-shot-20260903T101804Z\result.json`
- `outputs/postflash/f269-device-20260903T101754Z/`

## Quantenna isolation progress

F269 contains `/usr/sbin/om-qtn-step`, an ACK-gated CLI that executes exactly
one same-value operation and emits `OMQTNSTEP begin/pass/fail` markers. It does
not run at boot and is not exposed through the web/API.

Physical probes completed without changing the configured 5 GHz profile:

- `rf-write-same`: PASS
- `interface-up-same`: PASS when using the verified BusyBox path
- SSH after each step: PASS
- 2.4 GHz and 5 GHz AP state after each step: PASS
- fatal kernel/MuC/QMAC markers: zero
- stale-lock recovery: proven; the lock is removed after success and failure

The remaining steps (`mode`, `ssid`, `channel`, TX power, 802.11h/TPC,
hostapd restart and post-rearm) can remove management and must not be executed
without physical recovery available.

## Known defect and successor

F269 defaults `ifconfig` to `/sbin/ifconfig`, while the target exposes the
BusyBox applet at `/bin/ifconfig`. The installed probe remains usable with
`OM_IFCONFIG=/bin/ifconfig`.

F270 fixes that default path and is built offline. It is not installed.

