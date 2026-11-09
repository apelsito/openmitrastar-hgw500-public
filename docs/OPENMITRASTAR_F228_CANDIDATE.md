# OpenMitraStar F228 Integration Hold

Date: 2026-09-02

F228 combines the F223 RX-ring-256 kernel with the complete F227 Foundation
4.0 rootfs. It contains no additional integration change.

## Artifact

- Bytes: `5210112`
- SHA-256: `98f6606f839490ed6f4e40b6d14751e35410471b2d9fb91ce53a85b0bd066def`
- Full-slot CRC32: `7bee94fa`
- Full-slot SHA-256: `9f39a7fb4986ac29f0c1859d3b14bb414b2072dffad55fefc22e1055013be40e`
- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f228-device-bound`

## Exact Composition

- Kernel, config, DTB and vmlinux: byte-identical to F223.
- SquashFS rootfs: byte-identical to F227.
- Bootbase and slot-fit contracts: PASS.
- SHA256SUMS: PASS.
- Integrated offline tests: PASS.
- `lyoko_store` remains outside the firmware prefix and untouched.

## Hold

F228 is classified `PRIVATE_DEVICE_BOUND_INTEGRATION_HOLD_DO_NOT_FLASH` and is
not eligible for promotion until F223 passes its three-run physical 2.4 GHz
campaign. After that, F228 requires boot, authenticated web/API, package,
dual-radio and regression gates.
