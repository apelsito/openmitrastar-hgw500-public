# OpenMitraStar F236 Integration Hold

> **SUPERSEDED:** replaced by F238, which combines F223 with hardened F237.

F236 combines the F223 RX-ring-256 kernel with the complete F235 dual-radio
native control rootfs. The kernel is byte-identical to F223 and the rootfs is
byte-identical to F235.

## Artifact

- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f236-device-bound`
- Bytes: `5214208`
- SHA-256: `20030b50a5f5755b226ebde032731d85e528cf00ffe5c8b7b6d5f463457683ab`
- Full-slot SHA-256: `a1e298543f4099360948ab0bf6c7991c3b6b7ab65577ae2c967332e25081126f`
- Rootfs SHA-256: `8c5d878132e48322873f4f530b0f30d2e6e3fec8cf2553ed6fbb39573ee78333`

F236 remains `PRIVATE_DEVICE_BOUND_INTEGRATION_HOLD_DO_NOT_FLASH` until F223
and F235 pass their isolated physical campaigns.
