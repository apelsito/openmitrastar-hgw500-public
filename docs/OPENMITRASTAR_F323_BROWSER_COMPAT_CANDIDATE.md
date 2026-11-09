# F323: browser compatibility over installed F321

Prepared offline on 2026-09-11. **Not installed; NO GO for physical execution.**
This candidate closes the integration step for the two browser defects recorded
in `docs/OPENMITRASTAR_F321_BROWSER_ACCEPTANCE.md`. It does not add radar,
enable persistent writes or complete the Linux 5.10 migration.

## Immutable artifact

Private directory:
`/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f323-f321-browser-compat-device-bound`.

Image:
`openmitrastar-linux510-f323-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`.

| Property | Value |
| --- | --- |
| Image bytes | 5,361,664 |
| Image SHA-256 | `9d8dbd5bd9a6c372e95d8f6365396f8eb4695ab61848cd49341d76fee2153c11` |
| Full-slot bytes | 7,995,392 |
| Full-slot expected CRC32 | `ba8a6167` |
| Full-slot expected SHA-256 | `5d04789476852e8623b6266f3f237f21ed1105ddad2842505c09abdd66acc3de` |
| Candidate manifest SHA-256 | `fd8638db46f905383ada91e2e99f1bdc05a64623fd282c37baa30dd8a5388a4a` |
| Rootfs inventory SHA-256 | `a2ae4d2d7598719749ccbda6d850b67454cc9170cee6201acd11dd048c44d8af` |
| Bootbase contract SHA-256 | `195fcca7910275311792652b2cb25f7da706c1f09a094e15874973f4bc2d406c` |
| Product version | `lyoko-foundation-6.9.2-f323-browser-compat-f321-device` |
| Firmware build ID | `f61bc760266ccf19` |
| UI version / build | `0.3.1-classic-compat` / `019cdf1a2a608c2d` |
| Rootfs offset / window | `0x180000` / `0x460000` |
| Rootfs headroom | 798,720 bytes |
| Reserved store begins | `0x5e0000`, left erased in the expected full-slot image |

Full-slot hashes and CRC here describe the **local padded artifact**, not a
hardware readback. The Bootbase contract verifies format/header/load/entry and
payload acceptance; it does not prove a physical boot or a working mtd3 rescue.

The UI package is
`outputs/frontend/lyoko-classic-compat-019cdf1a2a608c2d`, manifest SHA-256
`fb7b57a594148cb1af33708aa09e3e516d3dafe8c43acc89fb5cf944456d4eaa`.

## Change boundary

Source: exact local F321 image SHA-256
`eb8e23ac75ec50e113cd337e9b68ab86e366a09c8dbbec255a3b426843a9da18`,
rootfs SHA-256 `75b044206fea26ecbac36ce45508d2b32687643b2fcd606e16ea9a2c7766fe9e`.
The recorded F321 acceptance and its source manifest were separately pinned.

Only these seven paths change:

```text
etc/lyoko/frontend.env
etc/lyoko/web-next.env
etc/lyoko/web-next.json
etc/openmitrastar/release
usr/libexec/openmitrastar/om-api-v1
usr/share/openmitrastar/web/dashboard.html
www/assets/lyoko-next/lyoko-D-cCRVi6.js
```

The native before/after inventories, including a fresh extraction of the packed
rootfs, preserve 434 entries and the metadata of all 69 existing directories.
No directory is added. CSS, brand files, the common JS chunk, old fixed assets,
CGI authentication, radio drivers/control/bootstrap, calibration-dependent
inputs, host keys, credentials and storage modules remain unchanged. Existing
unused hashed assets are retained; this is not an asset-pruning change.

The kernel payload, load/entry/type metadata and all six kernel sidecars match
F321. No kernel or radio driver compilation was performed. F322 is a separate,
uninstalled shadow candidate and is not a source of this image.

The API correction changes only the literal-brace guard in config/store status;
the corrected API hash is
`f7e6568f9749a848f0f5f9b75cd7eec8b4d0346d2214cb987f0b173a6ad763e1`.
The existing split-bundle frontend branch and POST behavior are preserved. The
UI fallback recognizes only the explicit legacy 5 GHz status alias and keeps
CAC/NOP/TX authority unknown when the old backend does not publish them.

## Verification

- Existing source-fix tests: 27 API/DFS tests and 9 config-store branch tests.
- F323 contract tests: **13/13 PASS**, including 48 header-byte mutation
  subcases, source pins, release delta, metadata preservation and storage bounds.
- F323 package tests: **33/33 PASS**, with no skips. Include real temporary
  symlinks, changed JS/HTML with recalculated hashes, provenance, identities,
  URLs, brand/CSS preservation and strict authority flags.
- All 15 files in the candidate's `SHA256SUMS` were independently rehashed.
- Initial build:
  `outputs/preflight/f323-browser-compat-20260911T141428342374Z/result.json`.
- Independent second build:
  `outputs/preflight/f323-browser-compat-20260911T141601823529Z/result.json`.
  It reports `REPRODUCIBLE_PASS_NO_GO_PHYSICAL`: image, rootfs and all six
  kernel sidecars match byte for byte. It did not replace the first artifact.

The builder pins its inputs/tools and records their hashes. File-only recovery
verification rechecked the exact F314 artifact and historical Bootbase recovery
transcript. This is neither a new recovery rehearsal nor permission to write.

Reproduce without overwriting the original:

```powershell
python -B tools/build_f323_browser_compat.py `
  --package outputs/frontend/lyoko-classic-compat-019cdf1a2a608c2d `
  --package-manifest-sha256 fb7b57a594148cb1af33708aa09e3e516d3dafe8c43acc89fb5cf944456d4eaa `
  --verify-reproducible
```

## Physical gate still required

The F323 installation/recovery executor is now reviewed **offline**, under
`outputs/preflight/f323-executor-20260911T150647Z/executor-review.json`, SHA-256
`43c3ba71ea2fa2dba0ff1d3ec0a7a645cdfbe179968280eeb0e92e1c22a31d36`.
Its final qualification records **148 passing tests and 69 passing subtests**,
with no failed or skipped selected cases. The 47 deselected historical cases
are not counted as executed. All 40 bound source files are copied and rehashed
under the adjacent `executor-source-snapshot` directory. Qualification SHA-256:
`1095b3d172a21dbaa47581a5a49b5f5254aad1dc11b23cf6b2df637f1b83b302`.

The owner later authorized the exact F323 installation and controlled F321
recovery with `SI AUTORIZO`. The record is
`outputs/authorizations/f323-20260911T153634Z/authorization.json`. Do not reuse an
F319/F320/F321 ACK or invoke an older promoter with replacement files. All
eligibility flags in the immutable candidate remain false. The separate review
does not alter those historical packaging fields or grant hardware authority.

Entrypoints are `tools/promote_f323_mtd4_direct.ps1` and
`tools/f323_restore_mtd4.ps1`. Both default to file-only dry-run and require the
exact review path/hash in execute mode. Promotion has its own action ACK:
`OPENMITRASTAR_F323_MTD4_9D8DBD5B`. F321 restoration and the separately invoked
F314 contingency have distinct ACKs. Knowing an ACK string is not user approval.

The new executor preserves the checked F321 writer and binds only its exact
image table and explicit workspace context. A real backend dry-run caught and
fixed PowerShell's empty `PSScriptRoot` in dynamic script blocks; both backend
and reboot adapter now bind their checked source paths explicitly. Tests cover
the real no-execute backend, not only extracted functions. Earlier test reports
remain untouched and do not qualify the final source revisions.

F323 additionally propagates uncertain SSH termination to a sticky failure
flag, refusing another cycle, rollback or lease release until that uncertainty
is resolved. Reboot, YMODEM entry and flash backend require an inherited live
lease and authenticated board-binding context before transmission. The context
is not an authorization and does not replace the exact ACK/review checks.

Only a verified writer followed by a failed platform/HTTP gate can trigger one
F321 restoration under the original held lease. Missing/ambiguous writer results
stop without retry; failed restoration never chains F314 automatically. The
HTTP gate checks 12 installed hashes, exact frontend metadata, all 19 panel
reads, config/store status, legacy DFS observations and normal login/logout.
It does not claim browser JavaScript, client traffic, CAC or release acceptance.

Pinned SSH at 2026-09-11 15:09 UTC still observed F321, build
`ad60c8e1e49dfbbf`, with a clean SSH exit. No UART was opened, no radio setting
was changed and no flash was performed. The absent lock directory is not proof
of COM3 ownership or physical connection; those must be verified at execution.

The guarded attempt at
`outputs/flash-watch/f323-direct-20260911T153844Z-5e485259` failed in the UART
transfer before the flash backend was invoked. It reached 3,529,728 confirmed
bytes and then exhausted YMODEM retransmissions. No RAM-integrity PASS, erase or
flash-write stage was reached. The original `STOP_NO_AUTOMATIC_RETRY` result is
preserved, with confirmed helper termination and no automatic retry/reflash.
The adjacent `preerase-failure-audit.json` separates those facts from the
still-unresolved transport cause.

The owner then power-cycled only the HGW without moving the UART. Pinned SSH
at 15:57 UTC and the 27/27 platform gate at 16:00 UTC confirmed F321 was running
again. This is recovery of the existing F321 boot, not a reflash or F323 pass.

The remaining immediate gate is diagnosing and qualifying the transfer path,
then obtaining fresh ownership, pinned SSH/UART board binding,
protected/current-slot checks and readback before another attempt. The existing
authorization remains valid for this exact F323 image and F321 recovery scope.
Any changed host executor requires a new review; the old review does not qualify
modified code. Exact
F314 restoration is the historical tested recovery; F323-to-F321 restoration
is not proved merely by having the F321 image, and a working mtd3 rescue rootfs
remains unproved.

After installation, the acceptance gate must run the real authenticated browser:
all 19 panel reads, honest legacy DFS observations, login/logout, unchanged
branding and radio/client regressions. None of those physical results is implied
by this offline artifact. OEM and physical mtd0/mtd1/mtd2/mtd3/mtd5, logical mtd6,
boot environment and calibration remain outside this iteration's write scope.

## Alternative transport preparation, 2026-09-11 19:34 UTC

Following the three pre-erase UART stops, F321 was recovered and passed 27/27
platform checks. F323 is still uninstalled. A quiet 32-KiB Linux UART receive
window passed, but does not qualify another complete YMODEM upload.

The unchanged F323 image now has an offline Ethernet transport preparation:
`docs/OPENMITRASTAR_F323_ETHERNET_PREPARATION.md`. The scoped server and file-only
plan passed 122/122 focused tests, including a full-size synthetic transfer.
No real image was served and no LAN listener or firewall change was made.
The PC Ethernet carries its default route and is not proven isolated. The
additional private-image network exposure and temporary networking scope need
an owner decision, and the Ethernet executor/recovery review remains pending.
The existing firmware authorization is preserved; no further firmware build
or repetition of the old UART attempt is justified by this preparation.
