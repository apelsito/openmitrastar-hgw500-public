# OpenMitraStar F235 Experimental Candidate

> **SUPERSEDED / DO NOT FLASH:** replaced by F237 after adversarial rollback
> review found unsafe TTL cleanup and insufficient Quantenna process recovery.

F235 completes Lyoko's first native dual-radio configuration plane without
depending on the absent OEM `qweconfig` or the incompatible OEM `call_qcsapi`.

## Backends

- Realtek 2.4 GHz: `om-rtlctl`, using atomic hostapd configuration replacement
  and `hostapd_cli reload` over the working nl80211 stack.
- Quantenna 5 GHz: `om-qtnctl`, using the proven WEXT mode/SSID/channel sequence
  plus a controlled hostapd-qtn restart and RF rearm.
- Both participate in the same `validate -> stage -> apply -> verify -> rollback`
  transaction contract.

Only previously bounded settings are exposed: SSID, channels 1-13 and 20/40
MHz on 2.4 GHz; SSID, channels 36/40/44/48 and 20/40/80 MHz on 5 GHz. DFS,
regulatory domain, TX power and PSK mutation remain blocked.

## Artifact

- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f235-device-bound`
- Bytes: `5214208`
- SHA-256: `e8984886b169b49d8459b66cafd1c2445a63498a28c95f62211ddd7f841f5b5e`
- Full-slot SHA-256: `e8c2ce62a242d70c1920a235d9166765d33713fc12eec1897d9d6949021ad03e`
- Rootfs SHA-256: `8c5d878132e48322873f4f530b0f30d2e6e3fec8cf2553ed6fbb39573ee78333`

## Status

Offline backend/API/browser validation passes. F235 is classified
`PRIVATE_DEVICE_BOUND_HARDWARE_TEST_CANDIDATE`: eligible only for an explicitly
authorized, guarded write to `mtd4/linux_live`. Hardware remains `NOT_RUN`.

Dry-run of the complete physical cycle:

```powershell
pwsh -File .\tools\run_f235_flash_test_cycle.ps1
```

The execution form requires the exact acknowledgement embedded in the script.
