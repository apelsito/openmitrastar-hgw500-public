# OpenMitraStar F174 signed package base

Date: `2026-09-01`

F174 demonstrates the first Lyoko package integrated into a reproducible
SquashFS image. It is an offline branch from F173 and does not include the
experimental F172 NAPI change.

## Package chain

- Standard deterministic `.ipk` container.
- ABI: `arc700_uclibc_lyoko_v1`.
- Kernel ABI: `5.10.260-openmitrastar-radiohw`.
- Platform: `hgw-500bna-qcv2`.
- Repository index signed with the local Lyoko Ed25519 feed key.
- Signature and package SHA-256 verified before rootfs integration.
- Private signing key remains outside the workspace and firmware.
- Immutable public feed snapshot: `versions/lyoko-feed-1.0-f174/`.

Installed package:

```text
lyoko-sysinfo 1.0.0-1
/usr/bin/lyoko-sysinfo
```

Runtime package installation remains disabled. F174 proves build-time package
integration only, preserving the immutable SquashFS model and avoiding use of
`mtd5` as an overlay.

Build:

```powershell
.\tools\build_f174_lyoko_package_base.ps1
```

Hardware validation remains `NOT_RUN`.

## Built artifact

- Candidate:
  `work/mission-state/q3-persistent-composite-f174-lyoko-package-base-from-f173/build/openmitrastar-linux510-q3-persistent-f174-lyoko-package-base-from-f173-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `4,964,352` bytes
- SHA-256: `85a1094d83f48f629aafc1e36b5426324cfc0e4869749198cd8e7f5e2929db08`
- Candidate CRC32: `f490988f`
- Full-slot CRC32: `b283701f`
- Full-slot SHA-256:
  `8f0ecfffbc434b54f82d7798531ac3b8b4ee1273e283a46590c47c86b7a0d17f`
- Bootbase and slot-fit: PASS
- Offline suite: `14 passed`
- Integrated package: `lyoko-sysinfo 1.0.0-1`
- Package SHA-256:
  `01bc62552b105f581a4799c498078559608943bc6ae71f76ea793429c5921512`
