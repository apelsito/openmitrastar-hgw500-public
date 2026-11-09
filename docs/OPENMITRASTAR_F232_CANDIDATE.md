# OpenMitraStar F232 Integration Hold

F232 combines exactly two already isolated branches:

- F223 kernel: EMAC RX ring `128 -> 256`, with NAPI still `128`.
- F231 rootfs: Foundation 4.2 with truthful, fail-closed 5 GHz controls.

No third change is introduced.

## Artifact

- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f232-device-bound`
- Bytes: `5214208`
- SHA-256: `2687b1eee7572ff3ed9a1b6245e510ff4a8217cf9a341a920db5fc0864b2eb9b`
- Full-slot SHA-256: `ef672d0b9719290ca5f7827f8b97893ff498449aa3e85cf507585eac1283d188`
- Rootfs SHA-256: `5bb679159b01143905918d68a2336e2e8e199a3195a2c963d5c07d2d2104565c`

## Status

F232 is deliberately classified
`PRIVATE_DEVICE_BOUND_INTEGRATION_HOLD_DO_NOT_FLASH`. It is not eligible for
flash until F223 passes its three-run physical 2.4 GHz campaign and F231 passes
the hardware radio-contract, package, front-panel and dual-radio regressions.
