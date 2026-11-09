# OpenMitraStar F234 Integration Hold

F234 combines exactly:

- F223 kernel with EMAC RX ring 256 and NAPI 128.
- F233 rootfs with the native Quantenna WEXT plus hostapd transaction backend.

No third variable is introduced.

## Artifact

- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f234-device-bound`
- Bytes: `5214208`
- SHA-256: `726de5d0614425f51272949f02ae84cea8e29601632fec066fe89ec860546b00`
- Full-slot SHA-256: `71be22fc5ac387507063c8ce1a7179dd915d0d89338fa4c0dac7199e91760942`
- Rootfs SHA-256: `e6628d5acde7507e534f7f98cddfa91777fbb41f7c77c60e639b4f54ab9f7831`

## Status

F234 remains `PRIVATE_DEVICE_BOUND_INTEGRATION_HOLD_DO_NOT_FLASH`. F223 and
F233 must pass their isolated physical campaigns before this combined image is
eligible for promotion.
