# OpenMitraStar F171 candidate

Snapshot date: `2026-09-01`

## Status

- Installed firmware remains **F170** in physical `mtd4/linux_live`.
- F171 is an offline, reproducible flash candidate. Hardware validation is
  `NOT_RUN`; this document does not claim that F171 has been installed.
- Normal writes remain restricted to physical `mtd4/linux_live`.
- `mtd3/linux_safety`, `mtd5/data`, bootloader and environment remain outside
  the write set.

## Candidate

- File:
  `work/mission-state/q3-persistent-composite-f171-lyoko-foundation-health-fix/build/openmitrastar-linux510-q3-persistent-f171-lyoko-foundation-health-fix-LZMA-OFFLINE-NO-FLASH.webformat.bin`
- Size: `4,964,352` bytes
- SHA-256: `0ab845197b8612d4b3a4f70d2d0845f6d9c57284813083485e8198ab1cdad654`
- Candidate CRC32: `5baea262`
- Full-slot CRC32: `478d9342`
- Full-slot SHA-256:
  `8b12e858efa8f176b335bb121c3cbc2eccf41921b5d96dac8ec684bde0a6c05d`
- Bootbase contract: PASS
- Slot fit: PASS, `3,031,040` bytes headroom
- Offline suite: `19 passed`
- Repeated build SHA-256: identical
- Immutable source snapshot:
  `versions/lyoko-foundation-1.0-f171/`; subsequent Foundation work continues
  in `versions/lyoko-foundation-1.1-dev/` so rebuilding F171 cannot silently
  absorb newer UI or API changes.

## Single-scope changes

- Retry the IPv6 local policy from `S90-ready` after `br0` exists and clear
  the stale `S34-ipv6-local-policy` degraded marker only after success.
- Make a verified no-op transaction consume both pending and rollback state,
  and report `rollback_available=false`.
- Define the `/persist` root used by the still feature-gated material commit
  path.
- Identify the runtime and nested manifest schemas as F171.
- Install `S90-ready` with mode `0755`.

Kernel, DTB and both radio module sets are byte-identical to F170/F167.

## Discriminating live gate

`post_flash_f171_foundation_gate.py` was run against the currently installed
F170. It correctly passed the base SquashFS, SSH, API, radio, firmware and
privacy checks, while failing exactly the two conditions F171 changes:

- `boot_ready=false`
- `no_op_transaction=false`

Evidence:
`outputs/postflash/f171-gate-against-f170-20260901T115240Z/status.json`

After promotion, acceptance requires every F171 check to pass, including
strict existing SSH host-key validation, `boot-state=ready`, native 2.4/5 GHz
API values and isolated no-op transaction cleanup.

## Reproducible commands

Dry run, build and tests:

```powershell
.\tools\build_flash_test_f171_lyoko_foundation.ps1
```

Materialization is intentionally a separate explicit operation:

```powershell
.\tools\build_flash_test_f171_lyoko_foundation.ps1 -Execute -SkipBuild -Transport uart-ymodem
```

UART/YMODEM remains the proven transport. A direct Bootbase RRQ to the
temporary APELSITO TFTP server timed out before any erase or flash write.
