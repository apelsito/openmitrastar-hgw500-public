# OpenMitraStar F298 Full offline capability-truth hold

Date: 2026-09-04

F298 replaces stale internal capability labels with a human-readable inventory
grounded in current F292-F297 evidence. It keeps one unified Developer console
and changes no kernel, radio or runtime-control behavior.

## Artifact

- Runtime: `lyoko-foundation-6.6.0-f298-capability-truth-device`
- Bytes: `5267456`
- SHA-256: `7786fd8e68b16dccc4245bbf0f716a1063e39d0d7cc6a17121bf397950898389`
- Full-slot CRC32: `775fa9be`
- Full-slot SHA-256: `bed234b6661a9110186bcf3fcbd27b94eb708cb279de97026d93c3334049e6fe`
- Candidate eligible: false.
- Flash supported: false.
- Hardware boot: NOT RUN.

## Capability model

The console now displays 23 named capabilities. Each item includes:

- an operator-facing Spanish title;
- a concise explanation of what the capability does;
- its technical identifier and subsystem;
- actual availability state;
- concrete evidence from the current physical or offline lineage.

The registry distinguishes physical support, experimental controls,
certification requirements and hard blockers. It records the current package
lifecycle evidence, F293 RX telemetry, F295/F296 storage observation, F297
multicast preparation, the VLAN topology blocker and the unproven Linux 5.10
safety-slot boot.

## Validation

- Foundation and F298 tests: PASS.
- JavaScript syntax and deterministic frontend identity: PASS.
- Desktop: 23 capability rows and no horizontal overflow.
- Mobile `390x844`: 23 rows and no horizontal overflow.
- Browser console errors: zero.
- Kernel, DTB and radio modules: byte-identical to F297/F293.
- Hardware actions: none.

F298 remains an offline non-flashable hold until the F293 physical campaign.

