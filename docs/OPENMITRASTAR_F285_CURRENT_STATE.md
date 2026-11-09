# OpenMitraStar F285 Full current state

Date: 2026-09-03

## Installed image

- Runtime: `lyoko-foundation-6.3.9-f285-qtn-convergent-verify-device`
- Physical target: `mtd4/linux_live`
- Candidate bytes: `5259264`
- Candidate SHA-256: `ad0a668df4a05f841483157c778292664011148cbaef598d2fbde1ec0d7232e4`
- Full-slot CRC32: `670899dd`
- Full-slot SHA-256: `68348c17312b0f8f23c3e1146e0e918b3af0a60910f96d3f3cc35bace3291357`
- Bootbase TFTP write/readback: PASS
- Protected partitions and store tail: PASS
- Platform gate: PASS

## First material 5 GHz transaction

F285 changed only the 5 GHz SSID from `MOVISTAR_PLUS_55CB` to
`Lyoko-5G-Material-Test`, preserving channel 36, 80 MHz bandwidth, WPA2 PSK,
bridge topology and all MTD contents.

Two physical trials passed. The second held the target SSID for 30 seconds and
then restored the original configuration:

- target apply marker: true;
- restore marker: true;
- final state restored exactly: true;
- SSH after: true;
- fatal count: `0 -> 0`;
- watchdog armed: true;
- automatic retry: false;
- flash/MTD writes during trial: false.

The fix was bounded convergence polling. F284 had already started hostapd with
the target SSID and valid WPA2, but treated transient channel reads as a failure.
F285 waits for SSID, channel, bandwidth, bridge membership and hostapd PONG to
converge before accepting or rolling back.

## Physical AELITA association

AELITA deliberately associated to `Lyoko-5G-Material-Test` during a bounded
material trial. Sanitized evidence proves:

- 5 GHz, channel 36 and `802.11ac`;
- WPA2-Personal with CCMP;
- negotiated receive/transmit PHY of 866.7 Mbps;
- signal 93 percent and RSSI -29 dBm;
- DHCP IPv4 and router ping PASS;
- client restoration to its original profile PASS;
- temporary profile and encrypted secret blob removed;
- router restored to `MOVISTAR_PLUS_55CB`, channel 36 / 80 MHz;
- zero fatal markers and no flash or MTD writes.

The outer material gate recorded a false failure after restoration. Its own
`restore.log` says the apply was verified, and the watchdog subsequently found
an exact no-op because the original state was already restored. F286 adds a
bounded convergence wait around this final readback.

This proves association and local L3 connectivity, not the current-image 32 MiB
bidirectional throughput gate.

## Current-image 5 GHz traffic

A subsequent non-mutating AELITA run against the permanent
`MOVISTAR_PLUS_55CB` SSID completed:

- 32 MiB downstream: 36.46 Mbps;
- 32 MiB upstream: 27.59 Mbps;
- negotiated PHY: 866.7 Mbps receive/transmit;
- 120-second continuity window: 111/111 connected samples;
- disconnects: zero;
- router and 2.4 GHz AP preserved;
- fatal markers: zero;
- AELITA eventually restored to A348 with Internet connectivity.

The first result was conservatively marked FAIL because A348 was temporarily
unavailable at the exact restore instant. A read-only reconciliation confirmed
the delayed restoration without repeating traffic.

## Current-image 2.4 GHz traffic

Three physical AELITA runs completed 32 MiB in each direction with the F285
kernel and its 256-entry RX ring:

- downstream: 14.681, 14.132 and 14.727 Mbps; median 14.681 Mbps;
- upstream: 14.265, 13.921 and 14.439 Mbps; median 14.265 Mbps;
- all transfers, WPA2 association, router health and client restoration: PASS;
- WLAN errors and drops: zero;
- client identifiers were redacted from the new evidence.

Compared with the F219 median, downstream improved from 7.074 Mbps while
upstream moved from 16.218 to 14.265 Mbps. The 256-entry ring therefore improves
useful receive throughput but does not remove starvation: each run recorded one
NO_RX_DESC-attributed recovery, 20-43 NO_RX_DESC IRQs, 300-308 sampled
NO_RX_DESC states and 33-47 NAPI budget exhaustions. The next isolated datapath
candidate should raise NAPI weight from 128 to 256 while retaining the 256-entry
RX ring.

## Evidence

- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f285-device-bound/flash-one-shot-20260903T195336Z/result.json`
- `outputs/postflash/f285-device-20260903T195327Z/status.json`
- `outputs/postflash/f285-qtn-material-20260903T195846Z/result.json`
- `outputs/postflash/f285-qtn-material-client-window-20260903T200100Z/result.json`
- `outputs/postflash/f285-material-aelita-scan-20260903T200115Z/result.json`
- `outputs/f3-certification/f285-material-aelita-20260903/sanitized-association-result.json`
- `outputs/f3-certification/f285-5g-aelita-traffic-20260903/result-reconciled-20260903T204757Z.json`
- `outputs/f3-certification/f285-realtek-2g-current-evaluation-20260903.json`

## Next gate

Install and verify F286 only when an mtd4 campaign is explicitly authorized,
then repeat matched traffic to compare any subsequent Quantenna optimization.
Channel and bandwidth mutation remain separate later gates.
