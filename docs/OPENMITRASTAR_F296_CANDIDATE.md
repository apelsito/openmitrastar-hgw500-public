# OpenMitraStar F296 Full offline hold

Date: 2026-09-04

F296 combines the exact F293 telemetry kernel, the F294 diagnostics UI and the
F295 store-protection observer in one SquashFS image.

## Artifact

- Runtime: `lyoko-foundation-6.5.3-f296-store-protection-ui-device`
- Bytes: `5263360`
- SHA-256: `2b9c7adc2ec6ecfc40e7f150d468feea61c7b9468db57a68cbdfa0327b10c2c6`
- Full-slot CRC32: `07e435dc`
- Full-slot SHA-256: `82ae8521f8d2effa28199874152684c116c25d97d584dc4729fa92c6c0052ed6`
- Bootbase and slot-fit contracts: PASS.
- Candidate eligible: false.
- Flash supported: false.
- Hardware boot: NOT RUN.

## Safety state

- Observer packaged: yes.
- Observer enabled by default: no.
- Observer autoload: no.
- MTD registration: absent.
- Program and erase paths: absent.
- Persistent writes: unavailable.
- Kernel, DTB and kernel configuration: byte-identical to F294/F293.

The storage API reports whether the observer is packaged, enabled and loaded.
Only after a separately controlled module load would it display the raw JEDEC,
status, security and DPB values. The API contains no module-load or flash-write
operation.

## Validation

- F295 module contract: 6 PASS with inherited observer/write-foundation tests.
- F296 Foundation/API/UI suite: 39 PASS.
- Packaged SHA256SUMS: PASS.
- Mobile `390x844`: no horizontal overflow.
- Storage commit and rollback controls remain disabled.
- Browser console errors: zero.
- Read-only module-load gate dry-run: PASS.
- Gate verifies the module and firmware hashes, exact F296 runtime, disabled
  feature flags, UART capture, complete `lyoko_store` hash before/after,
  unchanged MTD table, unchanged fatal count and successful module removal.
- Hardware actions: none.

F296 must not be promoted before the F293 physical telemetry campaign.

Prepared future gate:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools\run_f296_store_protection_probe.ps1 `
  -Execute -Ack OPENMITRASTAR_F296_STORE_PROTECTION_READONLY_2F00A2DB
```

The command refuses to run unless the exact F296 runtime is already installed.
