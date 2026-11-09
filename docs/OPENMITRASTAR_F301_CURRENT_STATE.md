# OpenMitraStar F301 Full current state

Date: 2026-09-04

## Installed Image

F301 is installed persistently in physical `mtd4/linux_live`.

- Runtime: `lyoko-foundation-6.6.1-f301-f300-capability-truth-device`
- Candidate bytes: `5267456`
- Candidate SHA-256: `4c280e84b4593008b900cec70041b801d204bdde748b09064410708253b87262`
- Full-slot CRC32: `2483522f`
- Full-slot SHA-256: `c9c98d000fa9ea1c2fd53738e97decf83ef9a21132b382a23df03121fac1577b`
- Bootbase TFTP write/readback: PASS
- Protected partitions: PASS
- Linux 5.10, SquashFS, SSH and dual-radio readiness: PASS

## Product Integration

F301 combines the physically accepted F300 datapath with the updated Lyoko
capability-truth interface.

- Kernel, configuration, DTB and `vmlinux`: byte-identical to F300.
- Radio modules, firmware and configuration: 86/86 files identical to F300.
- Authenticated dashboard: PASS.
- API v1 endpoints for status, firmware, frontend, capabilities, diagnostics
  and storage: PASS.
- Capability registry: 23 current developer-facing entries.
- Live hashes for dashboard, JavaScript, CSS and login assets: 7/7 PASS.
- F300 hardware-demand metrics are exposed in Developer diagnostics.
- A zero-millisecond hardware-progress age is treated as valid evidence.
- Store protection observer remains disabled and has no autoload path.
- Multicast harness is packaged but inactive by default.

The retargeted read-only store-protection gate is prepared at
`tools/f301_store_protection_probe.ps1`. Its local contract and dry-run pass,
but execution is correctly blocked while the six-hour F301 soak is active. It
has not loaded the observer or touched hardware.

The login dispatcher now redirects both an existing session and a successful
password submission to the authenticated `/dashboard.cgi` route.

## Physical Radio Regression

The exact installed F301 image completed:

- 2.4 GHz WPA2, 32 MiB each direction: 30.918 Mbps down / 14.282 Mbps up.
- 5 GHz WPA2/CCMP channel 36, 32 MiB each direction: 38.592 Mbps down /
  25.287 Mbps up.
- 5 GHz 120-second soak: 111/111 connected samples, zero disconnects.
- Final router health: both APs ready, F300 metrics present, zero fatal markers.

## Remaining Release Work

- Six-hour sequential dual-radio soak on F301.
- Final 24-hour soak and simultaneous two-client test.
- Controlled Spain DFS/CAC/radar exercise.
- Real multicast/IGMP and isolated VLAN traffic gates.
- Physical LED identification and independent Linux 5.10 recovery-slot proof.

## Evidence

- `outputs/campaign/f301-flash-test-20260904T120428Z/f301-promotion-reconciled-20260904T122134Z.json`
- `outputs/f3-certification/f301-integrated-regression-20260904T121108Z/campaign.json`
- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f301-device-bound/flash-one-shot-20260904T120441Z/result.json`
- `outputs/postflash/f301-device-20260904T120430Z/status.json`
