# OpenMitraStar F170 current state

Snapshot date: `2026-09-01`

## Installed firmware

- Target: `MitraStar HGW-500BNA-QCv2 A2`
- Kernel: `5.10.260-openmitrastar-radiohw`
- Active physical slot: `mtd4/linux_live`
- Candidate: `4,964,352` bytes
- SHA-256: `432e4341e92fc5162c3550d5c7df05d378b31d250086ce7a72bedb64b0e4559d`
- Full-slot CRC32: `d77c9c82`
- Full-slot SHA-256: `fc7723187b913a89100a21db1b4d4c03d3d489d563418067e66d9476ab8b69bc`
- Rollback: preserved `mtd3/linux_safety`, manual UART `ATGO`
- Protected partitions: PASS unchanged

Flash evidence:
`work/mission-state/q3-persistent-composite-f170-lyoko-foundation-runtime-fix/build/flash-one-shot-20260901T111746Z/result.json`

## Foundation state

- SquashFS-XZ root is read-only and `rootfs_live` is the exact `0x620000` window.
- `/run` and `/tmp` are tmpfs; `/persist` starts read-only.
- Stable device-specific Dropbear Ed25519 host key is bundled as fallback.
- Normal OpenSSH connection succeeds with the existing pinned host fingerprint.
- `/dashboard.html` is installed with `Normal`, `Advanced` and `Developer` views.
- `/api/v1/status`, `network`, `radios/2g`, `radios/5g`, `clients`,
  `hardware`, `diagnostics`, `privacy` and `firmware` return valid JSON on the
  physical router when invoked through the authenticated backend.
- Unauthenticated HTTP access to `/api/v1/status` returns `403`.
- Radio responses expose state, SSID, channel, bandwidth, power and region but
  never PSKs or client MAC addresses.
- Material configuration changes remain feature-gated. Safe no-op validation
  exists; persistent apply is not yet enabled.

Post-flash evidence:
`outputs/postflash/f170-lyoko-foundation-20260901-133549/status.json`

## Physical Wi-Fi baseline inherited from F167

- 2.4 GHz: 32 MiB down/up PASS, approximately `6.88 / 15.13 Mbps`, WPA2,
  MCS15/130 Mbps and no station TX failures.
- During that test, EMAC telemetry recorded `NO_RX_DESC` pressure and two RX
  restarts attributed to that condition. This is the current bottleneck lead.
- 5 GHz: 32 MiB down/up PASS, approximately `24.56 / 26.75 Mbps`, WPA2 and no
  client disconnects. One enriched SSH monitor stream stalled while traffic
  completed, consistent with the shared EMAC issue rather than a radio loss.
- F170 changes no kernel or radio module bytes relative to F167.

## Transport

The canonical F170 flow attempted TFTP first. A later direct RAM-only Bootbase
probe reached gigabit link and issued an RRQ to the temporary APELSITO server
at `192.168.1.63`, but the transfer timed out. No erase or flash write began.
UART/YMODEM remains the proven transport.

## Next work

1. Promote and physically validate the prepared F171 health/transaction fix.
2. Finish and enable native transactional radio apply/rollback.
3. Integrate one driver experiment at a time from the separate Realtek and
   Quantenna candidates.
4. Repeat the physical client benchmark after every datapath change.
5. Complete DFS, multicast/VLAN and long dual-radio soak certification.
