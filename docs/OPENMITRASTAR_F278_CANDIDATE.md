# OpenMitraStar F278 Full offline successor

Date: 2026-09-03

## Artifact

- Runtime: `lyoko-foundation-6.3.3-f278-multicast-cert-harness-device`
- Classification: `PRIVATE_DEVICE_BOUND_OFFLINE_SUCCESSOR_HOLD`
- Candidate bytes: `5259264`
- Candidate SHA-256: `929c11cbb7e3245a159778a26560f39f2e6fb97748640b8dd1667a73310b82ed`
- Rootfs SHA-256: `90ead734a1326d8ca20687a117f18d2e5362b531950c314bd0199b8e162bf0af`
- Full-slot CRC32: `375f1364`
- Full-slot SHA-256: `a899e943805404f3211ae5089e4f38e267f29d3712062bb4f0eb52395e5e4c0f`
- Candidate eligible: false
- Flash supported: false
- Hardware validation: NOT RUN

## Single capability

F278 inherits the exact F277 kernel, DTB, configuration and rootfs, then adds:

- `/usr/sbin/om-multicast-cert`;
- `/etc/openmitrastar/features/multicast-cert-v1`;
- the F278 release identity.

Nothing runs at boot. The harness modifies only the three live `br0` multicast
sysfs controls after an exact acknowledgement. It snapshots their original
values, serializes access through a stale-lock-aware lock, arms a bounded
rollback watchdog and restores the exact previous values.

It contains no MTD, boot environment, `/persist`, `mtd5` or package-store write
path.

## Validation

- POSIX shell syntax: PASS.
- Status is JSON and read-only: PASS.
- Apply without exact ACK is rejected without state change: PASS.
- Apply and rollback restore exact values in the sandbox: PASS.
- Static no-persistent-write contract: PASS.
- Builder/rootfs/kernel contract tests: PASS.
- Combined F278 tests: 6 PASS.
- `SHA256SUMS`: PASS for every packaged artifact.

## Promotion boundary

F278 must remain offline until F277 has booted and passed its live plan and
`mode-write-same` gates. It must not be used to skip the F277 Quantenna
checkpoint.

