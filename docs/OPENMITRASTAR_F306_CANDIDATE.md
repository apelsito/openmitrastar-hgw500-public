# OpenMitraStar F306 Physical Promotion Candidate

Date: 2026-09-04

## Classification

- Version: `6.7.3-f306-unified-product`
- Offline build: PASS
- Candidate eligible: yes
- Flash supported: yes, only through the guarded pipeline
- Hardware validation: NOT RUN
- Current installed firmware: F301

F306 promotes the complete F305 console and API without changing the proven
F301 kernel or radio payload. It is prepared for the normal Lyoko cycle:

```text
build -> mtd4/linux_live -> physical tests -> keep or exact F301 rollback
```

## Composition

- Kernel, config, DTB and vmlinux: byte-identical to F301.
- Radio modules, firmware, power tables and control files: 86/86 byte-identical
  to F301.
- Product surface: F305 Normal, Advanced and Developer console plus its API.
- Runtime identity: `lyoko-foundation-6.7.3-f306-unified-product-device`.
- Store observer: packaged, disabled and not autoloaded.
- Multicast harness: packaged and inactive.
- DFS writes: disabled while the native radar detector remains unavailable.

## Artifact

- File: `openmitrastar-linux510-f306-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`
- Bytes: `5,267,456`
- Candidate CRC32: `6b1387dd`
- Candidate SHA-256: `a245ab177e9ce7688c638b34161265bcdc70c5d21da54715530801fe20e33dc2`
- Rootfs SHA-256: `58060918d3af34ca61e53ab241c19b329c9b37f16a583bed09831817d71dc9eb`
- Kernel SHA-256: `fefc38802811f6639b847cc8e4166b4b6ddd0b9c0361bfde3a31262b5d716649`
- Full-slot CRC32: `71548682`
- Full-slot SHA-256: `c0a17995cbde98d28748dce3a7163b3629dd3a9783ea33dde32cda5eaf077b36`

Private output:

```text
/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f306-device-bound
```

## Physical Acceptance Contract

The promotion gate requires:

- exact F301 installed full-slot identity before writing;
- write target restricted to physical `mtd4/linux_live`;
- readback and protected-partition verification;
- authenticated login and dashboard;
- Normal, Advanced and Developer modes;
- canonical `PATCH /api/v1/radios/{2g|5g}` contract;
- 23 capability rows and seven live asset hashes;
- one 32 MiB bidirectional 2.4 GHz transfer;
- one 32 MiB bidirectional 5 GHz transfer plus 120 seconds of traffic;
- separate final health reads with five retries each;
- automatic exact rollback to F301 after any non-PASS result.

The coordinator checks `outputs/locks/f301-physical-radio.lock`. A live soak
owner makes `execute_allowed_now=false` and blocks execution before hardware
preflight.

## Verification

- Two complete builds produced identical `SHA256SUMS`.
- Combined F301/F304/F305/F306 regression: 92/92 PASS.
- F306 builder and physical-pipeline suite: 26/26 PASS.
- Bootbase contract, slot fit and `SHA256SUMS`: PASS.
- Dry-run contract: PASS.
- Current dry-run execution state: blocked by the active F301 sequential soak.
- SSH, COM, UART, TFTP, flash, radio mutation and MTD actions in this task: 0.

Dry-run evidence:

```text
outputs/preflight/f306-unified-product-final-20260904T160638Z/plan.json
```
