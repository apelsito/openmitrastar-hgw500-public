# OpenMitraStar F312 Current State

## Installed image

- Version: `lyoko-foundation-6.7.7-f312-http11-transaction-compat-device`
- Target: physical `mtd4/linux_live`
- Candidate bytes: `5271552`
- Candidate SHA-256: `14677b30886f91f67a664f02623f8f1cfa29220e33bab867b8eed5ab3c8728f7`
- Full-slot CRC32: `e5dcf574`
- Full-slot SHA-256: `039e18bb7f4addd373513fcd6307ab22b2d88b39f301455271f0e41b19a0db82`
- Kernel, modules, firmware and radio profile: byte-identical to F311.

## Purpose

F312 fixes the browser-to-CGI transaction protocol exposed by F311:

- staging uses the HTTP/1.1-compatible `POST /api/v1/radios/{band}/stage` route;
- apply, commit and rollback retain their headers but also accept the confirmation
  token and transaction id in the form body;
- 5 GHz remains bounded to SSID-only material writes;
- channel and bandwidth remain read-only plans;
- DFS is reported as hardware present in Quantenna QT4 with its Linux 5.10
  provider pending and fail-closed.

## Physical evidence

- Bootbase transfer, `mtd4` write and complete readback: PASS.
- Protected `mtd0`, `mtd1`, `mtd2`, `mtd3` and `mtd5`: unchanged.
- Linux 5.10 boot, SSH, SquashFS, bridge and both radio ready states: PASS.
- Authenticated API reports F312 and UI 6.7.7: PASS.
- 5 GHz web transaction through POST-body compatibility:
  stage PASS, material SSID apply PASS, rollback PASS, original SSID restored.
- Fatal kernel/QMAC/MuC markers after the transaction: zero.

The first rollback request reported a transient verification failure, but the
watchdog completed a verified restore. A second immediate transaction completed
stage, apply and explicit rollback successfully.

## Traffic gates

The first F312 5 GHz attempt proved association but transferred zero bytes
because the controller speed server was not listening. After starting the
pinned 32 MiB endpoint, the unchanged firmware passed:

- 5 GHz: WPA2/CCMP, channel 36, 866.7 Mbps PHY, 93 percent signal.
- 5 GHz downstream: 28.650 Mbps over 32 MiB.
- 5 GHz upstream: 24.639 Mbps over 32 MiB.
- 5 GHz soak: 120 seconds, 111/111 connected samples, zero disconnects.
- 2.4 GHz downstream: 29.624 Mbps over 32 MiB.
- 2.4 GHz upstream: 13.615 Mbps over 32 MiB.
- 2.4 GHz: zero new WLAN errors, drops, descriptor starvation or RX restarts.
- Router health and client restoration: PASS; fatal markers: zero.

Evidence:

- `outputs/f3-certification/f312-5g-aelita-traffic-20260904/result-20260904T223932Z.json`
- `outputs/f3-certification/f312-5g-aelita-traffic-r2-20260904/result-20260904T225147Z.json`
- `outputs/f3-certification/f312-realtek-20260904/summary.json`
- `outputs/postflash/f312-device-20260904T222501Z/`
- `%USERPROFILE%/.openmitrastar/devices/hgw500bna-qcv2-a2-primary/firmware/f312-device-bound/flash-one-shot-20260904T222511Z/result.json`

## Next step

Keep F312 as the installed product baseline. The next radio-control candidates
should certify one material setting at a time: non-DFS channel, bandwidth,
SSID visibility and then the remaining Quantenna controls. DFS requires the
separate Linux 5.10 radar-provider port and its physical regulatory campaign.
