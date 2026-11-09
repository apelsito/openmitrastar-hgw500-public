# OpenMitraStar F304 API v1 Audit

Date: 2026-09-04

## Scope

Offline audit of the F301 backend against the complete Lyoko API v1 objective.
F304 changes only `usr/libexec/openmitrastar/om-api-v1` plus release identity.
No router, SSH, UART, TFTP, radio, flash or MTD operation was executed.

## F301 Classification

| Area | F301 state | Classification | Evidence or limitation |
|---|---|---|---|
| `GET /status` | Present | Implemented | Reports health, uptime, memory, load, boot, persistence and apply feature state |
| `GET /network` | Present | Implemented | Read-only bridge/interface, IGMP/multicast and VLAN observation |
| `GET /radios/{id}` | Present | Implemented | Delegates to the non-secret `om-radioctl` status/contract backend |
| `PATCH /radios/{id}` | Rejected with 405 | Functional but different contract | F301 stages through `/radios/{id}/stage` instead of the documented canonical route |
| `GET /clients` | Present | Implemented | Counts only; client identifiers remain redacted |
| `GET /hardware` | Present | Implemented with hardware limits | Buttons and LEDs observable; temperature, GPIO and watchdog report unavailable when the kernel exposes none |
| `GET /diagnostics` | Present | Implemented | EMAC, F300 RX-demand telemetry, IRQ, TQE, DFS readback and fatal markers |
| `GET /privacy` | Present | Implemented | Secret and identifier disclosure policy; persistence policy was implicit |
| `GET /firmware` | Present | Implemented with stale metadata | Active/recovery slots correct, but `rootfs_live_bytes` was hard-coded to the pre-store-split `0x620000` value |
| `POST /config/apply` | Present | Implemented, hardware-dependent | Verified runtime transaction with automatic rollback; 2.4 and 5 GHz remain subject to their backend gates |
| `POST /config/rollback` | Present | Implemented, hardware-dependent | Reapplies and verifies the runtime snapshot; no persistent write |
| Package catalog/query | Present | Implemented | Signed local feed: update/search/info/depends/plan; no network fetch |
| Package install/remove | Present but disabled by default | Implemented, feature-gated | RAM-only `/run` lifecycle was physically proved on F292; persistent install is absent |
| DFS mutation | Denied | Blocked by hardware | Radar detector is not ported; acknowledgement cannot make DFS writable |
| Persistent config/package writes | Not part of target API | Absent by policy | Storage write path remains uncertified and disabled |
| Firmware update API | Not present | Absent by policy | Normal firmware iteration remains the guarded external `mtd4` pipeline |

## F304 Corrections

- Adds canonical `PATCH /api/v1/radios/{2g|5g}`.
- Keeps `/radios/{id}/stage` as a compatibility alias using exactly the same function.
- Preserves the DFS acknowledgement and radar-readiness gates.
- Reads `linux_live`, `linux_safety`, `rootfs_live` and `lyoko_store` sizes from
  `/proc/mtd`; removes the stale `6422528` rootfs constant.
- Declares firmware API writes, persistent configuration writes and persistent
  package writes as disabled.
- Declares package install scope as RAM-only and reports the feature-gate reason.
- Adds test-only root overrides for `/dev` and dmesg without changing router defaults.

## What F304 Does Not Claim

- No physical boot or API test on the HGW was run.
- No dynamic 5 GHz control or DFS capability was enabled.
- No persistent configuration or package installation was enabled.
- No frontend or radio/backend implementation changed.
- F301 remains the installed image.

## Decision

F304 is an offline API-contract candidate. It is deliberately marked
`candidate_eligible=false` and `flash_supported=false` for this task.

## Offline Artifact

- Candidate: `openmitrastar-linux510-f304-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`
- Bytes: `5,267,456`
- SHA-256: `8f66dba3089862e67449063a4d89a84fa25082a672b065789715cd8ad9459699`
- Rootfs SHA-256: `e59313923ed5d9a6a3decfff36671f2e0ea366c912f8162703c46600672eca17`
- Full-slot CRC32: `ddb99b8a`
- Full-slot SHA-256: `ac492113b9691739d5f38aed349190fd60e3701a4b898a84392c5c8f8d673f8b`
- Rootfs changes: `etc/openmitrastar/release` and
  `usr/libexec/openmitrastar/om-api-v1` only.
- Kernel and 86 radio/configuration files: byte-identical to F301.

## Verification

- BusyBox 1.38 API tests: PASS.
- HTTP emulator tests: PASS.
- F298 inherited API, transaction, package and radio regressions: PASS.
- Combined suite: `48/48 PASS`.
- Final focused F304 suite after reproducibility rebuild: `13/13 PASS`.
- Two consecutive builds produced the same candidate SHA-256.
- `SHA256SUMS`: PASS.
- Machine-readable audit:
  `outputs/audit/f304-api-20260904T152130Z/audit.json`.
