# OpenMitraStar F230 Integration Hold

Date: 2026-09-02

F230 combines the F223 RX-ring-256 kernel with the complete F229 Foundation
4.1 rootfs. It adds no third implementation change.

## Artifact

- Bytes: `5210112`
- SHA-256: `e22d814d53d0435771e46a80618a20822a7b3a1fd69775d29a93ad5e6a122f60`
- Full-slot CRC32: `9fc20a0e`
- Full-slot SHA-256: `20eca188ef553b9cdfe4fde9af222433f1c5611559981e5f88b9630b823b7b0d`
- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f230-device-bound`

## Exact Composition

- Kernel, config, DTB and vmlinux: byte-identical to F223.
- SquashFS rootfs: byte-identical to F229.
- Package manager and hardware inventory are inherited unchanged.
- Bootbase, slot-fit and SHA256SUMS: PASS.
- `lyoko_store` remains outside the firmware prefix and untouched.

F230 remains `PRIVATE_DEVICE_BOUND_INTEGRATION_HOLD_DO_NOT_FLASH` until the
F223 physical campaign passes.
