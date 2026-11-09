# OpenMitraStar F226 Integration Hold

Date: 2026-09-02

F226 combines the two current development tracks without adding another code
change:

- Kernel: F223, EMAC RX ring 256 with NAPI 128.
- Rootfs: F225, Foundation 3.9 with contract-driven radio controls and
  structured configuration transactions.

## Artifact

- Bytes: `5210112`
- SHA-256: `c35c1d1a0d9f6ead3e17f099278077254ef2172b12785938f39674a8925ad255`
- Full-slot CRC32: `a0ff9040`
- Full-slot SHA-256: `59bc056fe085a36883f0c02f6ebf73d8bb983e783c50800aa7b707c419640185`
- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f226-device-bound`

## Reproducibility Contract

- Kernel, raw kernel, compressed kernel, config, DTB and vmlinux are
  byte-identical to F223.
- SquashFS rootfs is byte-identical to F225.
- No additional integration changes are present.
- Bootbase and slot-fit contracts: PASS.
- SHA256SUMS: PASS.
- Integration tests: 24 PASS.
- `lyoko_store` remains outside the firmware prefix and untouched.

## Promotion State

F226 is intentionally classified
`PRIVATE_DEVICE_BOUND_INTEGRATION_HOLD_DO_NOT_FLASH`.

It becomes eligible only after:

1. F223 passes three physical 32 MiB bidirectional 2.4 GHz runs with the
   descriptor-starvation gates.
2. F225 passes authenticated browser and dual-radio hardware regression.

Installed hardware remains F222.
