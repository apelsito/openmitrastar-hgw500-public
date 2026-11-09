# OpenMitraStar F314 Current State

Date: `2026-09-05`

F314 is the current persistent firmware in physical `mtd4/linux_live` on the
HGW-500BNA-QCv2 A2.

## Installed Artifact

- Version: `lyoko-foundation-6.8.2-f314-qtn-nondfs-guard-device`
- Candidate bytes: `5,292,032`
- Candidate SHA-256:
  `a0c7350a50e5e4b532a0202982e6cd3c2d3da4e2e91079cd105473b248523f11`
- Full-slot CRC32: `d6b13baa`
- Full-slot SHA-256:
  `bc06db537f4eb20ae2b2c64c47262f44c678b1f46a035d2229a768aa36732989`
- Kernel SHA-256:
  `fefc38802811f6639b847cc8e4166b4b6ddd0b9c0361bfde3a31262b5d716649`

Bootbase later read the complete live slot and observed CRC32 `d6b13baa` before
performing any erase. A direct verified boot and a subsequent normal reboot
both reached `boot_state=ready`, SSH, 2.4 GHz `ENABLED`, 5 GHz `ready` on
channel 36 and zero fatal markers. Protected `mtd0`, `mtd1`, `mtd2`, `mtd3`
and `mtd5` remained unchanged during the installation campaign.

## Quantenna Control Matrix

The physical matrix passed all 14 controls currently supported while the
Linux 5.10 radar provider is unavailable:

`ssid`, `ssid_broadcast`, `client_isolation`, `wmm`, `short_gi`,
`beacon_interval`, `dtim_period`, `retry_count`, `ldpc`, `forty_only`,
`ba_control`, `ba_max`, `ampdu_density`, and `multicast_rate`.

Every control passed:

1. stage;
2. apply;
3. exact control readback;
4. complete settings/channel/bandwidth snapshot comparison;
5. SSH and dual-radio health while applied;
6. rollback;
7. exact restored snapshot;
8. unchanged fatal count.

Channel, bandwidth and TPC interval rejected staging as required. TPC is tied
to DOTH in this qdrv ABI and its ioctls disappear when DOTH is disabled, so it
remains blocked until the radar provider is ready.

Evidence:

- `outputs/flash-watch/f314-detached-watchdog-20260905T100618Z/qtn-control-matrix/result-20260905T112006Z.json`
- Result SHA-256:
  `ca66b1f5b4c98130a41b1fbbdc31ba89b82f34d3de728a854c5672a1825513b1`

## DFS Policy

DFS remains fail-closed. F314 fixes channel operation to the non-DFS set while
the QT4 radar provider is absent. It disables SCS channel selection, fixes the
scan path, excludes DFS scanning and clears the alternate radar channel. If a
DFS or invalid final channel is nevertheless observed, F314 stops only 5 GHz
and verifies RF off, `wifi0` down, hostapd stopped, `wifi0` detached from
`br0`, and Ethernet plus 2.4 GHz management preserved.

## Physical Traffic

### Quantenna 5 GHz

- WPA2/CCMP association: PASS.
- Channel: 36; PHY: 866.7 Mbps RX/TX; RSSI: -31 dBm.
- 32 MiB downstream: 34.026 Mbps.
- 32 MiB upstream: 26.949 Mbps.
- 120-second soak: 111/111 connected samples, zero disconnects.
- Fatal count: `0 -> 0`.
- Evidence:
  `outputs/f3-certification/f314-5g-aelita-traffic-20260905/result-20260905T112942Z.json`

### Realtek 2.4 GHz

- WPA2 association and 32 MiB bidirectional traffic: PASS.
- Downstream: approximately 18.998 Mbps.
- Upstream: 13.104 Mbps.
- No new WLAN errors or drops; management SSH remained available.
- One hardware-demand RX recovery was observed and completed.
- Evidence: `outputs/f3-certification/f314-realtek-2g-20260905/summary.json`

## Current Boundary

The persistent Linux 5.10 dual-radio product and every currently safe 5 GHz
transactional control are physically proven. The remaining Quantenna control
work is the radar-provider wave: physical QT4 acquisition/classification,
CAC, evacuation and 1,800-second NOP, followed by enabling DFS channels,
channel changes, bandwidth changes and TPC under the same transactional gate.

