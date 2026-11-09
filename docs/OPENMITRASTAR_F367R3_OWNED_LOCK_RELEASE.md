# F367r3: release the owned IPC lock with available HGW utilities

2026-09-22. **PASS_OFFLINE_F367R3_OWNED_LOCK_IMAGE**.

Root confirmed on the real HGW that neither `rmdir` nor the BusyBox `rmdir`
applet exists. The old EXIT trap hid that failure with `|| true`, leaving
`ipc-lock` present after BEGIN. Later keeper/verify calls could not acquire it.
The previous readonly preamble/lease analysis did not establish this missing
utility; this target observation closes that concrete cause.

R3 changes only the lock lifecycle in `om-f367-stage`, retaining all R2
protection. The stage must have created the fixed private child directory
itself. It records its PID, rejects a replaced/symlink directory, checks the
exact own marker, and refuses any unexpected visible or hidden entry. It then
removes its marker and the checked-empty directory using verified `/bin/rm`.
There is no recursive force deletion or arbitrary path argument. Cleanup is
attempted once; failure is visible as `OMF367_LOCK_RELEASE_FAILED` and exit74,
even if the preceding IPC request succeeded.

Root executed the exact production cleanup function once with `/bin/ash` on
one newly created private fixture. It passed without stderr and removed no
pre-existing data or watchdog/radio/MTD state:
`outputs/handoff-live/f367r3-lock-probe-20260922T143309Z/result.json`,
SHA-256 `b211f67850e14413837f6a2c6ebc9292f139dceba7bae3d3cbf4f66f7f4f5ea5`.
The exact cleanup function hash is
`0c385205d8205c439d43f80533677720d9d2f72acfff6893b7fe841dfd3f49be`.
This probe was performed by root; the implementation agent did not access HW.

The focused delta test uses the actual helper and IPCv2 with no rmdir in PATH:
`outputs/preflight/f367r3-owned-lock-20260922T143418Z/result.json`,
SHA-256 `e804db4eff641ae20d3f4032a351c4fd802dbcfa0a9d3495d307e10137ff5d9d`.
It proves BEGIN/CEASE release, twelve concurrent HEALTH transactions, retention
of foreign ownership/symlink targets/unexpected entries, and explicit exit74
when removal fails. Its watchdog backend is test-only. Earlier R2 runtime,
preamble, guard and unchanged binary evidence are reused by SHA, not rerun.

The final qualification is
`outputs/preflight/f367r3-lock-qualified-20260922T143629Z/result.json`.
It verifies that all stage code after the lock lifecycle and every other R2
runtime helper remain byte-identical.

## Immutable candidate

Private result: `analysis/f367r3-fullimage-20260922T143805Z/result.json`.
Private directory: `f367r3-f365-owned-lock-release-device-bound/`.

| Property | Value |
| --- | --- |
| Bytes | 5,459,968 |
| Image SHA-256 | `a9d6283c383f65a0f02ea37c7624910b461e6e48adbf49c678b274af34b3f53c` |
| Manifest SHA-256 | `22d3ee5485ca30606b79981ec7b7ab6ab70c4874a2f9d9d1db58620ca9a5289e` |
| Product | `lyoko-foundation-6.11.2-f367r3-owned-lock-release-device` |
| Build ID | `8aa0aa32903368e0` |
| Prefix CRC32 | `1389675d` |
| Full-slot CRC32 | `3def6860` |
| Full-slot SHA-256 | `5e70ea5a0c36a76839ee60dbf6b9d8c9bba495884334287e67f0ffefbc9fd5e1` |
| Stage SHA-256 | `09b2131653cc98ac65b2ed3375d7e8c47c01d52a84d120cad9a9f5519a6313b9` |
| Bootbase / slot fit / reproduction | PASS / PASS / two identical repacks |

Kernel, qdrv, provider, engine, supervisor, preamble policy, HEALTH5s,
horizon90min, quarantine1800, CAC70 and NOP1800 are unchanged. The exact F365
fallback remains full-slot CRC32 `118901d4`, with journal CRC32 `5d2ee646`.
Old F367 and F367r2 artifacts remain immutable and are not execution targets.
The next gate is the new root-owned physical activation/CAC/client/NOP campaign.
