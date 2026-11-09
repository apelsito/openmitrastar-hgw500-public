# OpenMitraStar F141 current state

Date: 2026-08-30 22:18 CEST

## Latest physical-client result

AELITA saw and associated with `OpenMitraStar-5G-DIAG`, held the association
for 24/24 samples over 120 seconds, configured `192.168.77.2/24`, and restored
its normal WiFi successfully. One of four pings to the AP at `192.168.77.1`
returned in 2 ms.

The HGW management path then became unreachable. UART and SysRq did not
respond, so this is not yet a stable traffic PASS and a physical power-cycle is
required. The next run uses `q3_client_stream_openssh.py` to avoid the obsolete
RAM-key authentication failure that prevented synchronized router telemetry.

## Installed firmware

- Target: MitraStar HGW-500BNA-QCv2 A2
- Kernel: `5.10.260-openmitrastar-radiohw`
- Active slot: `mtd4/linux_live`
- Rollback slot: `mtd3/linux_safety`, preserved
- Candidate SHA-256: `57f76bb6393b09cbd8ee343c85f8b825999c85b7570e22a12a175783f6b6f8b3`
- Full-slot CRC32: `d16b5f46`
- Full-slot SHA-256: `e7f840255615bed94dc18a3fe1d80a272fc27b38704199ec404fdffa6d35d9cb`

## What F141 fixes

1. `hostapd-qtn` now opens its raw probe-request socket on `wifi0` when the AP
   is intentionally outside a bridge. This removes the previous empty-interface
   `SIOCGIFINDEX` failure.
2. `wlan.ko` no longer overwrites its initial TX-power limit with the zero-power
   sentinel.
3. `om-radio5-start` applies and verifies the OEM table maximum of 21 dBm.

## Live status

- SSH: reachable at `192.168.1.90:22`
- 2.4 GHz: hostapd `state=ENABLED`
- 5 GHz: service `ready`, hostapd control `PONG`
- SSID: `OpenMitraStar-5G-DIAG`
- RF: `1`
- Carrier: `1`
- TX power: `21 dBm`
- Fatal kernel markers: none
- Gate: `PASS_F141_5G_TXPOWER_READY_READONLY`

## Remaining proof

The controller PC has Ethernet only and AELITA is unavailable. Therefore SSID
visibility, association and bidirectional client traffic remain unproven. Run
the existing Q3 client gate when AELITA is available; do not promote 5 GHz to
product-ready until those three checks pass.

`watch_f141_aelita_5g_certification.ps1` is armed for six hours. When AELITA
SSH becomes reachable it runs the 120-second isolated-L3 certification and
restores AELITA's normal WiFi through the independent watchdog.
