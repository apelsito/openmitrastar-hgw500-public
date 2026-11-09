# OpenMitraStar F225 Candidate

Date: 2026-09-02

F225 is a private, device-bound Foundation candidate derived from F224. It
makes configuration transactions understandable and makes the local emulator
enforce the same fail-closed behavior expected from the physical appliance.

## Artifact

- Bytes: `5210112`
- SHA-256: `d0f82ed4f99194cfe65aee48058168261d79fa0b5a0dc5d4a465ac59c8d206e8`
- Full-slot CRC32: `6e3a8206`
- Full-slot SHA-256: `2523a4c1dd3c40387a49e2f4e78b6eedda78a2e239315d32fda801eb50c9ea98`
- Location: `%USERPROFILE%\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f225-device-bound`

## Changes

- Replaces raw transaction JSON with a structured `before -> after` review.
- Shows phase, short transaction ID, expiry or commit state.
- Keeps `recovery-required` and other detailed failures visible in the
  transaction panel instead of reducing them to a transient generic toast.
- Transaction status now returns both before and after snapshots after reload.
- The Python and Node emulators reject missing CSRF, missing confirmation,
  unknown fields, invalid channels and concurrent transactions.
- Uncertified 5 GHz DFS channels remain rejected by the emulator.

## Preservation

- Kernel, config and DTB are byte-identical to F224 and F222.
- The F224 `lyoko.radio.settings/v1` backend remains unchanged.
- Package manager, signed feed, SSH identity and storage split remain unchanged.
- No hardware, UART, radio or flash operation occurred.

## Evidence

- Foundation/backend tests: 20 PASS.
- SHA256SUMS: PASS.
- Browser stage `channel 1 -> 6`: PASS.
- Apply and reload preserving the comparison: PASS.
- Rollback restoring channel 1: PASS.
- Mobile 390x844 layout: PASS without horizontal overflow.

F225 remains hardware `NOT_RUN`. It is a product/UI candidate and must remain
separate from the F223 RX-ring datapath experiment until the physical F223
campaign selects or rejects that kernel.
