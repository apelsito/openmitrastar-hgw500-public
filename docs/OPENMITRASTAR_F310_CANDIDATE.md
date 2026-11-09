# OpenMitraStar F310 Canonical Frontend Identity Candidate

Date: 2026-09-04

## Classification

- Version: `lyoko-foundation-6.7.5-f310-canonical-frontend-identity-device`
- Base: exact F309 device-bound image.
- Change type: rootfs-only.
- Candidate eligible: yes.
- Flash support: guarded `mtd4/linux_live` pipeline only.
- Hardware validation: NOT RUN.

## Correction

F309 correctly removed the public `/www/dashboard.html`, but its generated
`/etc/lyoko/frontend.env` used CRLF records. The API's `frontend_value()` and
`release_value()` readers preserved a terminal carriage return, which could be
serialized as a trailing space in frontend and firmware identity values.

F310 applies three bounded corrections:

1. Packages `frontend.env` using LF-only records.
2. Removes one terminal CR defensively in `frontend_value()`.
3. Removes one terminal CR defensively in `release_value()`.

The authenticated dashboard receives only the new 6.7.5/F310 cache identity.
`/www/dashboard.html` remains absent and `/dashboard.cgi` remains protected by
the unchanged F309 CGI/session implementation.

## Rootfs Write Set

Exactly four paths differ from F309:

```text
etc/lyoko/frontend.env
etc/openmitrastar/release
usr/libexec/openmitrastar/om-api-v1
usr/share/openmitrastar/web/dashboard.html
```

Login assets, CGI, device identity, credential contract, bridge, package
runtime, storage policy and all other web assets are byte-identical to F309.

## Preserved Binary Contract

- Kernel, config, DTB and vmlinux: byte-identical to F309/F306.
- Radio payload: 86/86 files byte-identical to F309/F306.
- Datapath and recovery behavior: unchanged.
- Public dashboard file: absent in both F309 and F310.
- Store boundary: preserved and erased in the candidate image.

## Artifact

- File:
  `openmitrastar-linux510-f310-hgw500bna-qcv2-a2-primary-PRIVATE-NO-FLASH.webformat.bin`
- Bytes: `5,267,456`
- Candidate CRC32: `f9806ffa`
- Candidate SHA-256:
  `df451d720d8a959ff79ae6a2377940f6f9c3253f22d00f4b15752827e55ba330`
- Rootfs SHA-256:
  `15118844753dd61275821e751e2e9b8d35a11586a58924153bdabc20a4007893`
- Kernel SHA-256:
  `fefc38802811f6639b847cc8e4166b4b6ddd0b9c0361bfde3a31262b5d716649`
- Full-slot CRC32: `115c78af`
- Full-slot SHA-256:
  `3b24a09219485bc68e821d20b4a4a84a0ab31cc005144b492493158bd50d1c09`

Private output:

```text
/workspace/user-home\.openmitrastar\devices\hgw500bna-qcv2-a2-primary\firmware\f310-device-bound
```

## Verification

- Two independent SquashFS and webformat builds: byte-identical.
- `frontend.env`: zero CR bytes and final LF present.
- API source: exactly two terminal-CR normalization operations.
- BusyBox emulator with deliberately CRLF-formatted input returns exact JSON
  values without terminal CR or spaces.
- `/www/dashboard.html`: absent from the packaged SquashFS.
- F306/F309/F310 builder and pipeline regression: 61/61 PASS.
- Packaged `SHA256SUMS`: PASS.

## Promotion Pipeline

- `tools/promote_f310_mtd4_direct.ps1`
- `tools/run_f310_physical_campaign.ps1`
- `tools/rollback_f310_to_f309_mtd4.ps1`
- `tools/run_f310_flash_test_rollback.ps1`

Prepared post-promotion and long-run validation:

- `docs/OPENMITRASTAR_F310_POST_PROMOTION_GATES.md`
- `docs/OPENMITRASTAR_F310_24H_SOAK.md`
- `tools/run_f310_post_promotion_gates.py`
- `tools/f310_soak_runner.py`
- `tools/f310_soak_consolidate.py`

The coordinator's `Test-F310FlashCompleted` scans `result.json` evidence using
its embedded `generated_at` timestamp. It retries ten times with a two-second
delay and does not treat directory modification time as authoritative. A
contract test creates the successful result after polling begins and gives the
directory an intentionally stale timestamp; detection still passes.

Rollback restores the exact F309 candidate and preserves its authenticated-only
dashboard layout. No F310 hardware, SSH, AELITA, COM3, UART, TFTP, flash or MTD
operation was executed during preparation.
