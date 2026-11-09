# OpenMitraStar F282 Full current state

Date: 2026-09-03

## Installed image

- Runtime: `lyoko-foundation-6.3.6-f282-qtn-hostapd-restart-fix-device`
- Target: physical `mtd4/linux_live`
- Candidate bytes: `5259264`
- Candidate SHA-256: `b3cebdd208199edc7bbeabef53e2c033a3dd926a590101d8e25e75f2a26b0733`
- Full-slot CRC32: `a347aceb`
- Full-slot SHA-256: `5f53dd9629563d6e1be99631cf38bbaa0720ae565bce8e856caa7aae84aa2904`
- Bootbase TFTP write/readback: PASS
- Protected partitions: PASS
- Linux 5.10, SSH, SquashFS, web/API, packages and dual-radio platform gate: PASS

The original promotion wrapper ended with a host-side false negative because
it still required a removed `QTN_STEP_PATH_RC` marker. The captured integrated
probe itself passed every emitted check; the wrapper was corrected afterwards.

## Quantenna physical sequence

F277 physically established:

- `mode-write-same`: PASS.
- `ssid-write-same`: PASS after a measured transient channel/mode transition.
- `channel-write-same`: PASS.
- `txpower-init-same`: PASS.
- `doth-write-same`: PASS.
- `tpc-write-same`: PASS.
- `tpc-interval-same`: PASS.
- `post-rearm-same`: PASS after convergence.
- fixed WEXT `txpower 21`: rejected by the driver without changing state.

F281 removed that invalid fixed-power command and added validated PID
termination. Its first hostapd restart proved that the old process stopped, but
also exposed that the boot script intentionally deletes the ephemeral
`hostapd.conf`; the radio was recovered by a clean reboot.

F282 regenerates a root-only hostapd configuration from the runtime secret,
executes the already-proven pre/post rearm sequence and waits for convergence.
The physical `hostapd-restart-same` gate passed:

- SSH after: true;
- before/after mode: `11ac80Edge+`;
- before/after radios: identical;
- fatal count: `0 -> 0`;
- convergence: first sample, 1.609 seconds;
- MTD writes: false.

## Current live state

- Boot state: `ready`.
- 2.4 GHz: `ap-ready`, channel 1, WPA2.
- 5 GHz: `ap-ready`, channel 36, 80 MHz, 21 dBm, WPA2.
- hostapd-qtn: `PONG`.
- Fatal kernel/radio markers: zero.

A passive AELITA scan after the restart returned only its currently associated
A348 network. This is the previously documented Windows scan-throttling
limitation, not evidence that Lyoko stopped transmitting: over 20 seconds
`wlan0` advanced 73 TX packets and `wifi0` advanced 6, with both AP states
ready and zero fatal markers.

## Evidence

- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f282-device-bound/flash-one-shot-20260903T190439Z/result.json`
- `outputs/postflash/f282-device-20260903T190429Z/status.json`
- `outputs/postflash/f282-qtn-step-hostapd-restart-same-20260903T191052Z/result.json`
- `outputs/postflash/f282-aelita-visibility-20260903T191200Z/result.json`

## Next boundary

F282 proves the complete same-value restart/rearm path. The next Quantenna
milestone is one reversible material change with automatic rollback and a real
client association/traffic gate. Dynamic apply remains disabled until that
campaign is separately prepared.
