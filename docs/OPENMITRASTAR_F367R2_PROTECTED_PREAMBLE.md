# F367r2: protect the real preamble before module loading

2026-09-22. **PASS_OFFLINE_F367R2_PROTECTED_PREAMBLE_IMAGE**.
This revision changes shell protection and failure evidence only. Kernel,
qdrv, native provider, OEM userspace engine and both watchdog binaries are
byte-identical to the preceding F367 candidate. No hardware action or C rebuild
was performed to prepare this revision.

## Established failure and remaining uncertainty

The capture-only repetition of F367 preserved
`OMRADIO5_REFUSED reason=f367-watchdog-not-protecting-module-load` before the
first dependency module. It occurred15.187 seconds after the host campaign
stage began; the preceding HR_TIMER_POLICY marker occurred at12.078 seconds.
ARM/BEGIN have no individual captured timestamps. The30-second phase and
90-minute horizon had not elapsed solely by this duration.

The old wrapper began `module-load` before the lengthy readonly preamble.
The preamble relied on an asynchronously launched keeper, without confirming
its actual HEALTH acknowledgement. Its first foreground HEALTH verification
was after calibration and artifact hashes. A missing or delayed keeper could
therefore expire the5-second lease while the30-second phase remained current.
The captured physical record did not contain the owner deadline or precise
verify RC, so it does not uniquely prove why that keeper stopped confirming.

A focused reproduction executes the actual sealed helper prefix through its
first module guard, using explicit local file fixtures and slow hashes, with
the actual IPCv2 supervisor and test-only watchdog backend:

| Case | Result |
| --- | --- |
| Old helper, keeper delayed6s | Same refusal at9.287s; lease expired, owner retained FD, phase still `module-load` and30-second deadline still future |
| Old helper, keeper immediate | Protected prefix passes |
| Revised helper, keeper delayed6s | Protected prefix and actual keeper acknowledgement pass |
| Revised helper, keeper absent | Rejected before module loading with `keeper-missing`; foreground preamble remains protected |

This demonstrates the protection gap and its correction. It does not invent a
unique explanation for the original physical keeper failure.

## Narrow correction

- ARM still precedes the helper and the HEALTH lease remains5 seconds.
- Readonly checks have an explicit30-second `preamble` phase. Foreground
  HEALTH acknowledgements occur before the preamble and during calibration
  and artifact hash loops; they cannot renew the phase or total deadline.
- Before loading any module, the guard requires an actual, recent keeper
  HEALTH receipt for the same nonce, phase and sequence. A PID or stale file
  alone cannot pass. The keeper deadline must remain at least2500ms ahead of
  the fresh foreground receipt's last-pet timestamp; that timestamp already
  has the client's bounded freshness validation.
- The helper then completes `preamble`, begins the unchanged30-second
  `module-load` phase and performs its original live HEALTH verification.
- Phase mismatch, failed HEALTH, missing/stale keeper and lock failure now
  have distinct receipts. They expose only operation/RC, phase/sequence, owner
  state and deadlines. No nonce, credentials, client addresses or MMIO data
  are emitted.
- Keeper failure/exit reaches the console ledger. The controller prints the
  native return code and sanitized refusal before cleanup.

CAC70, NOP1800, initial local quarantine1800, AP52/BW20→36, callback authority
and every radio command remain unchanged. The supervisor's total90-minute
deadline,5-second lease and128-phase limit are unchanged. The new startup phase
is visible in `campaign.startup_phases`; it is not an extension of CAC or NOP.
The host may budget up to240 seconds for the transport's complete activation
call, including the separate unarmed owner-start wait and bounded startup
phases. This does not alter any watchdog or radio timer.

## Immutable image

Private result: `analysis/f367r2-fullimage-20260922T134401Z/result.json`.
Private directory: `f367r2-f365-protected-preamble-device-bound/`.

| Property | Value |
| --- | --- |
| Bytes | 5,459,968 |
| Image SHA-256 | `d106f448ba0bff1b4a7d2eaa28434cc36f518ce8c4fd17e5312a9a080a2c08ed` |
| Manifest SHA-256 | `c2ba47c911d135bfdfcfc317cac6182025a3f5fff13da0cbef9aed2360d1d659` |
| Product | `lyoko-foundation-6.11.1-f367r2-protected-preamble-device` |
| Build ID | `5e10ad51dec1443b` |
| Prefix CRC32 | `2edbcaef` |
| Full-slot CRC32 | `12ff8ce9` |
| Full-slot SHA-256 | `ce6dacaf16d45cdc5f3c157ec2b6a5dba5c8f636b409727b271b3c42d12be5a6` |
| Bootbase / slot fit | PASS / PASS |
| Headroom before store | 700,416 bytes |

The exact F365 fallback remains SHA-256
`43f4655f09eb01d749ca24c003689470b2f7c2d2738333297348e965e56d5355`,
full-slot CRC32 `118901d4`; preserved journal CRC32 `5d2ee646`.
The original F367 image and every earlier failure record remain unchanged.

## Qualification

- `outputs/preflight/f367r2-preamble-20260922T133718Z/result.json`:
  four real-prefix/actual-IPC cases above, no module load or physical action.
  The old prefix is bound to the sealed native helper hash
  `b2a1f2d7d0fa225cff018478084711ebf54d533db6faa8fbf136c98f8f46b271`.
- `outputs/preflight/f367r2-guard-diagnostics-20260922T134142Z/result.json`:
  phase mismatch returns25 with an active owner; expired HEALTH returns24
  with a ceased owner and future phase deadline. STATUS probing changes no
  health, phase or session deadline.
- `outputs/preflight/f367r2-runtime-20260922T134142Z/result.json`:
  28 actual-shell/IPC checks with fake radio/watchdog. Failed activation
  returns EOF in under5s while the fake supervisor remains FD-held for10s.
  This validates cleanup, not the physical cause of the old SSH timeout.
- Existing binary, policy and radio qualification is reused by exact SHA.
  Two complete image repacks, catalogues, inventories, Bootbase, slot fit and
  stale-hash checks pass again for the changed shell image.

Physical bootstrap/CAC/client/NOP acceptance remains for the root-owned new
gate. No RF certification or release completion is claimed by this artifact.
